import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# --- 1. SETTINGS & STATE ---
st.set_page_config(page_title="HRV Training Pro", layout="wide")

# Persistent storage for session data
if 'hr' not in st.session_state: st.session_state.hr = 0
if 'hrv' not in st.session_state: st.session_state.hrv = 0
if 'last_update' not in st.session_state: st.session_state.last_update = None

DB_FILE = "athlete_data_log.csv"

def load_db():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User', 'Timestamp', 'HR', 'HRV', 'Soreness', 'Weight', 'Sex'])

# --- 2. THE OPTICAL PPG ENGINE (JavaScript) ---
# This script analyzes the GREEN channel (highest pulse contrast)
PPG_ENGINE_HTML = """
<div style="background: #111; color: white; padding: 20px; border-radius: 15px; text-align: center; font-family: sans-serif; border: 2px solid #444;">
    <h3 id="status" style="margin:0; color: #ff4b4b;">Sensor Offline</h3>
    <div id="heart-ui" style="font-size: 60px; margin: 20px 0; transition: transform 0.1s ease;">❤️</div>
    <div id="bpm-live" style="font-size: 28px; font-weight: bold; color: #00ff00;">-- BPM</div>
    
    <video id="v" width="10" height="10" style="position:absolute; opacity:0;" autoplay playsinline></video>
    <button id="start-btn" onclick="initSensor()" style="width:100%; padding:15px; background:#ff4b4b; color:white; border:none; border-radius:8px; font-weight:bold; cursor:pointer;">START 60s MEASUREMENT</button>
</div>

<script>
let samples = [], times = [], isScanning = false;

async function initSensor() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'environment'}});
        const v = document.getElementById('v');
        v.srcObject = stream;
        
        const track = stream.getVideoTracks()[0];
        try { await track.applyConstraints({advanced: [{torch: true}]}); } catch(e) {}

        document.getElementById('start-btn').style.display = 'none';
        document.getElementById('status').innerText = "🔴 ANALYZING PULSE...";
        isScanning = true;
        const startT = Date.now();

        // High-speed sampling (30fps)
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d', {alpha: false});
        canvas.width = 10; canvas.height = 10;

        const process = () => {
            if(!isScanning) return;
            ctx.drawImage(v, 0, 0, 10, 10);
            const pixels = ctx.getImageData(0,0,10,10).data;
            
            // PPG logic: Blood absorbs Green light
            let greenSum = 0;
            for(let i=1; i<pixels.length; i+=4) greenSum += pixels[i];
            
            const now = Date.now();
            samples.push(greenSum/100);
            times.push(now);

            // Pulse animation based on signal dips
            if(samples.length > 2 && samples[samples.length-1] < samples[samples.length-2]) {
                document.getElementById('heart-ui').style.transform = 'scale(1.2)';
                setTimeout(() => { document.getElementById('heart-ui').style.transform = 'scale(1)'; }, 100);
            }

            if(now - startT < 60000) {
                document.getElementById('bpm-live').innerText = Math.round((now-startT)/1000) + "s / 60s";
                requestAnimationFrame(process);
            } else {
                isScanning = false;
                track.stop();
                calculateResults();
            }
        };
        process();
    } catch(e) { alert("Camera error. Ensure HTTPS and permissions."); }
}

function calculateResults() {
    // Replica RMSSD Algorithm
    // Detects local minima (systolic peaks in PPG)
    let peaks = [];
    for(let i=2; i<samples.length-2; i++) {
        if(samples[i] < samples[i-1] && samples[i] < samples[i+1]) {
            peaks.push(times[i]);
        }
    }
    
    let rrIntervals = [];
    for(let i=1; i<peaks.length; i++) {
        let diff = peaks[i] - peaks[i-1];
        if(diff > 400 && diff < 1500) rrIntervals.push(diff);
    }

    const avgRR = rrIntervals.reduce((a,b)=>a+b, 0) / rrIntervals.length;
    const finalHR = Math.round(60000 / avgRR);

    let sumSqDiff = 0;
    for(let i=1; i<rrIntervals.length; i++) {
        sumSqDiff += Math.pow(rrIntervals[i] - rrIntervals[i-1], 2);
    }
    const finalRMSSD = Math.round(Math.sqrt(sumSqDiff / (rrIntervals.length - 1)));

    // SEND DATA TO PYTHON
    window.parent.postMessage({
        type: 'streamlit:setComponentValue',
        value: {hr: finalHR, hrv: finalRMSSD, ts: Date.now()}
    }, '*');
    
    document.getElementById('status').innerText = "✅ DATA SYNCED";
    document.getElementById('bpm-live').innerText = finalHR + " BPM";
}
</script>
"""

