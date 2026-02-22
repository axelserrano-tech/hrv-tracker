import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# --- 1. THE REFINED JAVASCRIPT BLOB ---
# We added a 'Streamlit.setComponentValue' listener to ensure the handshake is 100% stable.
HRV_JS_CODE = """
<div id="root">
    <style>
        .container {
            background: #000; padding: 20px; border-radius: 20px; 
            text-align: center; color: white; font-family: sans-serif;
            width: 100%; max-width: 400px; margin: auto; box-sizing: border-box;
            border: 2px solid #222;
        }
        #waveCanvas {
            background: #000; border-radius: 12px; margin: 15px 0; 
            width: 100%; height: 140px; display: block; border: 1px solid #333;
        }
        .bpm-main { font-size: 60px; font-weight: 800; color: #00ff41; margin: 0; }
        #progress-bg { width: 100%; height: 8px; background: #222; border-radius: 4px; margin: 10px 0; overflow: hidden; }
        #progress-fill { width: 0%; height: 100%; background: #00ff41; transition: linear 0.5s; }
        #btn {
            padding: 18px; background: #00ff41; color: #000; border: none; 
            border-radius: 15px; cursor: pointer; font-weight: 800; width: 100%; font-size: 16px;
        }
    </style>
    <div class="container">
        <div id="status" style="font-size:11px; color:#888; text-transform:uppercase;">Ready</div>
        <div class="bpm-main" id="bpm">--</div>
        <div id="progress-bg"><div id="progress-fill"></div></div>
        <canvas id="waveCanvas"></canvas>
        <video id="vid" autoplay playsinline style="display:none;"></video>
        <button id="btn" onclick="start()">Start 60s Scan</button>
    </div>
</div>

<script>
    // Standard Streamlit Component Handshake
    function sendToStreamlit(value) {
        window.parent.postMessage({
            isStreamlitMessage: true,
            type: "streamlit:setComponentValue",
            value: value
        }, "*");
    }

    let scanning = false;
    let beatTimes = [];
    let waveData = new Array(100).fill(0);
    const canvas = document.getElementById('waveCanvas');
    const ctx = canvas.getContext('2d');

    function draw(sig) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        waveData.push(sig); waveData.shift();
        let max = Math.max(...waveData.map(Math.abs)) || 0.1;
        let scale = (canvas.height / 2.5) / max;
        ctx.strokeStyle = '#00ff41'; ctx.lineWidth = 3;
        ctx.beginPath();
        for(let i=0; i<100; i++) {
            let x = (canvas.width / 100) * i;
            let y = (canvas.height / 2) - (waveData[i] * scale);
            if(i==0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }

    async function start() {
        if (scanning) return;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
            const vid = document.getElementById('vid');
            vid.srcObject = stream;
            document.getElementById('btn').style.display = 'none';
            scanning = true;

            const track = stream.getVideoTracks()[0];
            const caps = track.getCapabilities();
            if (caps.torch) await track.applyConstraints({ advanced: [{ torch: true }] });

            const pC = document.createElement('canvas');
            const pCtx = pC.getContext('2d', {willReadFrequently: true});
            pC.width = 20; pC.height = 20;

            let startTime = performance.now();
            let lastB = 0; let lp = 0;

            function process() {
                if (!scanning) return;
                let now = performance.now();
                let elapsed = (now - startTime) / 1000;
                
                document.getElementById('progress-fill').style.width = (elapsed/60*100) + "%";
                document.getElementById('status').innerText = "Scanning: " + Math.ceil(60 - elapsed) + "s";

                if (elapsed >= 60) {
                    scanning = false; track.stop();
                    let rr = [];
                    for(let i=1; i<beatTimes.length; i++) rr.push(beatTimes[i] - beatTimes[i-1]);
                    
                    let diffs = [];
                    for(let i=1; i<rr.length; i++) diffs.push(Math.pow(rr[i] - rr[i-1], 2));
                    let rmssd = Math.sqrt(diffs.reduce((a,b)=>a+b,0) / diffs.length);
                    let hr = Math.round(60000 / (rr.reduce((a,b)=>a+b,0)/rr.length));
                    
                    sendToStreamlit({hr: hr, hrv: Math.round(rmssd), status: "complete"});
                    return;
                }

                pCtx.drawImage(vid, 0, 0, 20, 20);
                let px = pCtx.getImageData(0,0,20,20).data;
                let g = 0; for(let i=1; i<px.length; i+=4) g += px[i];
                g /= 400;
                lp = (0.9 * lp) + (0.1 * g);
                let sig = g - lp;
                draw(sig);

                if (sig > 0.15 && (now - lastB) > 400) {
                    beatTimes.push(now);
                    if(beatTimes.length > 2) document.getElementById('bpm').innerText = Math.round(60000/(now-lastB));
                    lastB = now;
                }
                requestAnimationFrame(process);
            }
            process();
        } catch (e) { document.getElementById('status').innerText = "CAMERA ERROR"; }
    }
</script>
"""

# --- 2. THE SENSOR COMPONENT ---
def hrv_sensor_component():
    # Use a static height and avoid complex Python logic inside the call
    return components.html(HRV_JS_CODE, height=450, key="hrv_component_v1")

# --- 3. DATA & STATE MANAGEMENT ---
st.set_page_config(page_title="Kubios HRV", layout="wide")

# Initialize Session States safely
if 'detected_hr' not in st.session_state:
    st.session_state.detected_hr = 70
if 'detected_hrv' not in st.session_state:
    st.session_state.detected_hrv = 50

# --- 4. APP LAYOUT ---
st.title("Research-Grade HRV Readiness")

col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("Acquisition")
    
    # Capture the data from the component
    res = hrv_sensor_component()
    
    # Use a strict type check to avoid the TypeError
    if res is not None and isinstance(res, dict):
        if "hr" in res:
            st.session_state.detected_hr = res["hr"]
            st.session_state.detected_hrv = res["hrv"]
            st.success(f"Locked: {res['hr']} BPM")

    # The manual entry form
    with st.form("manual_entry"):
        hr_val = st.number_input("Heart Rate", value=int(st.session_state.detected_hr))
        hrv_val = st.number_input("HRV (RMSSD)", value=int(st.session_state.detected_hrv))
        if st.form_submit_button("Save Entry"):
            st.toast("Entry Saved locally (Simulated)")

with col_right:
    st.subheader("Training Readiness")
    
    st.info("The RMSSD (Root Mean Square of Successive Differences) is the gold standard for measuring parasympathetic recovery. A higher RMSSD compared to your baseline indicates high readiness for training.")
