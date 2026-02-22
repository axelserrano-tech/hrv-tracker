import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import time
import streamlit.components.v1 as components

# --- 1. RESEARCH-GRADE SENSOR COMPONENT ---
def hrv_sensor_component():
    return components.html(
        """
        <style>
            .container {
                background: #0d0d0d; padding: 20px; border-radius: 20px; 
                text-align: center; color: white; font-family: sans-serif;
                width: 100%; max-width: 400px; margin: auto; box-sizing: border-box;
                border: 1px solid #333;
            }
            #waveCanvas {
                background: #000; border-radius: 12px; margin: 15px 0; 
                width: 100%; height: 140px; display: block; border: 1px solid #222;
            }
            .bpm-text { font-size: 56px; font-weight: 800; color: #00ff41; margin: 0; text-shadow: 0 0 20px rgba(0,255,65,0.4); }
            #progress-bg { width: 100%; height: 8px; background: #222; border-radius: 4px; margin: 15px 0; overflow: hidden; }
            #progress-fill { width: 0%; height: 100%; background: #00ff41; transition: linear 1s; }
            #camera-btn {
                padding: 18px; background: #00ff41; color: black; border: none; 
                border-radius: 14px; cursor: pointer; font-weight: bold; width: 100%; font-size: 18px;
                box-shadow: 0 4px 15px rgba(0,255,65,0.3);
            }
            .status-label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 1.5px; }
        </style>

        <div class="container">
            <div class="status-label" id="status">Ready for Scan</div>
            <div class="bpm-text" id="bpm-val">--</div>
            <div class="status-label">Beats Per Minute</div>
            <div id="progress-bg"><div id="progress-fill"></div></div>
            <canvas id="waveCanvas"></canvas>
            <video id="video" autoplay playsinline style="display:none;"></video>
            <button id="camera-btn" onclick="initSensor()">BEGIN 60s HRV SCAN</button>
        </div>

        <script>
        let scanning = false;
        let signalAcquired = false;
        let beatTimes = [];
        let waveData = new Array(100).fill(0);
        const canvas = document.getElementById('waveCanvas');
        const ctx = canvas.getContext('2d');

        function draw(signal) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            waveData.push(signal);
            waveData.shift();
            let maxVal = Math.max(...waveData.map(Math.abs)) || 0.1;
            let scale = (canvas.height / 2.5) / maxVal;
            ctx.strokeStyle = '#00ff41';
            ctx.lineWidth = 3;
            ctx.shadowBlur = 8;
            ctx.shadowColor = '#00ff41';
            ctx.beginPath();
            for(let i=0; i<100; i++){
                let x = (canvas.width / 100) * i;
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

                    lowPass = (0.92 * lowPass) + (0.08 * green);
                    let signal = green - lowPass;
                    draw(signal);

                    // SIGNAL CHECK: Don't start the timer until we see clear rhythmic peaks
                    if (!signalAcquired) {
                        document.getElementById('status').innerText = "Adjusting Signal...";
                        if (signal > 0.2) { 
                             signalAcquired = true;
                             startTime = performance.now(); 
                        }
                    } else {
                        let elapsed = (now - startTime) / 1000;
                        document.getElementById('status').innerText = "Capturing: " + Math.ceil(60-elapsed) + "s";
                        document.getElementById('progress-fill').style.width = (elapsed/60*100) + "%";

                        if (elapsed >= 60) {
                            scanning = false; track.stop();
                            let rr = [];
                            for(let i=1; i<beatTimes.length; i++) rr.push(beatTimes[i]-beatTimes[i-1]);
                            
                            // KUBIOS-STYLE RMSSD MATH
                            let diffs = [];
                            for(let i=1; i<rr.length; i++) diffs.push(Math.pow(rr[i] - rr[i-1], 2));
                            let rmssd = Math.sqrt(diffs.reduce((a,b)=>a+b, 0) / diffs.length);
                            let avgHR = Math.round(60000 / (rr.reduce((a,b)=>a+b,0) / rr.length));

                            window.parent.postMessage({
                                type: 'streamlit:setComponentValue',
                                value: { hr: avgHR, hrv: Math.round(rmssd) }
                            }, '*');
                            return;
                        }
                    }

                    // ACCURATE PEAK TRIGGER
                    if (signal > 0.15 && (now - lastBeat) > 400) {
                        beatTimes.push(now);
                        if(beatTimes.length > 2) {
                            document.getElementById('bpm-val').innerText = Math.round(60000 / (now - lastBeat));
                        }
                        lastBeat = now;
                    }
                    requestAnimationFrame(process);
                }
                process();
            } catch (e) { document.getElementById('status').innerText = "CAMERA ERROR"; }
        }
        </script>
        """,
        height=420,
    )

# ... (Login logic)

# --- 2. THE CORRECTED SENSOR LOGIC ---
if st.session_state.role == "student":
    st.header("🕒 Daily Measurement")
    
    # Run the component
    sensor_data = hrv_sensor_component()
    
    # CRITICAL: Add the null-check here to fix the "NoneType" error
    if sensor_data is not None:
        st.session_state['detected_hr'] = sensor_data.get('hr', 70)
        st.session_state['detected_hrv'] = sensor_data.get('hrv', 50)
        st.success(f"✅ Data Locked: {st.session_state['detected_hr']} BPM / {st.session_state['detected_hrv']}ms HRV")

    st.divider()

    # --- DATA ENTRY FORM ---
    with st.form("entry", clear_on_submit=True):
        # Using .get() ensures that even if a scan hasn't run, the form doesn't crash
        current_hr = st.session_state.get('detected_hr', 70)
        current_hrv = st.session_state.get('detected_hrv', 50)
        
        hr = st.number_input("Heart Rate (BPM)", 40, 160, int(current_hr))
        hrv = st.number_input("HRV (RMSSD ms)", 5, 250, int(current_hrv))

