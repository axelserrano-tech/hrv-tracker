import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# --- 1. THE RESEARCH-GRADE SENSOR COMPONENT ---
def hrv_sensor_component():
    return components.html(
        """
        <style>
            .container {
                background: #000; padding: 20px; border-radius: 20px; 
                text-align: center; color: white; font-family: -apple-system, sans-serif;
                width: 100%; max-width: 420px; margin: auto; box-sizing: border-box;
                border: 2px solid #222;
            }
            #waveCanvas {
                background: #000; border-radius: 12px; margin: 15px 0; 
                width: 100%; height: 140px; display: block; border: 1px solid #333;
            }
            .bpm-main { font-size: 64px; font-weight: 800; color: #00ff41; margin: 0; line-height: 1; }
            .label-sm { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 5px;}
            #progress-bar { width: 100%; height: 8px; background: #222; border-radius: 4px; margin: 15px 0; overflow: hidden; }
            #progress-fill { width: 0%; height: 100%; background: #00ff41; transition: linear 0.5s; }
            #camera-btn {
                padding: 18px; background: #00ff41; color: #000; border: none; 
                border-radius: 15px; cursor: pointer; font-weight: 800; width: 100%; 
                font-size: 16px; text-transform: uppercase;
            }
        </style>

        <div class="container">
            <div class="label-sm" id="status">Ready for Precision Scan</div>
            <div class="bpm-main" id="bpm-val">--</div>
            <div class="label-sm">Beats Per Minute</div>
            
            <div id="progress-bar"><div id="progress-fill"></div></div>
            
            <canvas id="waveCanvas"></canvas>
            <video id="video" autoplay playsinline style="display:none;"></video>
            <button id="camera-btn" onclick="initSensor()">Start 60s Measurement</button>
        </div>

        <script>
        let scanning = false;
        let signalAcquired = false;
        let beatTimes = [];
        let waveData = new Array(120).fill(0);
        const canvas = document.getElementById('waveCanvas');
        const ctx = canvas.getContext('2d');

        function drawWave(signal) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            waveData.push(signal);
            waveData.shift();

            let max = Math.max(...waveData.map(Math.abs)) || 0.1;
            let scale = (canvas.height / 2.3) / max;

            ctx.strokeStyle = '#00ff41';
            ctx.lineWidth = 3;
            ctx.shadowBlur = 10;
            ctx.shadowColor = '#00ff41';
            ctx.beginPath();
            for(let i=0; i<waveData.length; i++) {
                let x = (canvas.width / (waveData.length-1)) * i;
                let y = (canvas.height / 2) - (waveData[i] * scale);
                if(i==0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        async function initSensor() {
            if (scanning) return;
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
                const video = document.getElementById('video');
                video.srcObject = stream;
                document.getElementById('camera-btn').style.display = 'none';
                scanning = true;

                const track = stream.getVideoTracks()[0];
                const caps = track.getCapabilities();
                if (caps.torch) await track.applyConstraints({ advanced: [{ torch: true }] });

                const pCanvas = document.createElement('canvas');
                const pCtx = pCanvas.getContext('2d', { willReadFrequently: true });
                pCanvas.width = 20; pCanvas.height = 20;

                let startTime = 0;
                let lastBeat = 0;
                let lowPass = 0;

                function process() {
                    if (!scanning) return;
                    let now = performance.now();
                    pCtx.drawImage(video, 0, 0, 20, 20);
                    const pixels = pCtx.getImageData(0, 0, 20, 20).data;
                    let green = 0;
                    for (let i = 1; i < pixels.length; i += 4) green += pixels[i];
                    green /= 400;

                    lowPass = (0.9 * lowPass) + (0.1 * green);
                    let signal = green - lowPass;
                    drawWave(signal);

                    if (!signalAcquired) {
                        document.getElementById('status').innerText = "Acquiring Signal... Keep Still";
                        if (Math.abs(signal) > 0.25) { 
                            signalAcquired = true; 
                            startTime = performance.now();
                        }
                    } else {
                        let elapsed = (now - startTime) / 1000;
                        document.getElementById('progress-fill').style.width = (elapsed / 60 * 100) + "%";
                        document.getElementById('status').innerText = "Scanning: " + Math.ceil(60 - elapsed) + "s";

                        if (elapsed >= 60) {
                            scanning = false; track.stop();
                            let rr = [];
                            for(let i=1; i<beatTimes.length; i++) rr.push(beatTimes[i] - beatTimes[i-1]);
                            
                            // Precision RMSSD Math
                            let diffsSq = [];
                            for(let i=1; i<rr.length; i++) diffsSq.push(Math.pow(rr[i] - rr[i-1], 2));
                            let rmssd = Math.sqrt(diffsSq.reduce((a,b)=>a+b, 0) / diffsSq.length);
                            let avgHR = Math.round(60000 / (rr.reduce((a,b)=>a+b, 0) / rr.length));

                            window.parent.postMessage({
                                type: 'streamlit:setComponentValue',
                                value: { hr: avgHR, hrv: Math.round(rmssd) }
                            }, '*');
                            return;
                        }
                    }

                    if (signal > 0.2 && (now - lastBeat) > 420) {
                        beatTimes.push(now);
                        if(beatTimes.length > 2) {
                            document.getElementById('bpm-val').innerText = Math.round(60000 / (now - lastBeat));
                        }
                        lastBeat = now;
                    }
                    requestAnimationFrame(process);
                }
                process();
            } catch (e) { document.getElementById('status').innerText = "Hardware Access Denied"; }
        }
        </script>
        """,
        height=450,
    )

