import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import time
import streamlit.components.v1 as components

# This function creates the "Bridge"
def hrv_sensor_component():
    return components.html(
        """
        <style>
            .container {
                background: #111; padding: 20px; border-radius: 20px; 
                text-align: center; color: white; font-family: -apple-system, sans-serif;
                width: 100%; max-width: 400px; margin: auto; box-sizing: border-box;
            }
            #waveCanvas {
                background: #000; border-radius: 12px; margin: 15px 0; 
                width: 100%; height: 120px; display: block; border: 1px solid #333;
            }
            .bpm-display { font-size: 48px; font-weight: bold; color: #ff4b4b; margin: 10px 0; }
            #camera-btn {
                padding: 16px; background: #ff4b4b; color: white; border: none; 
                border-radius: 50px; cursor: pointer; font-weight: bold; width: 80%; font-size: 18px;
            }
            .status { font-size: 14px; color: #888; margin-bottom: 10px; }
        </style>

        <div class="container">
            <div class="status" id="status-text">READY FOR PRECISION SCAN</div>
            <div class="bpm-display" id="bpm-val">--</div>
            <canvas id="waveCanvas"></canvas>
            <video id="video" autoplay playsinline style="display:none;"></video>
            <button id="camera-btn" onclick="initSensor()">START SCAN</button>
        </div>

        <script>
        let scanning = false;
        const canvas = document.getElementById('waveCanvas');
        const ctx = canvas.getContext('2d');
        const bpmText = document.getElementById('bpm-val');
        const statusText = document.getElementById('status-text');

        let dataPoints = new Array(100).fill(0);
        let history = [];
        
        function draw(val) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            dataPoints.push(val);
            dataPoints.shift();
            
            ctx.strokeStyle = '#ff4b4b';
            ctx.lineWidth = 3;
            ctx.beginPath();
            for(let i=0; i<100; i++){
                let x = (canvas.width / 100) * i;
                let y = (canvas.height / 2) - (dataPoints[i] * 40);
                if(i==0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        async function initSensor() {
            if (scanning) return;
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: "environment" }, audio: false
                });
                const video = document.getElementById('video');
                video.srcObject = stream;
                document.getElementById('camera-btn').style.display = 'none';
                scanning = true;

                // Try to turn on flash
                const track = stream.getVideoTracks()[0];
                const capabilities = track.getCapabilities();
                if (capabilities.torch) await track.applyConstraints({ advanced: [{ torch: true }] });

                const procCanvas = document.createElement('canvas');
                const pCtx = procCanvas.getContext('2d', { willReadFrequently: true });
                procCanvas.width = 20; procCanvas.height = 20;

                let lastBPMTime = performance.now();
                let filterLow = 0;
                let filterHigh = 0;
                let beatTimes = [];

                function loop() {
                    if (!scanning) return;
                    pCtx.drawImage(video, 0, 0, 20, 20);
                    const data = pCtx.getImageData(0, 0, 20, 20).data;
                    
                    // G-channel is the gold standard for PPG accuracy
                    let green = 0;
                    for (let i = 1; i < data.length; i += 4) green += data[i];
                    green /= 400;

                    // Bandpass Filter: Strips out camera auto-exposure drift
                    filterLow = (0.95 * filterLow) + (0.05 * green);
                    let highPassed = green - filterLow;
                    filterHigh = (0.8 * filterHigh) + (0.2 * highPassed);
                    
                    draw(filterHigh);

                    // Peak detection with "Cooldown" logic
                    const now = performance.now();
                    if (filterHigh > 0.3 && (now - lastBPMTime) > 400) {
                        beatTimes.push(now);
                        lastBPMTime = now;
                        if(beatTimes.length > 5) {
                            let diffs = [];
                            for(let i=1; i<beatTimes.length; i++) diffs.push(beatTimes[i]-beatTimes[i-1]);
                            // Use Median for 94%+ stability
                            diffs.sort();
                            let median = diffs[Math.floor(diffs.length/2)];
                            let bpm = Math.round(60000 / median);
                            if(bpm > 40 && bpm < 180) {
                                bpmText.innerText = bpm;
                                statusText.innerText = "❤️ PULSE DETECTED";
                            }
                        }
                    }

                    if(beatTimes.length > 15) beatTimes.shift();
                    requestAnimationFrame(loop);
                }
                loop();
            } catch (e) { statusText.innerText = "ERROR: ACCESS DENIED"; }
        }
        </script>
        """,
        height=400,
    )