# --- 2. INITIAL SETUP ---
st.set_page_config(page_title="Kubios HRV Readiness", layout="wide")
DB_FILE = "student_health_data.csv"

def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User_ID', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location', 'Weight', 'Sex'])

# --- LOGIN SYSTEM ---
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

# --- MAIN APP ---
df = load_data()

with st.sidebar:
    st.write(f"Logged in as: **{st.session_state.user}**")
    if st.button("Logout"):
        st.session_state.auth = False
        st.rerun()
    st.divider()
    
    if st.session_state.role == "student":
        st.header("🕒 Daily Measurement")
        # CAPTURE DATA FROM SENSOR
        sensor_data = hrv_sensor_component()
        
        if sensor_data:
            st.session_state['detected_hr'] = sensor_data['hr']
            st.session_state['detected_hrv'] = sensor_data['hrv']
            st.success(f"✅ Scan Complete! HR: {sensor_data['hr']} | HRV: {sensor_data['hrv']}")

        st.divider()

        # --- DATA ENTRY FORM ---
        with st.form("entry", clear_on_submit=True):
            hr = st.number_input("Heart Rate (BPM)", 40, 160, st.session_state.get('detected_hr', 70))
            hrv = st.number_input("HRV (RMSSD ms)", 5, 250, st.session_state.get('detected_hrv', 50))
            
            st.write("---")
            st.write("🧘 **Anatomical Soreness Map**")
            c1, c2 = st.columns(2)
            with c1:
                s1, s2, s3 = st.checkbox("Upper Back"), st.checkbox("Shoulders"), st.checkbox("Chest")
            with c2:
                s4, s5, s6 = st.checkbox("Quads"), st.checkbox("Hamstrings"), st.checkbox("Calves")
            
            s_val = st.select_slider("Intensity (1-10)", list(range(1, 11)), 1)
            
            with st.expander("Bio-Factors (Optional)"):
                weight = st.number_input("Weight (kg)", 30, 200, 70)
                sex = st.selectbox("Sex", ["Male", "Female", "Other"])

            if st.form_submit_button("Submit & Sync"):
                locs = [l for l, v in zip(["Upper Back", "Shoulders", "Chest", "Quads", "Hamstrings", "Calves"], [s1, s2, s3, s4, s5, s6]) if v]
                new = pd.DataFrame({'User_ID': [st.session_state.user], 'Timestamp': [datetime.now()], 'HR': [hr], 'RMSSD': [hrv], 
                                    'Soreness': [s_val], 'Location': [", ".join(locs) if locs else "None"], 'Weight': [weight], 'Sex': [sex]})
                df = pd.concat([df, new], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("Measurement Recorded!")
                st.rerun()

# --- DASHBOARD LOGIC ---
if st.session_state.role == "student":
    u_df = df[df['User_ID'] == st.session_state.user].copy()
    if not u_df.empty:
        baseline = u_df['RMSSD'].mean()
        std_v = u_df['RMSSD'].std() if len(u_df) > 1 else 10
        latest = u_df['RMSSD'].iloc[-1]
        z = (latest - baseline) / std_v if std_v != 0 else 0
        
        if z > -0.5: st.success("🟢 **READY:** Optimal recovery. Baseline stable.")
        elif z > -1.5: st.warning("🟡 **CAUTION:** Moderate deviation. Consider active recovery.")
        else: st.error("🔴 **REST:** Large deviation detected. Significant cardiovascular strain.")

        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("Readiness Gauge")
            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta", value=latest, delta={'reference': baseline},
                gauge={'axis': {'range': [0, 150]}, 'bar': {'color': "black", 'thickness': 0.2},
                       'steps': [{'range': [0, max(0, baseline - 1.5*std_v)], 'color': "#ff4b4b"},
                                 {'range': [max(0, baseline - 1.5*std_v), max(0, baseline - 0.5*std_v)], 'color': "#ffff00"},
                                 {'range': [max(0, baseline - 0.5*std_v), 150], 'color': "#00cc96"}]}))
            st.plotly_chart(fig, use_container_width=True)
            
        with col2:
            st.subheader("Trends")
            plot_df = u_df.tail(10).copy()
            plot_df['Personal_Baseline'] = baseline
            st.line_chart(plot_df.set_index('Timestamp')[['RMSSD', 'Personal_Baseline']])
    else: 
        st.info("Perform a 60s scan to establish your recovery baseline.")

elif st.session_state.role == "admin":
    st.title("👑 Coach Administration Panel")
    if not df.empty:
        st.metric("Active Students", df['User_ID'].nunique())
        st.subheader("Team Readiness Leaderboard")
        st.dataframe(df.sort_values('Timestamp', ascending=False), use_container_width=True)
        st.download_button("Export CSV", df.to_csv(index=False), "readiness_export.csv")

