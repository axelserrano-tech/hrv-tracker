import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import time
import streamlit.components.v1 as components

# --- 1. THE REFINED HTML/JS (Cleaned for Python 3.13 Compatibility) ---
HRV_HTML_CONTENT = """
<div style="background: #f0f2f6; padding: 15px; border-radius: 15px; text-align: center; border: 1px solid #d1d5db; font-family: sans-serif;">
    <p id="status-text" style="margin: 5px 0;">📊 <b>Hardware:</b> Ready</p>
    <canvas id="waveCanvas" style="background: #000; border-radius: 8px; margin: 10px 0; width: 100%; height: 120px; display: block;"></canvas>
    <video id="video" autoplay playsinline style="display:none;"></video>
    <button id="camera-btn" style="padding: 14px; background: #ff4b4b; color: white; border: none; border-radius: 10px; cursor: pointer; font-weight: bold; width: 100%; font-size: 16px;" onclick="initSensor()">Enable Camera & Flash</button>
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
        const stream = await navigator.mediaDevices.getUserMedia({video: { facingMode: "environment" }, audio: false});
        video.srcObject = stream;
        btn.style.display = "none";
        scanning = true;
        const track = stream.getVideoTracks()[0];
        const caps = track.getCapabilities();
        if (caps.torch) await track.applyConstraints({ advanced: [{ torch: true }] });
        const pC = document.createElement('canvas');
        const pCtx = pC.getContext('2d', { alpha: false });
        pC.width = 32; pC.height = 32;
        const start = Date.now();
        const duration = 60000;
        let beats = [];
        let lastVal = 0;
        let isPeak = false;

        function process() {
            if (!scanning) return;
            const now = Date.now();
            const elapsed = now - start;
            if (elapsed < duration) {
                pCtx.drawImage(video, 0, 0, 32, 32);
                const px = pCtx.getImageData(0, 0, 32, 32).data;
                let gSum = 0;
                for (let i = 1; i < px.length; i += 4) gSum += px[i];
                const avgG = gSum / 1024;
                drawWave(avgG);
                if (lastVal > 0 && avgG < lastVal && !isPeak && avgG < 140) {
                    beats.push(now);
                    isPeak = true;
                } else if (avgG > lastVal + 1) { isPeak = false; }
                lastVal = avgG;
                statusText.innerHTML = `💓 <b>BPM:</b> ${beats.length > 5 ? Math.round(beats.length / (elapsed/60000)) : "--"} | ⏱️ ${Math.ceil((duration-elapsed)/1000)}s`;
                requestAnimationFrame(process);
            } else {
                scanning = false; track.stop();
                let rr = [];
                for(let i=1; i<beats.length; i++) rr.push(beats[i]-beats[i-1]);
                let diffs = [];
                for(let i=1; i<rr.length; i++) diffs.push(Math.pow(rr[i]-rr[i-1], 2));
                let rmssd = Math.sqrt(diffs.reduce((a,b)=>a+b,0)/diffs.length) || 50;
                window.parent.postMessage({type: 'streamlit:setComponentValue', value: {hr: Math.round(beats.length), hrv: Math.round(rmssd)}}, '*');
                statusText.innerHTML = "✅ <b>Scan Complete!</b>";
            }
        }
        process();
    } catch (e) { statusText.innerHTML = "❌ Camera Error"; }
}
</script>
"""

# --- 2. INITIAL SETUP ---
st.set_page_config(page_title="Kubios HRV Readiness", layout="wide")

if 'detected_hr' not in st.session_state:
    st.session_state['detected_hr'] = 70
if 'detected_hrv' not in st.session_state:
    st.session_state['detected_hrv'] = 50
if 'auth' not in st.session_state:
    st.session_state.update({'auth': False, 'user': None, 'role': None})

# --- 3. DATA ENGINE ---
DB_FILE = "student_health_data.csv"
def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User_ID', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location', 'Weight', 'Sex'])

# --- 4. LOGIN ---
if not st.session_state.auth:
    st.title("🔐 Student Health Portal")
    with st.form("login"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
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
        # RENDER COMPONENT
        res = components.html(HRV_HTML_CONTENT, height=300, key="hrv_fixed_widget")
        if res is not None:
            st.session_state.detected_hr = res.get('hr', 70)
            st.session_state.detected_hrv = res.get('hrv', 50)
            st.toast("Hardware Data Synced!")

if st.session_state.role == "student":
    u_df = df[df['User_ID'] == st.session_state.user].copy()
    col_input, col_viz = st.columns([1, 2])
    
    with col_input:
        st.subheader("Confirm Entry")
        with st.form("entry", clear_on_submit=True):
            hr = st.number_input("Heart Rate (BPM)", 40, 160, value=int(st.session_state.detected_hr))
            hrv = st.number_input("HRV (RMSSD ms)", 5, 250, value=int(st.session_state.detected_hrv))
            s_val = st.select_slider("Muscle Soreness", range(1, 11), 1)
            if st.form_submit_button("Submit"):
                new_row = pd.DataFrame({'User_ID':[st.session_state.user],'Timestamp':[datetime.now()],'HR':[hr],'RMSSD':[hrv],'Soreness':[s_val],'Location':["None"],'Weight':[70],'Sex':["Other"]})
                df = pd.concat([df, new_row], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("Logged!")
                st.rerun()

    with col_viz:
        st.subheader("Readiness Analysis")
        
        if not u_df.empty:
            st.metric("Latest RMSSD", f"{u_df['RMSSD'].iloc[-1]} ms", f"{round(u_df['RMSSD'].iloc[-1]-u_df['RMSSD'].mean(), 1)} vs avg")
            st.line_chart(u_df.set_index('Timestamp')[['RMSSD']])
        else:
            st.info("Perform a scan to generate your recovery baseline.")

elif st.session_state.role == "admin":
    st.title("👑 Coach Panel")
    st.dataframe(df.sort_values('Timestamp', ascending=False))