# --- 3. DASHBOARD LOGIC ---
df = load_db()

st.title("🏆 Kubios HRV Athlete Portal")
st.markdown("---")

col_left, col_right = st.columns([1, 1.3])

with col_left:
    st.subheader("1. Pulse Scan")
    # This captures the JSON from the JS "postMessage"
    capture_data = components.html(PPG_ENGINE_HTML, height=320)
    
    # Update logic: Only trigger if the timestamp (ts) has changed
    if capture_data and 'ts' in capture_data:
        if capture_data['ts'] != st.session_state.last_update:
            st.session_state.hr = capture_data['hr']
            st.session_state.hrv = capture_data['hrv']
            st.session_state.last_update = capture_data['ts']
            st.rerun()

with col_right:
    st.subheader("2. Readiness Entry")
    with st.form("readiness_form"):
        # Forms use the Session State updated by the camera
        c1, c2 = st.columns(2)
        hr_val = c1.number_input("Recorded HR (BPM)", value=int(st.session_state.hr))
        hrv_val = c2.number_input("Recorded HRV (RMSSD)", value=int(st.session_state.hrv))
        
        soreness = st.select_slider("Muscle Soreness (1-10)", options=range(1, 11))
        
        
        
        st.write("**Subjective Bio-factors**")
        weight = st.number_input("Weight (kg)", 40, 150, 75)
        sex = st.selectbox("Sex", ["Male", "Female"])
        
        if st.form_submit_button("Submit to Dashboard"):
            new_entry = pd.DataFrame([[st.session_state.user or "User_1", datetime.now(), hr_val, hrv_val, soreness, weight, sex]], columns=df.columns)
            pd.concat([df, new_entry]).to_csv(DB_FILE, index=False)
            st.success("Entry Saved! Baseline updated.")
            st.rerun()

# --- 4. THE KUBIOS GAUGE & TRENDS ---
st.divider()

if len(df) >= 3:
    st.header("📈 Readiness Analytics")
    
    # 7-day rolling window
    user_df = df.tail(7)
    latest_hrv = user_df['HRV'].iloc[-1]
    baseline_hrv = user_df['HRV'].mean()
    std_hrv = user_df['HRV'].std() if len(user_df) > 1 else 5

    g_col, t_col = st.columns([1, 2])
    
    with g_col:
        st.subheader("Kubios Readiness Gauge")
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = latest_hrv,
            gauge = {
                'axis': {'range': [20, 120]},
                'bar': {'color': "black"},
                'steps': [
                    {'range': [0, baseline_hrv - std_hrv], 'color': "#ff4b4b"}, # Red
                    {'range': [baseline_hrv - std_hrv, baseline_hrv - (0.5*std_hrv)], 'color': "#ffea00"}, # Yellow
                    {'range': [baseline_hrv - (0.5*std_hrv), 120], 'color': "#00cc96"} # Green
                ],
                'threshold': {'line': {'color': "black", 'width': 4}, 'value': baseline_hrv}
            }
        ))
        st.plotly_chart(fig, use_container_width=True)
        
    with t_col:
        st.subheader("7-Day Trend View")
        st.line_chart(user_df.set_index('Timestamp')[['HRV', 'HR']])
else:
    st.info("📊 Collecting data... Once you submit 3 measurements, your personal baseline gauge will appear.")
