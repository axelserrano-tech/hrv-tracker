import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import time
import streamlit.components.v1 as components

# This function creates the "Bridge"
# This function creates the "Bridge" - UPDATED FOR FIX
def hrv_sensor_component():
    components.html(
        """
        <style>
            .container {
                background: #f0f2f6; 
                padding: 15px; 
                border-radius: 10px; 
                text-align: center; 
                border: 1px solid #d1d5db;
                font-family: sans-serif;
                /* Fix: Ensure container manages its children's width */
                width: 100%;
                box-sizing: border-box;
                overflow: hidden;
            }
            #waveCanvas {
                background: #000; 
                border-radius: 5px; 
                margin-bottom: 10px;
                /* Fix: Make canvas responsive to sidebar width */
                width: 100%;
                height: 80px;
                display: block;
            }
            #camera-btn {
                padding: 12px; 
                background: #ff4b4b; 
                color: white; 
                border: none; 
                border-radius: 5px; 
                cursor: pointer; 
                font-weight: bold; 
                width: 100%;
                font-size: 14px;
            }
            #status-text {
                font-size: 14px;
                margin-bottom: 10px;
            }
        </style>

        <div class="container">
            <p id="status-text">📊 <b>Hardware:</b> Ready</p>
            <canvas id="waveCanvas"></canvas>
            <video id="video" autoplay playsinline style="display:none;"></video>
            <button id="camera-btn" onclick="initSensor()">
                Enable Camera & Flash
            </button>
        </div>

   <script>
let scanning = false;

const canvas = document.getElementById('waveCanvas');
const ctxWave = canvas.getContext('2d');

canvas.width = canvas.offsetWidth;
canvas.height = 80;

let signalBuffer = [];
let timeBuffer = [];
const MAX_SAMPLES = 400;

/* ---------- SIGNAL ACQUISITION ---------- */

function robustGreenAverage(pixels) {
    let greens = [];
    for (let i = 1; i < pixels.length; i += 4) greens.push(pixels[i]);

    greens.sort((a,b)=>a-b);
    const trim = Math.floor(greens.length * 0.1);
    const trimmed = greens.slice(trim, greens.length - trim);

    return trimmed.reduce((a,b)=>a+b,0) / trimmed.length;
}

function pushSignal(value) {
    const now = performance.now() / 1000;

    signalBuffer.push(value);
    timeBuffer.push(now);

    if (signalBuffer.length > MAX_SAMPLES) {
        signalBuffer.shift();
        timeBuffer.shift();
    }
}

/* ---------- PREPROCESSING ---------- */

function detrend(signal) {
    const mean = signal.reduce((a,b)=>a+b,0) / signal.length;
    return signal.map(v => v - mean);
}

// Lightweight band-pass style filter
function bandpass(signal) {
    let out = [];
    let prev = 0;

    for (let i = 1; i < signal.length; i++) {
        let hp = signal[i] - signal[i-1];     
        let lp = prev + 0.2 * (hp - prev);    
        out.push(lp);
        prev = lp;
    }
    return out;
}

/* ---------- PEAK DETECTION ---------- */

function detectPeaks(signal, times) {
    let peaks = [];
    if (signal.length < 10) return peaks;

    const mean = signal.reduce((a,b)=>a+b,0) / signal.length;
    const std = Math.sqrt(signal.map(x => (x-mean)**2)
                        .reduce((a,b)=>a+b,0) / signal.length);

    const threshold = mean + 0.8 * std;

    for (let i = 1; i < signal.length - 1; i++) {
        if (signal[i] > threshold &&
            signal[i] > signal[i-1] &&
            signal[i] > signal[i+1]) {

            if (!peaks.length || (times[i] - peaks[peaks.length-1]) > 0.35)
                peaks.push(times[i]);
        }
    }
    return peaks;
}

function computeIBI(peaks) {
    let ibi = [];
    for (let i = 1; i < peaks.length; i++)
        ibi.push(peaks[i] - peaks[i-1]);
    return ibi;
}

/* ---------- PHYSIOLOGICAL VALIDATION ---------- */

function validateIBI(ibi) {
    let clean = [];

    for (let i = 0; i < ibi.length; i++) {

        if (ibi[i] < 0.33 || ibi[i] > 1.5) continue;

        if (i > 0) {
            const ratio = ibi[i] / ibi[i-1];
            if (ratio > 1.25 || ratio < 0.75) continue;
        }

        clean.push(ibi[i]);
    }
    return clean;
}

/* ---------- ARTIFACT CORRECTION ---------- */

function correctArtifacts(ibi) {
    if (ibi.length < 5) return ibi;

    let corrected = [...ibi];

    for (let i = 1; i < ibi.length - 1; i++) {
        const localMean = (ibi[i-1] + ibi[i+1]) / 2;

        if (Math.abs(ibi[i] - localMean) / localMean > 0.2) {
            corrected[i] = localMean;
        }
    }
    return corrected;
}

/* ---------- HRV METRICS ---------- */

function computeHR(ibi) {
    if (!ibi.length) return 0;
    const sorted = [...ibi].sort((a,b)=>a-b);
    const median = sorted[Math.floor(sorted.length/2)];
    return 60 / median;
}

function computeRMSSD(ibi) {
    if (ibi.length < 5) return 0;

    let diffs = [];

    for (let i = 1; i < ibi.length; i++)
        diffs.push(ibi[i] - ibi[i-1]);

    const meanSq = diffs.map(d => d*d)
                        .reduce((a,b)=>a+b,0) / diffs.length;

    return Math.sqrt(meanSq) * 1000; // sec → ms
}

/* ---------- STATIONARITY ---------- */

function checkStationarity(ibi) {
    if (ibi.length < 10) return false;

    const half = Math.floor(ibi.length / 2);

    const mean1 = ibi.slice(0, half).reduce((a,b)=>a+b,0) / half;
    const mean2 = ibi.slice(half).reduce((a,b)=>a+b,0) / (ibi.length - half);

    return Math.abs(mean1 - mean2) / mean1 < 0.1;
}

/* ---------- SIGNAL QUALITY INDEX ---------- */

function computeSQI(filtered, ibi) {
    if (ibi.length < 5) return 0;

    const amp = Math.max(...filtered) - Math.min(...filtered);
    const rmssd = computeRMSSD(ibi);

    let score = 100;

    if (amp < 1.0) score -= 40;
    if (rmssd < 10) score -= 30;
    if (!checkStationarity(ibi)) score -= 30;

    return Math.max(0, score);
}

/* ---------- VISUALIZATION ---------- */

function drawWave(value) {
    ctxWave.clearRect(0,0,canvas.width,canvas.height);
    ctxWave.strokeStyle = '#00ff00';
    ctxWave.lineWidth = 2;
    ctxWave.beginPath();

    const y = 40 - value * 8;

    if (!drawWave.points)
        drawWave.points = new Array(100).fill(y);

    drawWave.points.push(y);
    drawWave.points.shift();

    for (let i = 0; i < drawWave.points.length; i++) {
        const x = i * (canvas.width / 100);
        if (i === 0) ctxWave.moveTo(x, drawWave.points[i]);
        else ctxWave.lineTo(x, drawWave.points[i]);
    }

    ctxWave.stroke();
}

/* ---------- SENSOR ---------- */

async function initSensor() {
    if (scanning) return;

    const statusText = document.getElementById('status-text');
    const video = document.getElementById('video');
    const btn = document.getElementById('camera-btn');

    try {
        signalBuffer = [];
        timeBuffer = [];

        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment" },
            audio: false
        });

        const track = stream.getVideoTracks()[0];
        const capabilities = track.getCapabilities();
        if (capabilities.torch)
            await track.applyConstraints({ advanced: [{ torch: true }] });

        video.srcObject = stream;
        btn.style.display = "none";
        scanning = true;

        const procCanvas = document.createElement('canvas');
        const procCtx = procCanvas.getContext('2d');
        procCanvas.width = 32;
        procCanvas.height = 32;

        const startTime = performance.now();
        const duration = 20000;

        function process() {
            if (!scanning) return;

            const elapsed = performance.now() - startTime;
            const remaining = Math.max(0, Math.ceil((duration - elapsed)/1000));

            procCtx.drawImage(video, 0, 0, 32, 32);
            const pixels = procCtx.getImageData(0,0,32,32).data;

            const avgGreen = robustGreenAverage(pixels);
            pushSignal(avgGreen);

            const filtered = bandpass(detrend(signalBuffer));
            drawWave(filtered[filtered.length - 1] || 0);

            if (elapsed < duration) {
                statusText.innerHTML = `💓 Scanning: ${remaining}s`;
                requestAnimationFrame(process);
            } else {
                scanning = false;
                track.stop();

                const filteredFinal = bandpass(detrend(signalBuffer));
                const peaks = detectPeaks(filteredFinal, timeBuffer);

                let ibi = computeIBI(peaks);
                ibi = validateIBI(ibi);
                ibi = correctArtifacts(ibi);

                const hr = computeHR(ibi);
                const rmssd = computeRMSSD(ibi);
                const sqi = computeSQI(filteredFinal, ibi);

                let quality = "rejected";
                if (sqi > 70) quality = "good";
                else if (sqi > 40) quality = "usable";

                statusText.innerHTML =
                    `✅ HR: ${hr.toFixed(0)} | RMSSD: ${rmssd.toFixed(1)} ms | SQI: ${sqi} (${quality})`;

                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: { hr: Math.round(hr), hrv: rmssd, sqi: sqi, quality: quality }
                }, '*');
            }
        }

        video.onplay = () => process();

    } catch (err) {
        statusText.innerHTML = "❌ Camera access required";
    }
}
</script>
        """,
        height=220,
    )