# --- 2. DATA ENGINE ---
DB_FILE = "student_health_data.csv"

def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User_ID', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location', 'Weight', 'Sex'])

# --- 3. SESSION & LOGIN ---
st.set_page_config(page_title="Kubios-Grade HRV", layout="wide")

if 'auth' not in st.session_state:
    st.session_state.update({'auth': False, 'user': None, 'role': None, 'detected_hr': 70, 'detected_hrv': 50})

if not st.session_state.auth:
    st.title("🔐 Access Portal")
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
            else: st.error("Invalid credentials.")
    st.stop()

# --- 4. MAIN INTERFACE ---
df = load_data()

with st.sidebar:
    st.subheader(f"User: {st.session_state.user}")
    if st.button("Logout"):
        st.session_state.auth = False
        st.rerun()
    st.divider()

if st.session_state.role == "student":
    col_l, col_r = st.columns([1, 2])
    
    with col_l:
        st.header("Step 1: Measurement")
        sensor_data = hrv_sensor_component()
        
        # FIX: The null-check that prevents your error
        if sensor_data is not None:
            st.session_state.detected_hr = sensor_data.get('hr', 70)
            st.session_state.detected_hrv = sensor_data.get('hrv', 50)
            st.success(f"Scan Finished: {st.session_state.detected_hr} BPM / {st.session_state.detected_hrv}ms RMSSD")

        with st.form("data_entry", clear_on_submit=True):
            st.subheader("Step 2: Sync Data")
            final_hr = st.number_input("Heart Rate", 40, 180, int(st.session_state.detected_hr))
            final_hrv = st.number_input("HRV (RMSSD)", 5, 250, int(st.session_state.detected_hrv))
            s_val = st.slider("Soreness Level", 1, 10, 1)
            
            if st.form_submit_button("Submit to Dashboard"):
                new_entry = pd.DataFrame({
                    'User_ID': [st.session_state.user],
                    'Timestamp': [datetime.now()],
                    'HR': [final_hr],
                    'RMSSD': [final_hrv],
                    'Soreness': [s_val],
                    'Location': ["None"], 'Weight': [70], 'Sex': ["Other"]
                })
                df = pd.concat([df, new_entry], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.balloons()
                st.rerun()

    with col_r:
        st.header("Step 3: Readiness Analysis")
        u_df = df[df['User_ID'] == st.session_state.user]
        if not u_df.empty:
            
            latest = u_df['RMSSD'].iloc[-1]
            avg = u_df['RMSSD'].mean()
            
            st.metric("Latest HRV", f"{latest} ms", f"{round(latest-avg, 1)} from avg")
            
            fig = go.Figure(go.Scatter(x=u_df['Timestamp'], y=u_df['RMSSD'], mode='lines+markers', name='HRV'))
            fig.add_hline(y=avg, line_dash="dash", line_color="gray", annotation_text="Baseline")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Complete your first 60s scan to see your recovery baseline.")

elif st.session_state.role == "admin":
    st.title("👑 Coach Control Panel")
    st.dataframe(df.sort_values('Timestamp', ascending=False), use_container_width=True)
    st.download_button("Export Dataset", df.to_csv(index=False), "team_data.csv")
