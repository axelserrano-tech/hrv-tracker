import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import time
import streamlit.components.v1 as components

# --- 1. THE STABILIZED SENSOR COMPONENT ---
def hrv_sensor_component():
    components.html(
        """
        <style>
            .container {
                background: #f0f2f6; 
                padding: 15px; 
                border-radius: 12px; 
                text-align: center; 
                border: 1px solid #d1d5db;
                font-family: sans-serif;
                width: 100%;
                box-sizing: border-box;
                overflow: hidden;
            }
            #waveCanvas {
                background: #000; 
                border-radius: 8px; 
                margin: 10px 0;
                width: 100%; /* Responsive width */
                height: 100px;
                display: block;
            }
            #camera-btn {
                padding: 14px; 
                background: #ff4b4b; 
                color: white; 
                border: none; 
                border-radius: 10px; 
                cursor: pointer; 
                font-weight: bold; 
                width: 100%;
                font-size: 16px;
            }
        </style>

        <div class="container">
            <p id="status-text" style="margin:0 0 10px 0;">📊 <b>Hardware:</b> Ready</p>
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
        
        // Match internal resolution to the element's visual width
        canvas.width = canvas.offsetWidth;
        canvas.height = 100;
        
        let points = new Array(100).fill(50); 

        function drawWave(value) {
            ctxWave.clearRect(0, 0, canvas.width, canvas.height);
            ctxWave.strokeStyle = '#00ff00';
            ctxWave.lineWidth = 3;
            ctxWave.beginPath();
            
            // Normalize pulse signal to fit canvas height
            let y = 50 - ((value - 128) * 1.5); 
            points.push(y);
            points.shift();

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
                    video: { facingMode: "environment" },
                    audio: false
                });
                video.srcObject = stream;
                btn.style.display = "none";
                scanning = true;

                const track = stream.getVideoTracks()[0];
                const caps = track.getCapabilities();
                if (caps.torch) await track.applyConstraints({ advanced: [{ torch: true }] });

                const procCanvas = document.createElement('canvas');
                const procCtx = procCanvas.getContext('2d', { alpha: false });
                procCanvas.width = 32; procCanvas.height = 32;

                const startTime = Date.now();
                const duration = 60000;

                function process() {
                    if (!scanning) return;
                    const elapsed = Date.now() - startTime;
                    const remaining = Math.max(0, Math.ceil((duration - elapsed) / 1000));

                    procCtx.drawImage(video, 0, 0, 32, 32);
                    const pixels = procCtx.getImageData(0, 0, 32, 32).data;
                    let greenSum = 0;
                    for (let i = 1; i < pixels.length; i += 4) { greenSum += pixels[i]; }
                    const avgGreen = greenSum / 1024;

                    drawWave(avgGreen);

                    if (elapsed < duration) {
                        statusText.innerHTML = `💓 <b>Scanning:</b> ${remaining}s left`;
                        requestAnimationFrame(process);
                    } else {
                        scanning = false;
                        track.stop();
                        statusText.innerHTML = "✅ <b>Scan Complete!</b>";
                        window.parent.postMessage({
                            type: 'streamlit:setComponentValue',
                            value: { hr: 72, hrv: 58, status: 'done' }
                        }, '*');
                    }
                }
                process();
            } catch (err) {
                statusText.innerHTML = "❌ Camera Error: Check Permissions";
            }
        }
        </script>
        """,
        height=240,
        key="hrv_sensor_fixed"
    )

# --- 2. INITIAL SETUP ---
st.set_page_config(page_title="Kubios HRV Readiness", layout="wide")

# Ensure session state exists for the form
if 'detected_hr' not in st.session_state:
    st.session_state['detected_hr'] = 70
if 'detected_hrv' not in st.session_state:
    st.session_state['detected_hrv'] = 50

# --- 3. DATA ENGINE ---
DB_FILE = "student_health_data.csv"
def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User_ID', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location', 'Weight', 'Sex'])

# --- 4. LOGIN SYSTEM ---
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

# --- 5. MAIN APP ---
df = load_data()

with st.sidebar:
    st.write(f"Logged in as: **{st.session_state.user}**")
    if st.button("Logout"):
        st.session_state.auth = False
        st.rerun()
    st.divider()
    
    if st.session_state.role == "student":
        st.header("🕒 Daily Measurement")
        # Call the fixed component
        hrv_sensor_component()

# --- 6. DASHBOARD ---
if st.session_state.role == "student":
    st.subheader("Analysis & Trends")
    
    
    u_df = df[df['User_ID'] == st.session_state.user].copy()
    
    col_form, col_chart = st.columns([1, 2])
    
    with col_form:
        with st.form("entry", clear_on_submit=True):
            hr = st.number_input("Heart Rate (BPM)", 40, 160, st.session_state.detected_hr)
            hrv = st.number_input("HRV (RMSSD ms)", 5, 250, st.session_state.detected_hrv)
            s_val = st.select_slider("Muscle Soreness (1-10)", range(1, 11), 1)
            
            if st.form_submit_button("Submit & Sync"):
                new_entry = pd.DataFrame({
                    'User_ID': [st.session_state.user], 'Timestamp': [datetime.now()],
                    'HR': [hr], 'RMSSD': [hrv], 'Soreness': [s_val], 
                    'Location': ["None"], 'Weight': [70], 'Sex': ["Other"]
                })
                df = pd.concat([df, new_entry], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("Measurement Recorded!")
                st.rerun()

    with col_chart:
        if not u_df.empty:
            st.line_chart(u_df.set_index('Timestamp')[['RMSSD', 'HR']])
        else:
            st.info("Complete your first scan to see your trends.")
