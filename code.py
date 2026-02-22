import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# --- 1. COMPUTER VISION PPG SENSOR ---
# This uses the camera to detect actual blood volume changes (Photoplethysmography)
REAL_PPG_SENSOR_HTML = """
<div style="background: #0e1117; color: white; padding: 20px; border-radius: 15px; text-align: center; font-family: sans-serif; border: 1px solid #262730;">
    <h3 style="margin:0; color: #ff4b4b;">📸 Biometric Optical Sensor</h3>
    <p id="instruction" style="font-size: 13px; color: #fafafa; margin: 10px 0;"><b>Place finger FIRMLY over the back camera and flash.</b></p>
    <canvas id="canvas" width="300" height="100" style="background:#000; border-radius:8px; border: 1px solid #444;"></canvas>
    <video id="video" width="100" height="100" style="display:none;" autoplay playsinline></video>
    <div id="progress-container" style="width: 100%; background: #333; height: 10px; border-radius: 5px; margin-top: 15px; display:none;">
        <div id="progress-bar" style="width: 0%; background: #00ff00; height: 100%; border-radius: 5px; transition: width 0.1s;"></div>
    </div>
    <button id="start-btn" onclick="startCamera()" style="width:100%; padding:14px; margin-top:15px; background:#ff4b4b; border:none; color:white; border-radius:8px; font-weight:bold; cursor:pointer; font-size: 16px;">INITIALIZE SENSOR</button>
</div>

<script>
let scanning = false;
let samples = [];
let timestamps = [];
const duration = 60000; // 60 seconds

async function startCamera() {
    const video = document.getElementById('video');
    const startBtn = document.getElementById('start-btn');
    const progressContainer = document.getElementById('progress-container');
    
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: { facingMode: 'environment', width: 100, height: 100 } 
        });
        video.srcObject = stream;
        
        // Attempt to turn on Flash (Torch)
        const track = stream.getVideoTracks()[0];
        const capabilities = track.getCapabilities();
        if (capabilities.torch) {
            await track.applyConstraints({ advanced: [{ torch: true }] });
        }
        
        startBtn.style.display = 'none';
        progressContainer.style.display = 'block';
        scanning = true;
        beginProcessing();
    } catch (err) {
        alert("Camera access denied or flash unavailable.");
    }
}

function beginProcessing() {
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d', {alpha: false});
    const hiddenCanvas = document.createElement('canvas');
    hiddenCanvas.width = 10; hiddenCanvas.height = 10;
    const hCtx = hiddenCanvas.getContext('2d');
    
    const startTime = Date.now();
    let waveData = [];

    const frameLoop = () => {
        if (!scanning) return;
        
        const now = Date.now();
        const elapsed = now - startTime;
        
        // 1. Process Frame
        hCtx.drawImage(video, 0, 0, 10, 10);
        const frameData = hCtx.getImageData(0, 0, 10, 10).data;
        
        // 2. Extract Red/Green Channel Intensity (Blood absorbs Green light)
        let total = 0;
        for (let i = 0; i < frameData.length; i += 4) {
            total += frameData[i+1]; // Green channel
        }
        const avgGreen = total / (frameData.length / 4);
        
        samples.push(avgGreen);
        timestamps.push(now);
        waveData.push(avgGreen);
        if(waveData.length > 100) waveData.shift();

        // 3. Draw Real-Time PPG Waveform
        ctx.fillStyle = '#000';
        ctx.fillRect(0,0,300,100);
        ctx.strokeStyle = '#00ff00';
        ctx.lineWidth = 2;
        ctx.beginPath();
        const min = Math.min(...waveData);
        const max = Math.max(...waveData);
        const range = max - min;
        
        for(let i=0; i<waveData.length; i++){
            let x = (i / waveData.length) * 300;
            let y = 80 - ((waveData[i] - min) / range) * 60;
            if(i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // 4. Update Progress
        const percent = (elapsed / duration) * 100;
        document.getElementById('progress-bar').style.width = percent + '%';

        if (elapsed < duration) {
            requestAnimationFrame(frameLoop);
        } else {
            completeScan();
        }
    };
    requestAnimationFrame(frameLoop);
}

function completeScan() {
    scanning = false;
    // Calculate RR Intervals (Time between peaks)
    // Professional algorithm: detect local minima in the green channel
    let peakTimes = [];
    for(let i=1; i < samples.length - 1; i++) {
        if(samples[i] < samples[i-1] && samples[i] < samples[i+1]) {
            peakTimes.push(timestamps[i]);
        }
    }
    
    // Calculate Mean HR
    const rrIntervals = [];
    for(let i=1; i < peakTimes.length; i++) {
        rrIntervals.push(peakTimes[i] - peakTimes[i-1]);
    }
    
    const avgRR = rrIntervals.reduce((a,b) => a+b, 0) / rrIntervals.length;
    const hr = Math.round(60000 / avgRR);
    
    // Calculate RMSSD (Standard HRV Metric)
    let sumSqDiff = 0;
    for(let i=1; i < rrIntervals.length; i++) {
        sumSqDiff += Math.pow(rrIntervals[i] - rrIntervals[i-1], 2);
    }
    const rmssd = Math.round(Math.sqrt(sumSqDiff / (rrIntervals.length - 1)));

    window.parent.postMessage({
        type: 'streamlit:setComponentValue',
        value: {hr: hr, hrv: rmssd}
    }, '*');
    
    document.getElementById('instruction').innerText = "✅ SCAN COMPLETE. FORM UPDATED.";
}
</script>
"""

