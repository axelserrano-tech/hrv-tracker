import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# --- 1. PERSISTENCE & DATABASE ---
DB_FILE = "readiness_log.csv"

def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Locations'])

# --- 2. THE PPG BRIDGE (JAVASCRIPT) ---
# This uses the Green-Channel variation to detect blood volume pulses.
def hrv_bridge_component():
    components.html(
        """
        <div style="background:#1e1e1e; color:white; padding:20px; border-radius:15px; text-align:center; font-family:sans-serif; border:2px solid #333;">
            <h3 id="msg" style="margin:0; color:#00ff00;">READY TO SCAN</h3>
            <canvas id="wave" width="300" height="60" style="background:#000; border-radius:5px; margin:10px 0; width:100%;"></canvas>
            <video id="v" width="1" height="1" style="opacity:0;" autoplay playsinline></video>
            <button id="btn" onclick="start()" style="width:100%; padding:15px; background:#ff4b4b; color:white; border:none; border-radius:8px; cursor:pointer; font-weight:bold;">START 20s SCAN</button>
        </div>

        <script>
        let samples = [], times = [], scanning = false;
        const canvas = document.getElementById('wave');
        const ctx = canvas.getContext('2d');

        async function start() {
            const stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'environment'}});
            const v = document.getElementById('v');
            v.srcObject = stream;
            const track = stream.getVideoTracks()[0];
            try { await track.applyConstraints({advanced: [{torch: true}]}); } catch(e) {}
            
            document.getElementById('btn').style.display = 'none';
            scanning = true;
            const startT = Date.now();
            
            const pCanvas = document.createElement('canvas');
            const pCtx = pCanvas.getContext('2d');
            pCanvas.width = 10; pCanvas.height = 10;

            const loop = () => {
                if(!scanning) return;
                pCtx.drawImage(v, 0, 0, 10, 10);
                const data = pCtx.getImageData(0,0,10,10).data;
                let g = 0; for(let i=1; i<data.length; i+=4) g += data[i];
                
                samples.push(g/100);
                times.push(Date.now());

                // Draw Waveform
                ctx.fillStyle = '#000'; ctx.fillRect(0,0,300,60);
                ctx.strokeStyle = '#00ff00'; ctx.beginPath();
                for(let i=0; i<100; i++) {
                    let val = samples[samples.length - 100 + i] || 0;
                    ctx.lineTo(i*3, 30 + (val - samples[samples.length-1])*5);
                }
                ctx.stroke();

                if(Date.now() - startT < 20000) {
                    document.getElementById('msg').innerText = "🔴 SCANNING: " + Math.ceil((20000-(Date.now()-startT))/1000) + "s";
                    requestAnimationFrame(loop);
                } else {
                    scanning = false;
                    track.stop();
                    finish();
                }
            };
            loop();
        }

        function finish() {
            // Precise Peak Detection for HRV
            let peaks = [];
            for(let i=2; i<samples.length-2; i++) {
                if(samples[i] < samples[i-1] && samples[i] < samples[i+1]) peaks.push(times[i]);
            }
            let rr = [];
            for(let i=1; i<peaks.length; i++) {
                let diff = peaks[i]-peaks[i-1];
                if(diff > 400 && diff < 1200) rr.push(diff);
            }
            
            const hr = Math.round(60000 / (rr.reduce((a,b)=>a+b,0)/rr.length));
            let dSq = 0;
            for(let i=1; i<rr.length; i++) dSq += Math.pow(rr[i]-rr[i-1], 2);
            const rmssd = Math.round(Math.sqrt(dSq / (rr.length - 1)));

            window.parent.postMessage({
                type: 'streamlit:setComponentValue',
                value: {hr: hr, rmssd: rmssd, key: Date.now()}
            }, '*');
            document.getElementById('msg').innerText = "✅ SYNCED";
        }
        </script>
        """, height=220
    )

# --- 3. THE APP ENGINE ---
st.set_page_config(page_title="Cardio-Baseline Pro", layout="wide")

