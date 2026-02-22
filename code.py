import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import time
import streamlit.components.v1 as components

# This function creates the "Bridge"
def hrv_sensor_component():
    return components.html(
        """
        <style>
            .container {
                background: #f0f2f6; padding: 10px; border-radius: 15px; 
                text-align: center; border: 1px solid #d1d5db; font-family: sans-serif;
                width: 100%; box-sizing: border-box;
            }
            #waveCanvas {
                background: #000; border-radius: 8px; margin: 10px 0; 
                width: 100%; height: 140px; display: block;
            }
            #quality-box { width: 100%; height: 8px; background: #ddd; border-radius: 4px; margin: 5px 0; overflow: hidden; }
            #quality-bar { width: 0%; height: 100%; background: #ff4b4b; transition: 0.3s; }
            #camera-btn { padding: 14px; background: #ff4b4b; color: white; border: none; border-radius: 10px; cursor: pointer; font-weight: bold; width: 100%; font-size: 16px; }
        </style>

        <div class="container">
            <p id="status-text" style="margin: 5px 0; font-size: 14px;">📡 <b>Status:</b> Calibrating for Accuracy</p>
            <div id="quality-box"><div id="quality-bar"></div></div>
            <canvas id="waveCanvas"></canvas>
            <video id="video" autoplay playsinline style="display:none;"></video>
            <button id="camera-btn" onclick="initSensor()">Initiate Precision Scan</button>
        </div>

        <script>
        let scanning = false;
        const canvas = document.getElementById('waveCanvas');
        const ctxWave = canvas.getContext('2d');
        const qBar = document.getElementById('quality-bar');
        
        function resize() {
            canvas.width = canvas.clientWidth;
            canvas.height = 140;
        }
        window.addEventListener('resize', resize);
        resize();

        let points = new Array(100).fill(70); 

        function drawWave(zScore) {
            ctxWave.clearRect(0, 0, canvas.width, canvas.height);
            ctxWave.strokeStyle = '#00ff00';
            ctxWave.lineWidth = 3;
            ctxWave.lineJoin = 'round';
            ctxWave.beginPath();
            
            let y = 70 - (zScore * 30); 
            y = Math.max(10, Math.min(130, y));
            points.push(y);
            points.shift();

            for (let i = 0; i < points.length; i++) {
                let x = i * (canvas.width / 99);
                if (i === 0) ctxWave.moveTo(x, points[i]);
                else ctxWave.lineTo(x, points[i]);
            }
            ctxWave.stroke();
        }

        async function initSensor() {
            if (scanning) return;
            const statusText = document.getElementById('status-text');
            const video = document.getElementById('video');
            const btn = document.getElementById('camera-btn');

            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: "environment", width: { ideal: 160 } },
                    audio: false
                });
                video.srcObject = stream;
                btn.style.display = "none";
                scanning = true;

                const track = stream.getVideoTracks()[0];
                const capabilities = track.getCapabilities();
                if (capabilities.torch) await track.applyConstraints({ advanced: [{ torch: true }] });

                const procCanvas = document.createElement('canvas');
                const procCtx = procCanvas.getContext('2d');
                procCanvas.width = 20; procCanvas.height = 20;

                const startTime = Date.now();
                let beatTimes = []; 
                let smoothedValue = 0;
                let rollingMean = 0;
                let rollingSTD = 0;
                let isPeak = false;

                function process() {
                    if (!scanning) return;
                    const now = Date.now();
                    const elapsed = now - startTime;

                    procCtx.drawImage(video, 0, 0, 20, 20);
                    const pixels = procCtx.getImageData(0, 0, 20, 20).data;
                    let greenSum = 0;
                    for (let i = 1; i < pixels.length; i += 4) { greenSum += pixels[i]; }
                    const avgGreen = greenSum / 400;

                    // EMA Filters for extreme denoising
                    smoothedValue = (0.12 * avgGreen) + (0.88 * smoothedValue);
                    rollingMean = (0.01 * smoothedValue) + (0.99 * rollingMean);
                    let diff = smoothedValue - rollingMean;
                    rollingSTD = (0.01 * Math.abs(diff)) + (0.99 * rollingSTD);
                    
                    // Normalization
                    let zScore = rollingSTD > 0.05 ? (diff / rollingSTD) : 0;
                    drawWave(zScore);

                    // Signal Quality Index (SQI)
                    let quality = Math.min(100, (rollingSTD * 800));
                    qBar.style.width = quality + "%";
                    qBar.style.background = quality > 60 ? "#00ff00" : (quality > 30 ? "#ffcc00" : "#ff4b4b");

                    if (elapsed > 5000) {
                        // Advanced Peak Detection: Looks for the rapid upward swing of blood volume
                        if (zScore < -1.4 && !isPeak) {
                            let ibi = now - beatTimes[beatTimes.length - 1];
                            // PHYSIOLOGICAL GATE: Rejects anything outside 40-180 BPM
                            if (!beatTimes.length || (ibi > 333 && ibi < 1500)) {
                                beatTimes.push(now);
                                isPeak = true;
                            }
                        } else if (zScore > 0.7) {
                            isPeak = false;
                        }

                        let bpm = "--";
                        if (beatTimes.length >= 5) {
                            // Calculates BPM based on the median of the last 5 intervals (Outlier Rejection)
                            let intervals = [];
                            for(let i=1; i<beatTimes.slice(-6).length; i++) {
                                intervals.push(beatTimes[beatTimes.length-i] - beatTimes[beatTimes.length-i-1]);
                            }
                            intervals.sort((a, b) => a - b);
                            let medianIBI = intervals[Math.floor(intervals.length / 2)];
                            bpm = Math.round(60000 / medianIBI);
                        }
                        
                        statusText.innerHTML = `💓 <b>Verified BPM:</b> ${bpm} | ⏱️ ${Math.max(0, Math.ceil((65000-elapsed)/1000))}s`;
                    }

                    if (elapsed < 65000) {
                        requestAnimationFrame(process);
                    } else {
                        scanning = false; track.stop();
                        window.parent.postMessage({
                            type: 'streamlit:setComponentValue',
                            value: { hr: bpm, status: 'complete' }
                        }, '*');
                    }
                }
                video.onplay = () => { smoothedValue = 150; rollingMean = 150; process(); };
            } catch (err) { statusText.innerHTML = "❌ Error: Permission Denied"; }
        }
        </script>
        """,
        height=420,
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