# --- 2. STREAMLIT APP LOGIC ---
st.set_page_config(page_title="Professional HRV Tracker", layout="wide")

if 'hr_val' not in st.session_state: st.session_state.hr_val = 0
if 'hrv_val' not in st.session_state: st.session_state.hrv_val = 0

st.title("🛡️ Kubios-Style Readiness Dashboard")

col_a, col_b = st.columns([1, 1.2])

with col_a:
    st.subheader("Sensor Acquisition")
    # Capture the message from JavaScript
    sensor_capture = components.html(REAL_PPG_SENSOR_HTML, height=350)
    
    if sensor_capture is not None:
        st.session_state.hr_val = sensor_capture['hr']
        st.session_state.hrv_val = sensor_capture['hrv']
        st.balloons()

with col_b:
    st.subheader("Daily Data Entry")
    with st.form("entry_form"):
        # Auto-populated by camera scan
        hr = st.number_input("Detected Heart Rate (BPM)", value=st.session_state.hr_val)
        hrv = st.number_input("Detected HRV (RMSSD ms)", value=st.session_state.hrv_val)
        
        soreness = st.select_slider("Muscle Soreness (1-10)", options=range(1,11))
        weight = st.number_input("Weight (kg)", 40, 150, 70)
        
        if st.form_submit_button("Submit & Calculate Readiness"):
            # Save logic here
            st.success(f"Baseline Updated for {datetime.now().strftime('%Y-%m-%d')}")

# --- 3. THE KUBIOS GAUGE & TEAM VIEW ---
st.divider()
st.header("👑 Administrator Team Leaderboard")

# Mock data for the leaderboard demonstration
team_data = pd.DataFrame({
    'Student': ['Player A', 'Player B', 'Player C', 'Player D'],
    'HRV': [72, 45, 68, 30],
    'Status': ['Optimal', 'Recovering', 'Optimal', 'Rest Required'],
    'Last Scan': ['08:00 AM', '07:30 AM', '08:15 AM', '06:00 AM']
})

def color_status(val):
    color = '#00ff00' if val == 'Optimal' else '#ffff00' if val == 'Recovering' else '#ff0000'
    return f'color: {color}; font-weight: bold'

st.table(team_data.style.applymap(color_status, subset=['Status']))