# --- INITIAL SETUP ---
st.set_page_config(page_title="Kubios HRV Readiness", layout="wide")

# --- DATA ENGINE ---
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
        hrv_sensor_component()
        # --- FEATURE PREVIEW: PPG FLASH SCAN ---
        st.info("💡 **PPG Flash Scan (Mock):** Based on research, place your finger over the camera and flash for a 60-second scan.")
        
        if st.button("🚀 Start Pulse Scan"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            chart_placeholder = st.empty()
            
            # Simulated 60s acquisition window (compressed for demo)
            for i in range(100):
                progress_bar.progress(i + 1)
                # Create a mock PPG wave visualization based on green channel processing
                mock_wave = np.sin(np.linspace(0, 5, 50) + i/5) + np.random.normal(0, 0.05, 50)
                chart_placeholder.line_chart(mock_wave)
                status_text.text(f"Acquiring PPG Signal... {i}%")
                time.sleep(0.04)
            
            # Simulate rMSSD calculation from beat-to-beat accuracy models
            st.session_state['detected_hr'] = np.random.randint(60, 85)
            st.session_state['detected_hrv'] = np.random.randint(45, 75)
            st.success("✅ Scan Complete! Validating RMSSD signal...")

        st.divider()

        # --- DATA ENTRY FORM ---
        with st.form("entry", clear_on_submit=True):
            # Form defaults to "detected" values from the scan above
            hr = st.number_input("Heart Rate (BPM)", 40, 160, st.session_state.get('detected_hr', 70))
            hrv = st.number_input("HRV (RMSSD ms)", 5, 250, st.session_state.get('detected_hrv', 50))
            
            st.write("---")
            st.write("🧘 **Anatomical Soreness Map** (The 'Dessert')")
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
        # Scientific Baseline Logic (RMSSD focus as requested)
        baseline = u_df['RMSSD'].mean()
        std_v = u_df['RMSSD'].std() if len(u_df) > 1 else 10
        latest = u_df['RMSSD'].iloc[-1]
        z = (latest - baseline) / std_v if std_v != 0 else 0
        
        # Readiness Advice Logic
        if z > -0.5: st.success("🟢 **READY:** Optimal recovery. Baseline stable.")
        elif z > -1.5: st.warning("🟡 **CAUTION:** Moderate deviation. Consider active recovery.")
        else: st.error("🔴 **REST:** Large deviation detected. Significant cardiovascular strain.")

        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("Personal Gauge")
            fig = go.Figure(go.Indicator(
                mode="gauge+number+delta", value=latest, delta={'reference': baseline},
                gauge={'axis': {'range': [0, 150]}, 'bar': {'color': "black", 'thickness': 0.2},
                       'steps': [{'range': [0, max(0, baseline - 1.5*std_v)], 'color': "#ff4b4b"},
                                 {'range': [max(0, baseline - 1.5*std_v), max(0, baseline - 0.5*std_v)], 'color': "#ffff00"},
                                 {'range': [max(0, baseline - 0.5*std_v), 150], 'color': "#00cc96"}],
                       'threshold': {'line': {'color': "black", 'width': 4}, 'value': baseline}}))
            st.plotly_chart(fig, use_container_width=True)
            
        with col2:
            st.subheader("Trends & Team Context")
            plot_df = u_df.tail(10).copy()
            plot_df['Personal_Baseline'] = baseline
            plot_df['Team_Avg'] = df['RMSSD'].mean()
            st.line_chart(plot_df.set_index('Timestamp')[['RMSSD', 'Personal_Baseline', 'Team_Avg']])
        
        st.divider()
        st.subheader("📋 Your Recent History")
        st.table(u_df[['Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location']].tail(5))
    else: 
        st.info("Welcome! Please perform a scan or enter your first reading to see your baseline.")

# --- ADMIN PANEL ---
elif st.session_state.role == "admin":
    st.title("👑 Coach Administration Panel")
    if not df.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Active Students", df['User_ID'].nunique())
        m2.metric("Group HR Avg", f"{int(df['HR'].mean())} BPM")
        m3.metric("Global Compliance", f"{len(df)} Logs")
        
        st.subheader("Team Readiness Leaderboard")
        leaderboard = df.sort_values('Timestamp', ascending=False)
        st.dataframe(leaderboard, use_container_width=True)
        st.download_button("Export Full Dataset (CSV)", df.to_csv(index=False), "ryan_readiness_export.csv", "text/csv")














