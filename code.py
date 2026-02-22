import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# --- 1. THE "PULSING UI" OPTICAL SENSOR ---
# Uses the camera/flash but hides the waveform, showing a live BPM and pulsing heart instead.
PULSE_SENSOR_HTML = """
<div style="background: #1e1e24; color: white; padding: 25px; border-radius: 15px; text-align: center; font-family: sans-serif; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
    <h3 style="margin:0 0 5px 0; color: #ff4b4b;">📸 Biometric Scan</h3>
    <p id="instruction" style="font-size: 14px; color: #aaa; margin-bottom: 20px;">Place finger firmly over the back camera and flash.</p>
    
    <div id="heart-container" style="font-size: 60px; transition: transform 0.1s ease-out; margin: 20px 0;">❤️</div>
    <div id="live-bpm" style="font-size: 32px; font-weight: bold; color: #00cc96; margin-bottom: 10px;">-- BPM</div>
    
    <video id="vid" width="10" height="10" style="display:none;" autoplay playsinline></video>
    <div style="width: 100%; background: #333; height: 8px; border-radius: 4px; overflow: hidden; margin-bottom: 15px;">
        <div id="progress" style="width: 0%; background: #ff4b4b; height: 100%;"></div>
    </div>
    
    <button id="start" onclick="startScan()" style="width:100%; padding:15px; background:#ff4b4b; border:none; color:white; border-radius:8px; font-weight:bold; cursor:pointer; font-size:16px;">START 60s MEASUREMENT</button>
</div>

<script>
let scanning = false;
let samples = [];
let times = [];
let lastPeakTime = 0;
let rrIntervals = [];

async function startScan() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'environment'}});
        const vid = document.getElementById('vid');
        vid.srcObject = stream;
        const track = stream.getVideoTracks()[0];
        try { await track.applyConstraints({advanced: [{torch: true}]}); } catch(e) {}
        
        document.getElementById('start').style.display = 'none';
        scanning = true;
        processVideo();
    } catch(e) { alert("Please allow camera access."); }
}

function processVideo() {
    const v = document.getElementById('vid');
    const hidden = document.createElement('canvas');
    hidden.width = 10; hidden.height = 10;
    const hCtx = hidden.getContext('2d', {alpha: false});
    
    const duration = 60000;
    const startT = Date.now();
    let recentSamples = [];

    const loop = () => {
        if(!scanning) return;
        const now = Date.now();
        const elapsed = now - startT;
        
        // 1. Extract Green Channel
        hCtx.drawImage(v, 0, 0, 10, 10);
        const data = hCtx.getImageData(0,0,10,10).data;
        let g = 0;
        for(let i=1; i<data.length; i+=4) g += data[i];
        const avgG = g / 100;
        
        samples.push(avgG);
        times.push(now);
        recentSamples.push(avgG);
        if(recentSamples.length > 30) recentSamples.shift();

        // 2. Real-time Peak Detection (For Live UI)
        if (recentSamples.length === 30) {
            const mid = recentSamples[15];
            const isLocalMin = recentSamples.every((val, idx) => idx === 15 || val > mid);
            
            if (isLocalMin && (now - lastPeakTime > 400)) { // Minimum 400ms between beats
                if (lastPeakTime > 0) {
                    const rr = now - lastPeakTime;
                    rrIntervals.push(rr);
                    if(rrIntervals.length > 5) rrIntervals.shift();
                    
                    // Update Live BPM
                    const avgRR = rrIntervals.reduce((a,b)=>a+b,0)/rrIntervals.length;
                    const liveHr = Math.round(60000 / avgRR);
                    if (liveHr > 40 && liveHr < 180) {
                        document.getElementById('live-bpm').innerText = liveHr + " BPM";
                    }
                }
                lastPeakTime = now;
                
                // Pulse Animation
                const heart = document.getElementById('heart-container');
                heart.style.transform = 'scale(1.3)';
                setTimeout(() => { heart.style.transform = 'scale(1)'; }, 150);
            }
        }

        // 3. Update Progress Bar
        document.getElementById('progress').style.width = (elapsed / duration * 100) + '%';

        if (elapsed < duration) {
            requestAnimationFrame(loop);
        } else {
            finishScan();
        }
    };
    requestAnimationFrame(loop);
}

function finishScan() {
    scanning = false;
    document.getElementById('instruction').innerHTML = "✅ <b>Scan Complete! Data transferred.</b>";
    document.getElementById('live-bpm').innerText = "DONE";
    
    // Post-Processing for RMSSD (HRV) and Final HR
    let peaks = [];
    for(let i=5; i<samples.length-5; i++) {
        let isMin = true;
        for(let j=-5; j<=5; j++) { if(i!==i+j && samples[i] > samples[i+j]) isMin = false; }
        if(isMin) peaks.push(times[i]);
    }
    
    let rr = [];
    for(let i=1; i<peaks.length; i++) rr.push(peaks[i] - peaks[i-1]);
    rr = rr.filter(x => x > 400 && x < 1400); // Filter artifacts
    
    if (rr.length < 10) {
        alert("Poor signal quality. Please try again holding finger still.");
        return;
    }
    
    const finalHr = Math.round(60000 / (rr.reduce((a,b)=>a+b,0)/rr.length));
    
    let diffSq = 0;
    for(let i=1; i<rr.length; i++) diffSq += Math.pow(rr[i] - rr[i-1], 2);
    const rmssd = Math.round(Math.sqrt(diffSq / (rr.length - 1)));

    window.parent.postMessage({type: 'streamlit:setComponentValue', value: {hr: finalHr, hrv: rmssd}}, '*');
}
</script>
"""

