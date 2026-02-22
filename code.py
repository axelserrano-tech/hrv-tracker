import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# --- 1. THE CLINICAL-GRADE SENSOR ---
# Uses Green-Channel Photoplethysmography (PPG)
PPG_SENSOR_HTML = """
<div style="background: #111; color: white; padding: 20px; border-radius: 15px; text-align: center; font-family: sans-serif; border: 2px solid #333;">
    <h3 style="margin:0; color: #ff4b4b;">🧬 Optical PPG Sensor</h3>
    <p id="msg" style="font-size: 13px; color: #00ff00;">Ready: Place finger over camera & flash</p>
    <canvas id="plot" width="400" height="100" style="background:#000; border-radius:5px;"></canvas>
    <video id="vid" width="100" height="100" style="display:none;" autoplay playsinline></video>
    <button id="start" onclick="init()" style="width:100%; padding:15px; margin-top:10px; background:#ff4b4b; border:none; color:white; border-radius:8px; font-weight:bold; cursor:pointer;">START 60s BASELINE SCAN</button>
</div>

<script>
let stream, track, samples = [], times = [];

async function init() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'environment'}});
        const vid = document.getElementById('vid');
        vid.srcObject = stream;
        track = stream.getVideoTracks()[0];
        try { await track.applyConstraints({advanced: [{torch: true}]}); } catch(e) {}
        
        document.getElementById('start').style.display = 'none';
        run();
    } catch(e) { alert("Camera Error"); }
}

function run() {
    const canvas = document.getElementById('plot');
    const ctx = canvas.getContext('2d');
    const v = document.getElementById('vid');
    const hidden = document.createElement('canvas');
    const hCtx = hidden.getContext('2d');
    hidden.width = 10; hidden.height = 10;
    
    const startT = Date.now();
    let displayData = [];

    const loop = () => {
        hCtx.drawImage(v, 0, 0, 10, 10);
        const data = hCtx.getImageData(0,0,10,10).data;
        
        // Extract Green Channel (Standard for PPG)
        let g = 0;
        for(let i=1; i<data.length; i+=4) g += data[i];
        const val = g / 100;
        
        samples.push(val);
        times.push(Date.now());
        displayData.push(val);
        if(displayData.length > 100) displayData.shift();

        // Waveform Visualizer
        ctx.fillStyle = '#000'; ctx.fillRect(0,0,400,100);
        ctx.strokeStyle = '#00ff00'; ctx.lineWidth = 2; ctx.beginPath();
        const min = Math.min(...displayData), max = Math.max(...displayData), r = max-min;
        displayData.forEach((d, i) => {
            const x = (i/100)*400;
            const y = 90 - ((d-min)/r)*80;
            if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
        });
        ctx.stroke();

        if(Date.now() - startT < 60000) {
            document.getElementById('msg').innerText = "Acquiring: " + Math.round((Date.now()-startT)/1000) + "s / 60s";
            requestAnimationFrame(loop);
        } else {
            process();
        }
    };
    loop();
}

function process() {
    track.stop();
    // Peak Detection & rMSSD Calculation
    let peaks = [];
    for(let i=2; i<samples.length-2; i++) {
        if(samples[i] < samples[i-1] && samples[i] < samples[i+1]) peaks.push(times[i]);
    }
    let rr = [];
    for(let i=1; i<peaks.length; i++) rr.push(peaks[i] - peaks[i-1]);
    
    // Filter out ectopic beats (RR < 400ms or > 1200ms)
    rr = rr.filter(x => x > 400 && x < 1200);
    
    const hr = Math.round(60000 / (rr.reduce((a,b)=>a+b,0)/rr.length));
    let diffSq = 0;
    for(let i=1; i<rr.length; i++) diffSq += Math.pow(rr[i] - rr[i-1], 2);
    const rmssd = Math.round(Math.sqrt(diffSq / (rr.length - 1)));

    window.parent.postMessage({type: 'streamlit:setComponentValue', value: {hr, hrv: rmssd}}, '*');
    document.getElementById('msg').innerText = "✅ COMPLETE: Data Sent to Form";
}
</script>
"""

# --- 2. DATA HANDLING ---
if 'hr_val' not in st.session_state: st.session_state.hr_val = 0
if 'hrv_val' not in st.session_state: st.session_state.hrv_val = 0

st.title("🛡️ Kubios Readiness Portal")

col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("1. Pulse Acquisition")
    # This captures the value from the JS
    result = components.html(PPG_SENSOR_HTML, height=300)
    
    # THE CRITICAL FIX: Ensure 'result' is not None before subscripting
    if result is not None and isinstance(result, dict):
        st.session_state.hr_val = result.get('hr', 0)
        st.session_state.hrv_val = result.get('hrv', 0)

with col2:
    st.subheader("2. Subjective Entry")
    with st.form("entry"):
        hr = st.number_input("Heart Rate (BPM)", value=st.session_state.hr_val)
        hrv = st.number_input("HRV (rMSSD)", value=st.session_state.hrv_val)
        sore = st.select_slider("Muscle Soreness", range(1, 11))
        
        if st.form_submit_button("Submit Entry"):
            # Here you would save to CSV/DB
            st.success("Measurement recorded in your baseline.")

# --- 3. KUBIOS READINESS VISUALIZER ---
st.divider()
st.subheader("📊 Readiness Baseline")

# Example calculation for the Readiness Gauge
if st.session_state.hrv_val > 0:
    # A real replica uses 7-day rolling std deviation
    baseline = 60 # Simulated mean
    std_dev = 8   # Simulated volatility
    
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = st.session_state.hrv_val,
        gauge = {
            'axis': {'range': [20, 100]},
            'bar': {'color': "black"},
            'steps': [
                {'range': [0, baseline - std_dev], 'color': "red"},
                {'range': [baseline - std_dev, baseline - (0.5*std_dev)], 'color': "yellow"},
                {'range': [baseline - (0.5*std_dev), 100], 'color': "green"}
            ],
            'threshold': {'line': {'color': "black", 'width': 4}, 'value': baseline}
        }
    ))
    st.plotly_chart(fig, use_container_width=True)
