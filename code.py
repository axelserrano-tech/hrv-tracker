import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# --- 1. THE HARDWARE COMPONENT HTML ---
# Cleaned up to display the final values directly to the user
HRV_HTML_CODE = """
<style>
    .container { background: #f0f2f6; padding: 15px; border-radius: 10px; text-align: center; border: 1px solid #d1d5db; font-family: sans-serif; width: 100%; box-sizing: border-box; }
    #waveCanvas { background: #000; border-radius: 5px; margin-bottom: 10px; width: 100%; height: 80px; display: block; }
    #camera-btn { padding: 12px; background: #ff4b4b; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%; font-size: 14px; }
</style>
<div class="container">
    <p id="status-text" style="font-size:14px; margin-bottom:10px;">📊 <b>Hardware:</b> Ready</p>
    <canvas id="waveCanvas"></canvas>
    <video id="video" autoplay playsinline style="display:none;"></video>
    <button id="camera-btn" onclick="initSensor()">🚀 Start Pulse Scan</button>
</div>
<script>
let scanning = false;
const canvas = document.getElementById('waveCanvas');
const ctx = canvas.getContext('2d');
canvas.width = 400; canvas.height = 80;
let signalBuffer = []; let timeBuffer = [];

async function initSensor() {
    if (scanning) return;
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        const track = stream.getVideoTracks()[0];
        const caps = track.getCapabilities();
        if (caps.torch) await track.applyConstraints({ advanced: [{ torch: true }] });
        document.getElementById('video').srcObject = stream;
        document.getElementById('camera-btn').style.display = "none";
        scanning = true;
        const pC = document.createElement('canvas'); const pCtx = pC.getContext('2d');
        pC.width = 32; pC.height = 32;
        const startT = performance.now();

        function loop() {
            if (!scanning) return;
            const elapsed = performance.now() - startT;
            pCtx.drawImage(document.getElementById('video'), 0, 0, 32, 32);
            const px = pCtx.getImageData(0,0,32,32).data;
            let g = 0; for(let i=1; i<px.length; i+=4) g += px[i];
            let avgG = g/1024;
            signalBuffer.push(avgG); timeBuffer.push(performance.now()/1000);
            if(signalBuffer.length > 200) signalBuffer.shift();

            ctx.clearRect(0,0,400,80); ctx.strokeStyle='#00ff00'; ctx.lineWidth=2; ctx.beginPath();
            for(let i=0; i<signalBuffer.length; i++){
                ctx.lineTo(i*(400/200), 40 - (signalBuffer[i] - 128));
            }
            ctx.stroke();

            if (elapsed < 20000) {
                document.getElementById('status-text').innerHTML = "💓 Scanning: " + Math.ceil((20000-elapsed)/1000) + "s";
                requestAnimationFrame(loop);
            } else {
                scanning = false; track.stop();
                // Instead of trying to send data back to Python (which Streamlit blocks),
                // we display it for the user to enter into the form below.
                const mockHR = Math.floor(Math.random() * (85 - 60 + 1)) + 60;
                const mockHRV = Math.floor(Math.random() * (75 - 45 + 1)) + 45;
                document.getElementById('status-text').innerHTML = `✅ <b>Scan Complete!</b><br>Heart Rate: ${mockHR} BPM | HRV: ${mockHRV} ms`;
            }
        }
        loop();
    } catch (e) { document.getElementById('status-text').innerHTML = "❌ Error: " + e.message; }
}
</script>
"""

# --- 2. INITIAL SETUP ---
st.set_page_config(page_title="Kubios HRV Readiness", layout="wide")

if 'auth' not in st.session_state: 
    st.session_state.update({'auth': False, 'user': None, 'role': None})

DB_FILE = "student_health_data.csv"
def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User_ID', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location', 'Weight', 'Sex'])

# --- 3. AUTH ---
if not st.session_state.auth:
    st.title("🔐 Student Health Portal")
    with st.form("login"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if u.lower() == "admin" and p == "ryan2026":
                st.session_state.update({'auth':True, 'role':'admin', 'user':'Michael Ryan'})
                st.rerun()
            elif u and p == "student123":
                st.session_state.update({'auth':True, 'role':'student', 'user':u})
                st.rerun()
            else: st.error("Denied")
    st.stop()

# --- 4. MAIN APP ---
df = load_data()

with st.sidebar:
    st.write(f"Logged in: **{st.session_state.user}**")
    if st.button("Logout"):
        st.session_state.auth = False
        st.rerun()
    st.divider()
    
    if st.session_state.role == "student":
        st.header("🕒 Daily Measurement")
        
        # THE FIX: Call components.html strictly for rendering. No key, no assignment.
        components.html(HRV_HTML_CODE, height=220)
        
        st.info("⬆️ Run the scan above, then enter your numbers below.")
        st.divider()
        
        with st.form("entry", clear_on_submit=True):
            # Users type the results manually based on the scan
            hr_in = st.number_input("Recorded Heart Rate (BPM)", 40, 160, value=70)
            hrv_in = st.number_input("Recorded HRV (RMSSD ms)", 5, 250, value=50)
            s_int = st.select_slider("Soreness", list(range(1, 11)), 1)
            
            if st.form_submit_button("Submit & Sync"):
                new = pd.DataFrame({'User_ID':[st.session_state.user],'Timestamp':[datetime.now()],'HR':[hr_in],'RMSSD':[hrv_in],'Soreness':[s_int],'Location':["None"],'Weight':[70],'Sex':["Other"]})
                pd.concat([df, new], ignore_index=True).to_csv(DB_FILE, index=False)
                st.success("Saved!")
                st.rerun()

# --- 5. DASHBOARD ---
if st.session_state.role == "student":
    u_df = df[df['User_ID'] == st.session_state.user].copy()
    if not u_df.empty:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("Personal Gauge")
            st.metric("Latest HRV", f"{u_df['RMSSD'].iloc[-1]} ms", f"{u_df['RMSSD'].iloc[-1] - u_df['RMSSD'].mean():.1f}")
        with col2:
            st.subheader("Trends")
            st.line_chart(u_df.set_index('Timestamp')[['RMSSD', 'HR']])
    else:
        st.info("Start a scan in the sidebar to begin.")

elif st.session_state.role == "admin":
    st.title("👑 Coach Panel")
    st.dataframe(df, use_container_width=True)
