import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# --- 1. INITIAL SETUP & PERSISTENCE ---
st.set_page_config(page_title="Kubios HRV Replica", layout="wide")
DB_FILE = "student_readiness_data.csv"

# Initialize Session State
if 'auth' not in st.session_state:
    st.session_state.update({
        'auth': False, 'user': None, 'role': None,
        'hr': 0, 'hrv': 0, 'sync_id': 0
    })

def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User', 'Timestamp', 'HR', 'HRV', 'Soreness', 'Weight', 'Sex'])

# --- 2. AUTHENTICATION ---
if not st.session_state.auth:
    st.title("🔐 Athlete Portal Login")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        r = st.selectbox("Role", ["Student", "Admin"])
        if st.form_submit_button("Login"):
            st.session_state.update({'auth': True, 'user': u, 'role': r})
            st.rerun()
    st.stop()

# --- 3. THE PPG SENSOR BRIDGE ---
def hrv_sensor_bridge():
    # JavaScript sends a message to Python using window.parent.postMessage
    components.html(
        """
        <div style="background:#111; color:white; padding:20px; border-radius:15px; text-align:center; font-family:sans-serif; border:2px solid #333;">
            <div id="status" style="color:#00ff00; font-weight:bold; margin-bottom:10px;">SYSTEM: STANDBY</div>
            <canvas id="wave" width="300" height="80" style="width:100%; height:80px; background:#000; border-radius:5px;"></canvas>
            <video id="v" width="1" height="1" style="opacity:0;" autoplay playsinline></video>
            <button id="btn" onclick="start()" style="width:100%; padding:15px; background:#ff4b4b; color:white; border:none; border-radius:8px; cursor:pointer; font-weight:bold;">START 60s MEASUREMENT</button>
        </div>
        <script>
            let samples = [], times = [], active = false;
            const canvas = document.getElementById('wave'), ctx = canvas.getContext('2d');

            async function start() {
                const stream = await navigator.mediaDevices.getUserMedia({video: {facingMode:'environment'}});
                const v = document.getElementById('v'); v.srcObject = stream;
                const track = stream.getVideoTracks()[0];
                try { await track.applyConstraints({advanced:[{torch:true}]}); } catch(e){}
                
                document.getElementById('btn').style.display='none';
                active = true; const startT = Date.now();
                const pCanvas = document.createElement('canvas'); const pCtx = pCanvas.getContext('2d');
                pCanvas.width=10; pCanvas.height=10;

                const loop = () => {
                    if(!active) return;
                    pCtx.drawImage(v,0,0,10,10);
                    const d = pCtx.getImageData(0,0,10,10).data;
                    let g = 0; for(let i=1; i<d.length; i+=4) g+=d[i];
                    samples.push(g/100); times.push(Date.now());

                    ctx.fillStyle='#000'; ctx.fillRect(0,0,300,80);
                    ctx.strokeStyle='#00ff00'; ctx.lineWidth=2; ctx.beginPath();
                    for(let i=0; i<100; i++) {
                        let y = 40 + (samples[samples.length-100+i] - samples[samples.length-1])*5;
                        ctx.lineTo(i*3, y || 40);
                    }
                    ctx.stroke();

                    if(Date.now() - startT < 60000) {
                        document.getElementById('status').innerText = "🔴 ANALYZING: " + Math.ceil((60000-(Date.now()-startT))/1000) + "s";
                        requestAnimationFrame(loop);
                    } else {
                        active = false; track.stop();
                        calculate();
                    }
                };
                loop();
            }

            function calculate() {
                let peaks = [];
                for(let i=2; i<samples.length-2; i++){
                    if(samples[i]<samples[i-1] && samples[i]<samples[i+1]) peaks.push(times[i]);
                }
                let rr = [];
                for(let i=1; i<peaks.length; i++){
                    let d = peaks[i]-peaks[i-1]; 
                    if(d > 400 && d < 1300) rr.push(d); // Valid physiological range
                }
                const hr = Math.round(60000/(rr.reduce((a,b)=>a+b,0)/rr.length));
                let dSq = 0; for(let i=1; i<rr.length; i++) dSq += Math.pow(rr[i]-rr[i-1], 2);
                const rmssd = Math.round(Math.sqrt(dSq/(rr.length-1)));

                // THE SYNC: Sending data to Python
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue', 
                    value: {hr: hr, hrv: rmssd, sid: Date.now()}
                }, '*');
                document.getElementById('status').innerText = "✅ SYNCED TO DASHBOARD";
            }
        </script>
        """, height=280
    )

