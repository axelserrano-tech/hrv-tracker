import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import time
import streamlit.components.v1 as components

# --- 1. INITIAL SETUP & STATE ---
st.set_page_config(page_title="Kubios HRV Readiness", layout="wide")

# Crucial: Initialize these so the form doesn't crash on the first run
if 'detected_hr' not in st.session_state:
    st.session_state['detected_hr'] = 70
if 'detected_hrv' not in st.session_state:
    st.session_state['detected_hrv'] = 50

# --- 2. THE HARDWARE BRIDGE ---
def hrv_sensor_component():
    return components.html(
        """
        <style>
            .container {
                background: #f0f2f6; padding: 15px; border-radius: 15px; 
                text-align: center; border: 1px solid #d1d5db; font-family: sans-serif;
            }
            #waveCanvas {
                background: #000; border-radius: 8px; margin: 10px 0; 
                width: 100%; height: 120px; display: block;
            }
            #camera-btn {
                padding: 14px; background: #ff4b4b; color: white; border: none; 
                border-radius: 10px; cursor: pointer; font-weight: bold; width: 100%; font-size: 16px;
            }
        </style>

        <div class="container">
            <p id="status-text" style="margin: 5px 0;">📊 <b>Hardware:</b> Ready</p>
            <canvas id="waveCanvas"></canvas>
            <video id="video" autoplay playsinline style="display:none;"></video>
            <button id="camera-btn" onclick="initSensor()">Enable Camera & Flash</button>
        </div>

        <script>
        let scanning = false;
        const canvas = document.getElementById('waveCanvas');
        const ctxWave = canvas.getContext('2d');
        canvas.width = 400; canvas.height = 120;
        let points = new Array(100).fill(60); 

        function drawWave(value) {
            ctxWave.clearRect(0, 0, canvas.width, canvas.height);
            ctxWave.strokeStyle = '#00ff00';
            ctxWave.lineWidth = 3;
            ctxWave.beginPath();
            let y = 60 - ((value - 128) * 2);
            points.push(y); points.shift();
            for (let i = 0; i < points.length; i++) {
                let x = i * (canvas.width / 100);
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
                    video: { facingMode: "environment" }, audio: false
                });
                video.srcObject = stream;
                btn.style.display = "none";
                scanning = true;

                const track = stream.getVideoTracks()[0];
                const capabilities = track.getCapabilities();
                if (capabilities.torch) await track.applyConstraints({ advanced: [{ torch: true }] });

                const procCanvas = document.createElement('canvas');
                const procCtx = procCanvas.getContext('2d', { alpha: false });
                procCanvas.width = 32; procCanvas.height = 32;

                const startTime = Date.now();
                const duration = 60000;
                let beatTimes = [];
                let lastValue = 0;
                let isPeak = false;

                function process() {
                    if (!scanning) return;
                    const now = Date.now();
                    const elapsed = now - startTime;
                    const remaining = Math.max(0, Math.ceil((duration - elapsed) / 1000));

                    procCtx.drawImage(video, 0, 0, 32, 32);
                    const pixels = procCtx.getImageData(0, 0, 32, 32).data;
                    let greenSum = 0;
                    for (let i = 1; i < pixels.length; i += 4) { greenSum += pixels[i]; }
                    const avgGreen = greenSum / 1024;

                    drawWave(avgGreen);

                    if (lastValue > 0 && avgGreen < lastValue && !isPeak && avgGreen < 140) {
                        beatTimes.push(now);
                        isPeak = true;
                    } else if (avgGreen > lastValue + 1) {
                        isPeak = false;
                    }
                    lastValue = avgGreen;

                    if (elapsed < duration) {
                        let currentBPM = beatTimes.length > 5 ? Math.round((beatTimes.length / (elapsed / 60000))) : "--";
                        statusText.innerHTML = `💓 <b>BPM:</b> ${currentBPM} | ⏱️ ${remaining}s`;
                        requestAnimationFrame(process);
                    } else {
                        scanning = false;
                        track.stop();
                        let rrIntervals = [];
                        for(let i = 1; i < beatTimes.length; i++) { rrIntervals.push(beatTimes[i] - beatTimes[i-1]); }
                        let diffs = [];
                        for(let i = 1; i < rrIntervals.length; i++) { diffs.push(Math.pow(rrIntervals[i] - rrIntervals[i-1], 2)); }
                        let calculatedRMSSD = Math.sqrt(diffs.reduce((a, b) => a + b, 0) / diffs.length) || 50;
                        let finalHR = Math.round((beatTimes.length / (duration / 60000)));

                        window.parent.postMessage({
                            type: 'streamlit:setComponentValue',
                            value: { hr: finalHR, hrv: Math.round(calculatedRMSSD) }
                        }, '*');
                        statusText.innerHTML = "✅ <b>Scan Complete!</b>";
                    }
                }
                process();
            } catch (e) { statusText.innerHTML = "❌ Error: Camera access denied."; }
        }
        </script>
        """,
        height=300,
        key="hrv_sensor_widget"
    )

