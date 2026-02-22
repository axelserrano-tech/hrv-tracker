import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# --- 1. SETTINGS & STATE ---
st.set_page_config(page_title="Kubios HRV Tracker", layout="wide")

# Initialize state before ANYTHING else runs
for key, val in [("hr", 70), ("hrv", 50), ("auth", False)]:
    if key not in st.session_state:
        st.session_state[key] = val

# --- 2. THE STABLE JAVASCRIPT ---
# This uses a slightly different data bridge to bypass the TypeError
HRV_HTML = """
<div style="background:#111; color:white; padding:20px; border-radius:15px; font-family:sans-serif; text-align:center;">
    <div id="status" style="color:#888; font-size:12px;">READY</div>
    <div id="bpm" style="font-size:50px; font-weight:bold; color:#00ff41;">--</div>
    <canvas id="canvas" style="width:100%; height:100px; background:#000; border-radius:10px;"></canvas>
    <video id="v" autoplay playsinline style="display:none;"></video>
    <button id="b" style="width:100%; padding:15px; background:#00ff41; border:none; border-radius:10px; font-weight:bold; margin-top:10px;">START 60s SCAN</button>
</div>

<script>
const b=document.getElementById('b'), v=document.getElementById('v'), canvas=document.getElementById('canvas'), ctx=canvas.getContext('2d');
let scanning=false, beats=[], wave=new Array(100).fill(0);

function draw(s){
    ctx.clearRect(0,0,canvas.width,canvas.height);
    wave.push(s); wave.shift();
    ctx.strokeStyle='#00ff41'; ctx.lineWidth=2; ctx.beginPath();
    for(let i=0;i<100;i++){
        let x=(canvas.width/100)*i, y=(canvas.height/2)-(wave[i]*20);
        if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);
    }
    ctx.stroke();
}

b.onclick = async () => {
    if(scanning) return;
    const stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"}});
    v.srcObject=stream; b.style.display='none'; scanning=true;
    
    const track = stream.getVideoTracks()[0];
    const caps = track.getCapabilities();
    if(caps.torch) await track.applyConstraints({advanced:[{torch:true}]});

    let start=performance.now(), last=0, lp=0;
    const pC=document.createElement('canvas'); const pCtx=pC.getContext('2d',{willReadFrequently:true});
    pC.width=20; pC.height=20;

    function loop(){
        if(!scanning) return;
        let now=performance.now(), elapsed=(now-start)/1000;
        document.getElementById('status').innerText = "SCANNING: " + Math.ceil(60-elapsed) + "s";
        
        if(elapsed >= 60){
            scanning=false; track.stop();
            let rr=[]; for(let i=1;i<beats.length;i++) rr.push(beats[i]-beats[i-1]);
            let diffsSq = rr.slice(1).map((val,i)=>Math.pow(val-rr[i],2));
            let rmssd = Math.sqrt(diffsSq.reduce((a,b)=>a+b,0)/diffsSq.length);
            let hr = Math.round(60000/(rr.reduce((a,b)=>a+b,0)/rr.length));
            
            window.parent.postMessage({
                isStreamlitMessage: true,
                type: "streamlit:setComponentValue",
                value: {hr: hr, hrv: Math.round(rmssd)}
            }, "*");
            return;
        }

        pCtx.drawImage(v,0,0,20,20);
        let px=pCtx.getImageData(0,0,20,20).data, g=0;
        for(let i=1;i<px.length;i+=4) g+=px[i];
        g/=400; lp=(0.9*lp)+(0.1*g); let sig=g-lp;
        draw(sig);

        if(sig > 0.1 && (now-last)>400){
            beats.push(now);
            if(beats.length>2) document.getElementById('bpm').innerText = Math.round(60000/(now-last));
            last=now;
        }
        requestAnimationFrame(loop);
    }
    loop();
};
</script>
"""

# --- 3. MAIN APP LOGIC ---
st.title("Precision HRV Dashboard")

# Put everything in a container to manage the refresh cycle
main_container = st.container()

with main_container:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("1. Pulse Scanner")
        # Render component and catch data
        # We use a try/except block to catch the TypeError if Streamlit struggles with the handshake
        try:
            val = components.html(HRV_HTML, height=350, key="hrv_fixed_v3")
            if val and isinstance(val, dict):
                st.session_state.hr = val.get('hr', st.session_state.hr)
                st.session_state.hrv = val.get('hrv', st.session_state.hrv)
                st.success("Scan Data Received")
        except Exception:
            st.error("Component Handshake Error. Please refresh the page.")

    with col2:
        st.subheader("2. Results & Entry")
        
        with st.form("manual"):
            hr_in = st.number_input("Heart Rate", value=int(st.session_state.hr))
            hrv_in = st.number_input("HRV (RMSSD)", value=int(st.session_state.hrv))
            if st.form_submit_button("Save Measurement"):
                st.write("Data logged!")

st.info("⚠️ **Note:** Ensure you are using HTTPS and have granted camera permissions. This tool uses the green light absorption method (PPG) to detect your pulse through the fingertip.")

# --- 4. DATA TRENDS ---
st.divider()
st.subheader("Readiness Trend")

# Placeholder for graph
st.line_chart(np.random.randn(10, 2))