# --- 2. SETUP & DATA HANDLING ---
st.set_page_config(page_title="Cardio Readiness Portal", layout="wide")
DB_FILE = "readiness_db.csv"

if 'auth' not in st.session_state: st.session_state.update({'auth': False, 'user': None, 'role': None})
if 'scan_hr' not in st.session_state: st.session_state.scan_hr = 0
if 'scan_hrv' not in st.session_state: st.session_state.scan_hrv = 0

def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User', 'Role', 'Timestamp', 'HR', 'HRV', 'Soreness', 'Sore_Areas', 'Weight', 'Sex'])

df = load_data()

# --- 3. LOGIN SYSTEM ---
if not st.session_state.auth:
    st.title("🛡️ Cardiovascular Readiness Portal")
    with st.form("login_form"):
        username = st.text_input("Username")
        role = st.selectbox("Select Role", ["Student Athlete", "Administrator/Coach"])
        if st.form_submit_button("Login"):
            if username:
                st.session_state.auth = True
                st.session_state.user = username
                st.session_state.role = role
                st.rerun()
    st.stop()

# --- 4. SIDEBAR NAVIGATION ---
with st.sidebar:
    st.write(f"Logged in as: **{st.session_state.user}**")
    st.write(f"Role: {st.session_state.role}")
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()
    st.divider()
    st.info("Taking measurements daily upon waking yields the most reliable baseline.")

