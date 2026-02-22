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
                background: #111; padding: 15px; border-radius: 15px; 
                text-align: center; color: white; font-family: sans-serif;
                width: 100%; max-width: 400px; margin: auto; box-sizing: border-box;
                border: 1px solid #333;
            }
            #waveCanvas {
                background: #000; border-radius: 10px; margin: 10px 0; 
                width: 100%; height: 120px; display: block;
            }
            .bpm-text { font-size: 48px; font-weight: 800; color: #00ff41; margin: 0; }
            #progress-bg { width: 100%; height: 6px; background: #333; border-radius: 3px; margin: 10px 0; overflow: hidden; }
            #progress-fill { width: 0%; height: 100%; background: #00ff41; transition: linear 1s; }
            #camera-btn {
                padding: 15px; background: #00ff41; color: black; border: none; 
                border-radius: 10px; cursor: pointer; font-weight: bold; width: 100%; font-size: 16px;
            }
        </style>

        <div class="container">
            <div id="status" style="font-size:12px; color: #888;">READY FOR 60s SCAN</div>
            <div class="bpm-text" id="bpm-val">--</div>
            <div id="progress-bg"><div id="progress-fill"></div></div>
            <canvas id="waveCanvas"></canvas>
            <video id="video" autoplay playsinline style="display:none;"></video>
            <button id="camera-btn" onclick="initSensor()">START 60s MEASUREMENT</button>
        </div>

        <script>
        let scanning = false;
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

                let startTime = performance.now();
                let lastBeat = 0;
                let lowPass = 0;

                function process() {
                    if (!scanning) return;
                    let now = performance.now();
                    let elapsed = (now - startTime) / 1000;

                    if (elapsed >= 60) {
                        scanning = false; track.stop();
                        // Final HRV RMSSD Calculation
                        let rr = [];
                        for(let i=1; i<beatTimes.length; i++) rr.push(beatTimes[i]-beatTimes[i-1]);
                        let diffSq = rr.slice(1).map((val, i) => Math.pow(val - rr[i], 2));
                        let rmssd = Math.sqrt(diffSq.reduce((a,b)=>a+b, 0) / diffSq.length);
                        
                        window.parent.postMessage({
                            type: 'streamlit:setComponentValue',
                            value: { hr: Math.round(60000 / (rr.reduce((a,b)=>a+b,0)/rr.length)), hrv: Math.round(rmssd) }
                        }, '*');
                        return;
                    }

                    document.getElementById('progress-fill').style.width = (elapsed/60*100) + "%";
                    pCtx.drawImage(video, 0, 0, 20, 20);
                    const pixels = pCtx.getImageData(0, 0, 20, 20).data;
                    let green = 0;
                    for (let i = 1; i < pixels.length; i += 4) green += pixels[i];
                    green /= 400;

                    lowPass = (0.9 * lowPass) + (0.1 * green);
                    let signal = green - lowPass;
                    draw(signal);

                    if (signal > 0.15 && (now - lastBeat) > 450) {
                        beatTimes.push(now);
                        if(beatTimes.length > 2) {
                            let instBPM = Math.round(60000 / (now - lastBeat));
                            document.getElementById('bpm-val').innerText = instBPM;
                        }
                        lastBeat = now;
                    }
                    requestAnimationFrame(process);
                }
                process();
            } catch (e) { alert("Camera Error"); }
        }
        </script>
        """,
        height=380,
    )

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