# --- 4. DATA ENGINE & DASHBOARD ---
df = load_data()

if st.session_state.role == "Student":
    st.title(f"Athlete Dashboard: {st.session_state.user}")
    
    col_sensor, col_form = st.columns([1, 1.2])
    
    with col_sensor:
        st.subheader("1. Pulse Acquisition")
        # Capture the data from the HTML/JS component
        raw_data = hrv_sensor_bridge()
        
        # Check if new data has arrived by comparing sync IDs
        if raw_data and 'sid' in raw_data:
            if raw_data['sid'] > st.session_state.sync_id:
                st.session_state.hr = raw_data['hr']
                st.session_state.hrv = raw_data['hrv']
                st.session_state.sync_id = raw_data['sid']
                st.rerun() # Force the app to update the form below

    with col_form:
        st.subheader("2. Daily Readiness Form")
        with st.form("entry_log"):
            # These values now auto-populate from the sensor sync
            c1, c2 = st.columns(2)
            hr_final = c1.number_input("Heart Rate (BPM)", value=int(st.session_state.hr))
            hrv_final = c2.number_input("HRV (RMSSD)", value=int(st.session_state.hrv))
            
            soreness = st.select_slider("Muscle Soreness (1-10)", options=range(1, 11))
            
            
            
            st.divider()
            weight = st.number_input("Current Weight (kg)", 40, 150, 70)
            sex = st.selectbox("Sex", ["Male", "Female"])
            
            if st.form_submit_button("Submit & Save Measurement"):
                new_entry = pd.DataFrame({
                    'User': [st.session_state.user], 'Timestamp': [datetime.now()],
                    'HR': [hr_final], 'HRV': [hrv_final], 'Soreness': [soreness],
                    'Weight': [weight], 'Sex': [sex]
                })
                df = pd.concat([df, new_entry], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("Measurement Recorded with Timestamp!")
                st.rerun()

    # --- TRENDS & GAUGE ---
    st.divider()
    user_df = df[df['User'] == st.session_state.user]
    
    if len(user_df) >= 3:
        avg_hrv = user_df['HRV'].mean()
        std_hrv = user_df['HRV'].std() if len(user_df) > 1 else 10
        latest = user_df['HRV'].iloc[-1]
        
        g1, g2 = st.columns([1, 2])
        with g1:
            st.subheader("Kubios Readiness Gauge")
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=latest,
                gauge={'axis': {'range': [20, 120]}, 'bar': {'color': "black"},
                       'steps': [
                           {'range': [0, avg_hrv - 1.5*std_hrv], 'color': "#ff4b4b"}, # Red
                           {'range': [avg_hrv - 1.5*std_hrv, avg_hrv - 0.5*std_hrv], 'color': "#ffff00"}, # Yellow
                           {'range': [avg_hrv - 0.5*std_hrv, 120], 'color': "#00cc96"}]})) # Green
            st.plotly_chart(fig, use_container_width=True)
            
        with g2:
            st.subheader("Cardiovascular Trends")
            st.line_chart(user_df.set_index('Timestamp')[['HRV', 'HR']])
    else:
        st.info("📊 Establishing baseline... Please complete 3 measurements.")

# --- ADMIN VIEW ---
else:
    st.title("🏟️ Administrator Overview")
    if not df.empty:
        st.subheader("Team Compliance Log")
        # Shows exact timestamps as requested
        st.dataframe(df.sort_values(by='Timestamp', ascending=False), use_container_width=True)
        
        st.subheader("Group Analytics")
        st.bar_chart(df.groupby('User')['HRV'].mean())
        
        st.download_button("Export Dataset (CSV)", df.to_csv(index=False), "readiness_export.csv")