# ==========================================
# --- 5. STUDENT ATHLETE DASHBOARD ---
# ==========================================
if st.session_state.role == "Student Athlete":
    st.title(f"Welcome, {st.session_state.user}")
    
    col_sensor, col_form = st.columns([1, 1.2])
    
    with col_sensor:
        st.subheader("1. Morning Scan")
        result = components.html(PULSE_SENSOR_HTML, height=350)
        
        if result is not None and isinstance(result, dict):
            st.session_state.scan_hr = result.get('hr', 0)
            st.session_state.scan_hrv = result.get('hrv', 0)

    with col_form:
        st.subheader("2. Subjective Entry")
        with st.form("data_entry"):
            c1, c2 = st.columns(2)
            hr_input = c1.number_input("Heart Rate (BPM)", value=int(st.session_state.scan_hr))
            hrv_input = c2.number_input("HRV (rMSSD)", value=int(st.session_state.scan_hrv))
            
            st.write("---")
            soreness = st.select_slider("Overall Muscle Soreness", options=list(range(1, 11)), value=1, help="1 = Completely Fresh, 10 = Severe DOMS/Pain")
            
            
            areas = st.multiselect("Select Specific Sore Areas:", 
                                   ["None", "Quads", "Hamstrings", "Calves", "Lower Back", "Core", "Chest", "Shoulders/Arms"])
            areas_str = ", ".join(areas) if areas else "None"
            
            with st.expander("Bio-Factors (Optional Update)"):
                weight = st.number_input("Current Weight (kg)", 40, 150, 70)
                sex = st.selectbox("Sex (Biological)", ["Male", "Female", "Other"])
            
            if st.form_submit_button("Save Today's Data"):
                new_row = pd.DataFrame([[st.session_state.user, "Student", datetime.now(), hr_input, hrv_input, soreness, areas_str, weight, sex]], columns=df.columns)
                df = pd.concat([df, new_row], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("Measurement recorded successfully!")
                st.rerun()

    # --- READINESS & TRENDS ---
    st.divider()
    user_data = df[df['User'] == st.session_state.user].copy()
    
    if len(user_data) >= 3:
        st.header("📊 Your Readiness Baseline")
        
        # Calculations: 7-day rolling baseline
        recent_data = user_data.tail(7)
        baseline_hrv = recent_data['HRV'].mean()
        std_hrv = recent_data['HRV'].std() if len(recent_data) > 1 else 5
        latest_hrv = recent_data['HRV'].iloc[-1]
        latest_hr = recent_data['HR'].iloc[-1]
        baseline_hr = recent_data['HR'].mean()
        
        g_col, chart_col = st.columns([1, 2])
        
        with g_col:
            st.subheader("Kubios-Style Gauge")
            # Green = > Baseline - 0.5*StdDev
            # Yellow = > Baseline - 1.0*StdDev
            # Red = < Baseline - 1.0*StdDev
            fig = go.Figure(go.Indicator(
                mode = "gauge+number+delta",
                value = latest_hrv,
                delta = {'reference': baseline_hrv, 'position': "top"},
                title = {'text': "Readiness (rMSSD)"},
                gauge = {
                    'axis': {'range': [20, 120]},
                    'bar': {'color': "black"},
                    'steps': [
                        {'range': [0, baseline_hrv - std_hrv], 'color': "#ff4b4b"}, # Red
                        {'range': [baseline_hrv - std_hrv, baseline_hrv - (0.5*std_hrv)], 'color': "#ffea00"}, # Yellow
                        {'range': [baseline_hrv - (0.5*std_hrv), 120], 'color': "#00cc96"} # Green
                    ],
                    'threshold': {'line': {'color': "black", 'width': 3}, 'value': baseline_hrv}
                }
            ))
            st.plotly_chart(fig, use_container_width=True)
            
            st.metric("Resting Heart Rate", f"{latest_hr} BPM", f"{(latest_hr - baseline_hr):.1f} from baseline", delta_color="inverse")
            
        with chart_col:
            st.subheader("Long-Term Trends")
            chart_data = user_data.set_index('Timestamp')[['HRV', 'HR']]
            st.line_chart(chart_data)
            
            # Simple bar chart for subjective soreness
            st.bar_chart(user_data.set_index('Timestamp')['Soreness'], color="#ff4b4b")
            
    else:
        st.info("Collect at least 3 days of measurements to establish your rolling baseline and unlock the Readiness Gauge.")


# ==========================================
# --- 6. ADMINISTRATOR / COACH DASHBOARD ---
# ==========================================
elif st.session_state.role == "Administrator/Coach":
    st.title("🏟️ Team Administration Dashboard")
    
    if df.empty:
        st.info("No student data has been collected yet.")
    else:
        # Get latest entry for each user
        latest_df = df.sort_values('Timestamp').groupby('User').last().reset_index()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Active Athletes", len(latest_df))
        m2.metric("Team Average rMSSD", f"{latest_df['HRV'].mean():.1f} ms")
        m3.metric("Team Average HR", f"{latest_df['HR'].mean():.0f} BPM")
        
        st.subheader("Daily Team Readiness Overview")
        
        # Format Timestamp for clear visibility
        latest_df['Last Scan Time'] = latest_df['Timestamp'].dt.strftime('%Y-%m-%d %I:%M %p')
        
        # Calculate Deviation for each user
        def get_status(row):
            user_hist = df[df['User'] == row['User']].tail(7)
            if len(user_hist) < 3: return "Establishing Baseline"
            baseline = user_hist['HRV'].mean()
            std = user_hist['HRV'].std()
            if row['HRV'] < (baseline - std): return "High Strain (Red)"
            elif row['HRV'] < (baseline - 0.5*std): return "Moderate (Yellow)"
            else: return "Optimal (Green)"
            
        latest_df['Status'] = latest_df.apply(get_status, axis=1)
        
        # Display clean table
        display_cols = ['User', 'Last Scan Time', 'HR', 'HRV', 'Status', 'Soreness', 'Sore_Areas']
        st.dataframe(latest_df[display_cols], use_container_width=True, hide_index=True)
        
        st.subheader("Raw Data Export")
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Full CSV Database", data=csv, file_name="team_hrv_data.csv", mime="text/csv")