# --- 3. DATA ENGINE ---
DB_FILE = "student_health_data.csv"

def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User_ID', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location', 'Weight', 'Sex'])

# --- 4. AUTH SYSTEM ---
if 'auth' not in st.session_state:
    st.session_state.update({'auth': False, 'user': None, 'role': None})

if not st.session_state.auth:
    st.title("🔐 Student Health Portal")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if u.lower() == "admin" and p == "ryan2026":
                st.session_state.update({'auth': True, 'role': 'admin', 'user': 'Michael Ryan'})
                st.rerun()
            elif u and p == "student123":
                st.session_state.update({'auth': True, 'role': 'student', 'user': u})
                st.rerun()
            else: st.error("Access Denied.")
    st.stop()

# --- 5. MAIN APP ---
df = load_data()

with st.sidebar:
    st.write(f"Logged in: **{st.session_state.user}**")
    if st.button("Logout"):
        st.session_state.auth = False
        st.rerun()
    st.divider()
    
    if st.session_state.role == "student":
        st.header("🕒 Daily Scan")
        # --- SAFE COMPONENT DATA RETRIEVAL ---
        sensor_data = hrv_sensor_component()
        if sensor_data is not None:
            st.session_state.detected_hr = sensor_data.get('hr', 70)
            st.session_state.detected_hrv = sensor_data.get('hrv', 50)
            st.success("✅ Hardware Data Synced!")

# --- 6. STUDENT DASHBOARD ---
if st.session_state.role == "student":
    u_df = df[df['User_ID'] == st.session_state.user].copy()
    
    col_input, col_viz = st.columns([1, 2])
    
    with col_input:
        st.subheader("Manual Entry / Confirm")
        with st.form("entry", clear_on_submit=True):
            hr = st.number_input("Heart Rate (BPM)", 40, 160, value=int(st.session_state.detected_hr))
            hrv = st.number_input("HRV (RMSSD ms)", 5, 250, value=int(st.session_state.detected_hrv))
            
            st.write("---")
            st.write("🧘 **Soreness Map**")
            s_map = [st.checkbox(l) for l in ["Back", "Shoulders", "Chest", "Quads", "Hams", "Calves"]]
            s_val = st.select_slider("Intensity", range(1, 11), 1)
            
            if st.form_submit_button("Submit Measurement"):
                locs = [l for l, v in zip(["Back", "Shoulders", "Chest", "Quads", "Hams", "Calves"], s_map) if v]
                new_row = pd.DataFrame({
                    'User_ID': [st.session_state.user], 'Timestamp': [datetime.now()],
                    'HR': [hr], 'RMSSD': [hrv], 'Soreness': [s_val], 
                    'Location': [", ".join(locs) if locs else "None"], 'Weight': [70], 'Sex': ["Other"]
                })
                df = pd.concat([df, new_row], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("Logged!")
                st.rerun()

    with col_viz:
        st.subheader("Recovery Analysis")
        if not u_df.empty:
            baseline = u_df['RMSSD'].mean()
            latest = u_df['RMSSD'].iloc[-1]
            
            
            
            st.metric("Latest HRV", f"{latest} ms", f"{round(latest-baseline, 1)} ms vs avg")
            
            # Simple Trend Chart
            st.line_chart(u_df.set_index('Timestamp')[['RMSSD', 'HR']])
        else:
            st.info("Perform your first scan to generate recovery data.")

# --- 7. ADMIN PANEL ---
elif st.session_state.role == "admin":
    st.title("👑 Coach Panel")
    st.dataframe(df.sort_values('Timestamp', ascending=False))
    st.download_button("Export CSV", df.to_csv(index=False), "data.csv")
