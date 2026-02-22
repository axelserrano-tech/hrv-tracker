import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import time
import streamlit.components.v1 as components

# --- 1. THE HARDWARE COMPONENT (Bridge) ---
def hrv_sensor_component():
    # This component returns values to Streamlit via window.parent.postMessage
    val = components.html(
        """
        <style>
            .container {
                background: #f0f2f6; 
                padding: 15px; 
                border-radius: 10px; 
                text-align: center; 
                border: 1px solid #d1d5db;
                font-family: sans-serif;
                width: 100%;
                box-sizing: border-box;
                overflow: hidden;
            }
            #waveCanvas {
                background: #000; 
                border-radius: 5px; 
                margin-bottom: 10px;
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
        </style>

        <div class="container">
            <p id="status-text" style="font-size:14px; margin-bottom:10px;">📊 <b>Hardware:</b> Ready</p>
            <canvas id="waveCanvas"></canvas>
            <video id="video" autoplay playsinline style="display:none;"></video>
            <button id="camera-btn" onclick="initSensor()">
                🚀 Start Pulse Scan
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

        function robustGreenAverage(pixels) {
            let greens = [];
            for (let i = 1; i < pixels.length; i += 4) greens.push(pixels[i]);
            greens.sort((a,b)=>a-b);
            const trim = Math.floor(greens.length * 0.1);
            const trimmed = greens.slice(trim, greens.length - trim);
            return trimmed.reduce((a,b)=>a+b,0) / trimmed.length;
        }

        function detrend(signal) {
            const mean = signal.reduce((a,b)=>a+b,0) / signal.length;
            return signal.map(v => v - mean);
        }

        function bandpass(signal) {
            let out = []; let prev = 0;
            for (let i = 1; i < signal.length; i++) {
                let hp = signal[i] - signal[i-1];
                let lp = prev + 0.2 * (hp - prev);
                out.push(lp); prev = lp;
            }
            return out;
        }

        function detectPeaks(signal, times) {
            let peaks = [];
            if (signal.length < 10) return peaks;
            const mean = signal.reduce((a,b)=>a+b,0) / signal.length;
            const std = Math.sqrt(signal.map(x => (x-mean)**2).reduce((a,b)=>a+b,0) / signal.length);
            const threshold = mean + 0.8 * std;
            for (let i = 1; i < signal.length - 1; i++) {
                if (signal[i] > threshold && signal[i] > signal[i-1] && signal[i] > signal[i+1]) {
                    if (!peaks.length || (times[i] - peaks[peaks.length-1]) > 0.35) peaks.push(times[i]);
                }
            }
            return peaks;
        }

        async function initSensor() {
            if (scanning) return;
            const statusText = document.getElementById('status-text');
            const video = document.getElementById('video');
            const btn = document.getElementById('camera-btn');

            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
                const track = stream.getVideoTracks()[0];
                const caps = track.getCapabilities();
                if (caps.torch) await track.applyConstraints({ advanced: [{ torch: true }] });

                video.srcObject = stream;
                btn.style.display = "none";
                scanning = true;

                const pC = document.createElement('canvas'); const pCtx = pC.getContext('2d');
                pC.width = 32; pC.height = 32;
                const startT = performance.now();

                function loop() {
                    if (!scanning) return;
                    const elapsed = performance.now() - startT;
                    pCtx.drawImage(video, 0, 0, 32, 32);
                    const avgG = robustGreenAverage(pCtx.getImageData(0,0,32,32).data);
                    
                    signalBuffer.push(avgG);
                    timeBuffer.push(performance.now()/1000);
                    if(signalBuffer.length > 400) { signalBuffer.shift(); timeBuffer.shift(); }

                    const filt = bandpass(detrend(signalBuffer));
                    const latestFilt = filt[filt.length-1] || 0;
                    
                    // Draw Wave
                    ctxWave.clearRect(0,0,canvas.width,canvas.height);
                    ctxWave.strokeStyle = '#00ff00'; ctxWave.lineWidth = 2; ctxWave.beginPath();
                    if(!window.pts) window.pts = new Array(100).fill(40);
                    window.pts.push(40 - latestFilt * 8); window.pts.shift();
                    for(let i=0; i<100; i++) {
                        let x = i * (canvas.width/100);
                        if(i==0) ctxWave.moveTo(x, window.pts[i]); else ctxWave.lineTo(x, window.pts[i]);
                    }
                    ctxWave.stroke();

                    if (elapsed < 20000) {
                        statusText.innerHTML = "💓 Scanning: " + Math.ceil((20000-elapsed)/1000) + "s";
                        requestAnimationFrame(loop);
                    } else {
                        scanning = false; track.stop();
                        const finalFilt = bandpass(detrend(signalBuffer));
                        const peaks = detectPeaks(finalFilt, timeBuffer);
                        let ibis = []; for(let i=1; i<peaks.length; i++) ibis.push(peaks[i]-peaks[i-1]);
                        
                        const hr = 60 / (ibis.reduce((a,b)=>a+b,0)/ibis.length);
                        let diffs = []; for(let i=1; i<ibis.length; i++) diffs.push(Math.pow(ibis[i]-ibis[i-1], 2));
                        const rmssd = Math.sqrt(diffs.reduce((a,b)=>a+b,0)/diffs.length) * 1000;

                        statusText.innerHTML = "✅ Scan Complete!";
                        window.parent.postMessage({
                            type: 'streamlit:setComponentValue',
                            value: { hr: Math.round(hr), hrv: Math.round(rmssd) }
                        }, '*');
                    }
                }
                loop();
            } catch (e) { statusText.innerHTML = "❌ Error: " + e.message; }
        }
        </script>
        """,
        height=220,
        key="ppg_sensor"
    )
    return val