if 'hr_val' not in st.session_state: st.session_state.hr_val = 0
if 'hrv_val' not in st.session_state: st.session_state.hrv_val = 0
if 'last_key' not in st.session_state: st.session_state.last_key = 0

df = load_data()

st.title("🛡️ Kubios-Style Readiness Dashboard")

col_scan, col_entry = st.columns([1, 1.3])

with col_scan:
    st.subheader("1. Pulse Acquisition")
    # This captures the JS data
    sensor_data = hrv_bridge_component()
    
    # Critical Sync Check
    if sensor_data and sensor_data.get('key', 0) > st.session_state.last_key:
        st.session_state.hr_val = sensor_data['hr']
        st.session_state.hrv_val = sensor_data['rmssd']
        st.session_state.last_key = sensor_data['key']
        st.rerun()

with col_entry:
    st.subheader("2. Subjective Recovery")
    with st.form("log_entry", clear_on_submit=True):
        c1, c2 = st.columns(2)
        hr = c1.number_input("Detected HR (BPM)", value=st.session_state.hr_val)
        rmssd = c2.number_input("Detected HRV (RMSSD)", value=st.session_state.hrv_val)
        
        sore_val = st.select_slider("Muscle Soreness (1-10)", range(1, 11))
        
        
        
        locs = st.multiselect("Identify Sore Areas", ["Lower Back", "Quads", "Hamstrings", "Calves", "Shoulders", "Core"])
        
        if st.form_submit_button("Record Daily Baseline"):
            new_data = pd.DataFrame({
                'User': ["Current_Student"], 'Timestamp': [datetime.now()],
                'HR': [hr], 'RMSSD': [rmssd], 'Soreness': [sore_val], 'Locations': [", ".join(locs)]
            })
            df = pd.concat([df, new_data], ignore_index=True)
            df.to_csv(DB_FILE, index=False)
            st.success("Data stored in administrative log.")
            st.rerun()

# --- 4. DATA VISUALIZATION (THE KUBIOS REPLICA) ---
st.divider()

if not df.empty:
    # Baseline Math
    baseline_rmssd = df['RMSSD'].mean()
    std_rmssd = df['RMSSD'].std() if len(df) > 1 else 10
    latest_rmssd = df['RMSSD'].iloc[-1]
    
    vis_col, trend_col = st.columns([1, 2])
    
    with vis_col:
        st.subheader("Cardiovascular Readiness")
        # Color Coding: Green = Normal, Yellow = 0.5-1.5 SD, Red = >1.5 SD
        fig = go.Figure(go.Indicator(
            mode = "gauge+number+delta",
            value = latest_rmssd,
            delta = {'reference': baseline_rmssd},
            gauge = {
                'axis': {'range': [0, 150]},
                'bar': {'color': "black", 'thickness': 0.2},
                'steps': [
                    {'range': [0, baseline_rmssd - 1.5*std_rmssd], 'color': "#ff4b4b"},
                    {'range': [baseline_rmssd - 1.5*std_rmssd, baseline_rmssd - 0.5*std_rmssd], 'color': "#ffff00"},
                    {'range': [baseline_rmssd - 0.5*std_rmssd, 150], 'color': "#00cc96"}
                ],
                'threshold': {'line': {'color': "black", 'width': 4}, 'value': baseline_rmssd}
            }
        ))
        st.plotly_chart(fig, use_container_width=True)

    with trend_col:
        st.subheader("7-Day Trend Analysis")
        # Line chart showing user's RMSSD vs their Personal Baseline
        df_plot = df.tail(7).copy()
        df_plot['Baseline'] = baseline_rmssd
        st.line_chart(df_plot.set_index('Timestamp')[['RMSSD', 'Baseline']])

# --- 5. ADMINISTRATIVE VIEW ---
with st.expander("🔐 Administrative Compliance Log"):
    st.write("Full audit trail for recovery oversight.")
    st.dataframe(df.sort_values(by='Timestamp', ascending=False), use_container_width=True)