# --- INITIAL SETUP ---
st.set_page_config(page_title="Kubios HRV Readiness", layout="wide")

# --- DATA ENGINE ---
DB_FILE = "student_health_data.csv"

def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User_ID', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location', 'Weight', 'Sex'])

# --- LOGIN SYSTEM ---
if 'auth' not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None
    st.session_state.role = None

if not st.session_state.auth:
    st.title("🔐 Student Health Portal")
    with st.form("login"):
        u = st.text_input("Student ID / Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if u.lower() == "admin" and p == "ryan2026":
                st.session_state.auth, st.session_state.role, st.session_state.user = True, "admin", "Michael Ryan"
                st.rerun()
            elif u and p == "student123":
                st.session_state.auth, st.session_state.role, st.session_state.user = True, "student", u
                st.rerun()
            else: st.error("Access Denied.")
    st.stop()

# --- MAIN APP ---
df = load_data()

with st.sidebar:
    st.write(f"Logged in as: **{st.session_state.user}**")
    if st.button("Logout"):
        st.session_state.auth = False
        st.rerun()
    st.divider()
    
    if st.session_state.role == "student":
        st.header("🕒 Daily Measurement")
        hrv_sensor_component()
        # --- FEATURE PREVIEW: PPG FLASH SCAN ---
        st.info("💡 **PPG Flash Scan (Mock):** Based on research, place your finger over the camera and flash for a 60-second scan.")
          if st.button("🚀 Start Pulse Scan"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            chart_placeholder = st.empty()
            
            # Simulated 60s acquisition window (compressed for demo)
            for i in range(100):
                progress_bar.progress(i + 1)
                # Create a mock PPG wave visualization based on green channel processing
                mock_wave = np.sin(np.linspace(0, 5, 50) + i/5) + np.random.normal(0, 0.05, 50)
                chart_placeholder.line_chart(mock_wave)
                status_text.text(f"Acquiring PPG Signal... {i}%")
                time.sleep(0.04)
            
            # Simulate rMSSD calculation from beat-to-beat accuracy models
            st.session_state['detected_hr'] = np.random.randint(60, 85)
            st.session_state['detected_hrv'] = np.random.randint(45, 75)
       
            st.success("✅ Scan Complete! Validating RMSSD signal...")

        st.divider()

        # --- DATA ENTRY FORM ---
        with st.form("entry", clear_on_submit=True):
            # Form defaults to "detected" values from the scan above
            hr = st.number_input("Heart Rate (BPM)", 40, 160, st.session_state.get('detected_hr', 70))
            hrv = st.number_input("HRV (RMSSD ms)", 5, 250, st.session_state.get('detected_hrv', 50))
            
            st.write("---")
            st.write("🧘 **Anatomical Soreness Map** (The 'Dessert')")
            c1, c2 = st.columns(2)
            with c1:
                s1, s2, s3 = st.checkbox("Upper Back"), st.checkbox("Shoulders"), st.checkbox("Chest")
            with c2:
                s4, s5, s6 = st.checkbox("Quads"), st.checkbox("Hamstrings"), st.checkbox("Calves")
            
            s_val = st.select_slider("Intensity (1-10)", list(range(1, 11)), 1)
            
            with st.expander("Bio-Factors (Optional)"):
                weight = st.number_input("Weight (kg)", 30, 200, 70)
                sex = st.selectbox("Sex", ["Male", "Female", "Other"])

            if st.form_submit_button("Submit & Sync"):
                locs = [l for l, v in zip(["Upper Back", "Shoulders", "Chest", "Quads", "Hamstrings", "Calves"], [s1, s2, s3, s4, s5, s6]) if v]
                new = pd.DataFrame({'User_ID': [st.session_state.user], 'Timestamp': [datetime.now()], 'HR': [hr], 'RMSSD': [hrv], 
                                    'Soreness': [s_val], 'Location': [", ".join(locs) if locs else "None"], 'Weight': [weight], 'Sex': [sex]})
                df = pd.concat([df, new], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("Measurement Recorded!")
                st.rerun()

# --- DASHBOARD LOGIC ---
if st.session_state.role == "student":
    u_df = df[df['User_ID'] == st.session_state.user].copy()
    if not u_df.empty:
        # Scientific Baseline Logic (RMSSD focus as requested)
        baseline = u_df['RMSSD'].mean()
        std_v = u_df['RMSSD'].std() if len(u_df) > 1 else 10
        latest = u_df['RMSSD'].iloc[-1]
        z = (latest - baseline) / std_v if std_v != 0 else 0
        
        # Readiness Advice Logic
        if z > -0.5: st.success("🟢 **READY:** Optimal recovery. Baseline stable.")
        elif z > -1.5: st.warning("🟡 **CAUTION:** Moderate deviation. Consider active recovery.")
        else: st.error("🔴 **REST:** Large deviation detected. Significant cardiovascular strain.")

        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("Personal Gauge")
            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta", value=latest, delta={'reference': baseline},
                gauge={'axis': {'range': [0, 150]}, 'bar': {'color': "black", 'thickness': 0.2},
                       'steps': [{'range': [0, max(0, baseline - 1.5*std_v)], 'color': "#ff4b4b"},
                                 {'range': [max(0, baseline - 1.5*std_v), max(0, baseline - 0.5*std_v)], 'color': "#ffff00"},
                                 {'range': [max(0, baseline - 0.5*std_v), 150], 'color': "#00cc96"}],
                       'threshold': {'line': {'color': "black", 'width': 4}, 'value': baseline}}))
            st.plotly_chart(fig, use_container_width=True)
            
        with col2:
            st.subheader("Trends & Team Context")
            plot_df = u_df.tail(10).copy()
            plot_df['Personal_Baseline'] = baseline
            plot_df['Team_Avg'] = df['RMSSD'].mean()
            st.line_chart(plot_df.set_index('Timestamp')[['RMSSD', 'Personal_Baseline', 'Team_Avg']])
        
        st.divider()
        st.subheader("📋 Your Recent History")
        st.table(u_df[['Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location']].tail(5))
    else: 
        st.info("Welcome! Please perform a scan or enter your first reading to see your baseline.")

# --- ADMIN PANEL ---
elif st.session_state.role == "admin":
    st.title("👑 Coach Administration Panel")
    if not df.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Active Students", df['User_ID'].nunique())
        m2.metric("Group HR Avg", f"{int(df['HR'].mean())} BPM")
        m3.metric("Global Compliance", f"{len(df)} Logs")
        
        st.subheader("Team Readiness Leaderboard")
        leaderboard = df.sort_values('Timestamp', ascending=False)
        st.dataframe(leaderboard, use_container_width=True)
        st.download_button("Export Full Dataset (CSV)", df.to_csv(index=False), "ryan_readiness_export.csv", "text/csv")