# --- 2. INITIAL SETUP ---
st.set_page_config(page_title="Kubios HRV Readiness", layout="wide")

DB_FILE = "student_health_data.csv"
def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User_ID', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location', 'Weight', 'Sex'])

# --- 3. LOGIN ---
if 'auth' not in st.session_state:
    st.session_state.update({'auth': False, 'user': None, 'role': None})

if not st.session_state.auth:
    st.title("🔐 Student Health Portal")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if u.lower() == "admin" and p == "ryan2026":
                st.session_state.update({'auth':True, 'role':'admin', 'user':'Michael Ryan'})
                st.rerun()
            elif u and p == "student123":
                st.session_state.update({'auth':True, 'role':'student', 'user':u})
                st.rerun()
            else: st.error("Access Denied.")
    st.stop()

# --- 4. MAIN APP ---
df = load_data()

with st.sidebar:
    st.write(f"Logged in as: **{st.session_state.user}**")
    if st.button("Logout"):
        st.session_state.auth = False
        st.rerun()
    st.divider()
    
    if st.session_state.role == "student":
        st.header("🕒 Daily Measurement")
        
        # --- THE LIVE PPG SENSOR ---
        # This now replaces the "Mock" button.
        scan_data = hrv_sensor_component()
        
        if scan_data:
            st.session_state['detected_hr'] = scan_data.get('hr', 70)
            st.session_state['detected_hrv'] = scan_data.get('hrv', 50)
            st.toast("Pulse Detected! Form updated below.")

        st.divider()

        # --- DATA ENTRY FORM ---
        with st.form("entry", clear_on_submit=True):
            hr_val = st.number_input("Heart Rate (BPM)", 40, 160, st.session_state.get('detected_hr', 70))
            hrv_val = st.number_input("HRV (RMSSD ms)", 5, 250, st.session_state.get('detected_hrv', 50))
            
            st.write("🧘 **Anatomical Soreness Map**")
            c1, c2 = st.columns(2)
            with c1:
                s1, s2, s3 = st.checkbox("Upper Back"), st.checkbox("Shoulders"), st.checkbox("Chest")
            with c2:
                s4, s5, s6 = st.checkbox("Quads"), st.checkbox("Hamstrings"), st.checkbox("Calves")
            
            s_int = st.select_slider("Intensity (1-10)", list(range(1, 11)), 1)
            
            if st.form_submit_button("Submit & Sync"):
                locs = [l for l, v in zip(["Upper Back", "Shoulders", "Chest", "Quads", "Hamstrings", "Calves"], [s1, s2, s3, s4, s5, s6]) if v]
                new = pd.DataFrame({'User_ID': [st.session_state.user], 'Timestamp': [datetime.now()], 'HR': [hr_val], 'RMSSD': [hrv_val], 
                                    'Soreness': [s_int], 'Location': [", ".join(locs) if locs else "None"], 'Weight': [70], 'Sex': ["Other"]})
                df = pd.concat([df, new], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("Measurement Recorded!")
                st.rerun()

# --- DASHBOARD ---
if st.session_state.role == "student":
    u_df = df[df['User_ID'] == st.session_state.user].copy()
    if not u_df.empty:
        baseline = u_df['RMSSD'].mean()
        latest = u_df['RMSSD'].iloc[-1]
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("Personal Gauge")
            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta", value=latest, delta={'reference': baseline},
                gauge={'axis': {'range': [0, 150]}, 'bar': {'color': "black", 'thickness': 0.2}}))
            st.plotly_chart(fig, use_container_width=True)
            
        with col2:
            st.subheader("Heart Rate & HRV Trends")
            # We show both HR and HRV on the trend chart as requested
            st.line_chart(u_df.set_index('Timestamp')[['RMSSD', 'HR']])
        
        st.table(u_df[['Timestamp', 'HR', 'RMSSD', 'Soreness']].tail(5))
    else: 
        st.info("Perform a scan in the sidebar to begin.")

elif st.session_state.role == "admin":
    st.title("👑 Coach Panel")
    st.dataframe(df, use_container_width=True)
