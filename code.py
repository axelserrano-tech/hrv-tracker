import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os

# --- DATABASE CONFIG ---
DB_FILE = "readiness_data.csv"

def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User', 'Timestamp', 'HR', 'HRV', 'Soreness', 'Body_Part', 'Weight', 'Sex'])

# --- SESSION STATE INITIALIZATION ---
if 'auth' not in st.session_state:
    st.session_state.update({'auth': False, 'user': None, 'role': None, 'temp_hr': 0, 'temp_hrv': 0})

# --- LOGIN INTERFACE ---
if not st.session_state.auth:
    st.title("🛡️ Cardio Readiness Login")
    with st.form("login_gate"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        role = st.selectbox("I am a:", ["Student", "Administrator"])
        if st.form_submit_button("Enter Portal"):
            if u and p: # Simplified for prototype
                st.session_state.auth, st.session_state.user, st.session_state.role = True, u, role
                st.rerun()
    st.stop()

# --- THE HARDWARE BRIDGE (PPG SENSOR) ---
def pulse_sensor_component():
    # This component uses the Green-Channel light absorption method
    import streamlit.components.v1 as components
    components.html(
        """
        <div style="background:#111; color:white; padding:15px; border-radius:12px; text-align:center; font-family:sans-serif; border:2px solid #333;">
            <div id="status" style="color:#00ff00; font-weight:bold;">SYSTEM READY</div>
            <canvas id="pWave" width="300" height="80" style="width:100%; height:80px; background:#000; margin:10px 0; border-radius:5px;"></canvas>
            <video id="v" width="1" height="1" style="opacity:0;" autoplay playsinline></video>
            <button id="sBtn" onclick="startScan()" style="width:100%; padding:12px; background:#ff4b4b; color:white; border:none; border-radius:8px; cursor:pointer; font-weight:bold;">START 60s MEASUREMENT</button>
        </div>
        <script>
            let samples = [], times = [], active = false;
            const canvas = document.getElementById('pWave'), ctx = canvas.getContext('2d');

            async function startScan() {
                const stream = await navigator.mediaDevices.getUserMedia({video: {facingMode:'environment'}});
                const v = document.getElementById('v'); v.srcObject = stream;
                const track = stream.getVideoTracks()[0];
                try { await track.applyConstraints({advanced:[{torch:true}]}); } catch(e){}
                
                document.getElementById('sBtn').style.display='none';
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
                    ctx.strokeStyle='#00ff00'; ctx.beginPath();
                    for(let i=0; i<100; i++) {
                        let y = 40 + (samples[samples.length-100+i] - samples[samples.length-1])*5;
                        ctx.lineTo(i*3, y || 40);
                    }
                    ctx.stroke();

                    if(Date.now() - startT < 60000) {
                        document.getElementById('status').innerText = "🔴 RECORDING: " + Math.ceil((60000-(Date.now()-startT))/1000) + "s";
                        requestAnimationFrame(loop);
                    } else {
                        active = false; track.stop();
                        analyze();
                    }
                };
                loop();
            }

            function analyze() {
                let peaks = [];
                for(let i=2; i<samples.length-2; i++){
                    if(samples[i]<samples[i-1] && samples[i]<samples[i+1]) peaks.push(times[i]);
                }
                let rr = [];
                for(let i=1; i<peaks.length; i++){
                    let d = peaks[i]-peaks[i-1]; if(d>400 && d<1200) rr.push(d);
                }
                const hr = Math.round(60000/(rr.reduce((a,b)=>a+b,0)/rr.length));
                let dSq = 0; for(let i=1; i<rr.length; i++) dSq += Math.pow(rr[i]-rr[i-1], 2);
                const rmssd = Math.round(Math.sqrt(dSq/(rr.length-1)));

                window.parent.postMessage({type:'streamlit:setComponentValue', value:{hr:hr, hrv:rmssd, sync:Date.now()}}, '*');
                document.getElementById('status').innerText = "✅ DATA SYNCED";
            }
        </script>
        """, height=250
    )

# --- MAIN APP INTERFACE ---
df = load_data()

if st.session_state.role == "Student":
    st.title(f"Athlete Dashboard: {st.session_state.user}")
    
    col_left, col_right = st.columns([1, 1.5])
    
    with col_left:
        st.subheader("1. Pulse Acquisition")
        sensor_data = pulse_sensor_component()
        
        # Capture sensor data into Session State
        if sensor_data and 'sync' in sensor_data:
            st.session_state.temp_hr = sensor_data['hr']
            st.session_state.temp_hrv = sensor_data['hrv']

    with col_right:
        st.subheader("2. Wellness Input")
        with st.form("daily_form"):
            c1, c2 = st.columns(2)
            final_hr = c1.number_input("Heart Rate (BPM)", value=st.session_state.temp_hr)
            final_hrv = c2.number_input("HRV (RMSSD)", value=st.session_state.temp_hrv)
            
            soreness = st.select_slider("Muscle Soreness (1-10)", options=range(1,11))
            
            
            
            body_part = st.multiselect("Sore Areas:", ["Quads", "Hamstrings", "Calves", "Lower Back", "Shoulders", "Chest"])
            
            with st.expander("Bio-Factors"):
                w = st.number_input("Weight (kg)", 40, 150, 70)
                s = st.selectbox("Sex", ["Male", "Female"])
                
            if st.form_submit_button("Submit Measurement"):
                new_row = pd.DataFrame({
                    'User': [st.session_state.user], 'Timestamp': [datetime.now()],
                    'HR': [final_hr], 'HRV': [final_hrv], 'Soreness': [soreness],
                    'Body_Part': [", ".join(body_part)], 'Weight': [w], 'Sex': [s]
                })
                df = pd.concat([df, new_row], ignore_index=True)
                df.to_csv(DB_FILE, index=False)
                st.success("Log Updated!")
                st.rerun()

    # --- READINESS ANALYTICS ---
    st.divider()
    user_df = df[df['User'] == st.session_state.user]
    
    if len(user_df) >= 3:
        baseline = user_df['HRV'].mean()
        std_val = user_df['HRV'].std() if len(user_df) > 1 else 10
        latest = user_df['HRV'].iloc[-1]
        
        g_col, t_col = st.columns([1, 2])
        with g_col:
            st.subheader("Readiness Indicator")
            fig = go.Figure(go.Indicator(
                mode="gauge+number", value=latest,
                gauge={'axis': {'range': [20, 120]}, 'bar': {'color': "black"},
                       'steps': [
                           {'range': [0, baseline - 1.5*std_val], 'color': "#ff4b4b"},
                           {'range': [baseline - 1.5*std_val, baseline - 0.5*std_val], 'color': "#ffff00"},
                           {'range': [baseline - 0.5*std_val, 120], 'color': "#00cc96"}],
                       'threshold': {'line': {'color': "black", 'width': 4}, 'value': baseline}}))
            st.plotly_chart(fig, use_container_width=True)
        
        with t_col:
            st.subheader("Personal Trends")
            st.line_chart(user_df.set_index('Timestamp')[['HRV', 'HR']])
    else:
        st.info("📊 Establishing baseline... Please log 3 days of data.")

# --- ADMINISTRATOR PANEL ---
else:
    st.title("🏟️ Team Admin Dashboard")
    if not df.empty:
        st.subheader("Group Compliance Overview")
        # Timestamp visibility is automatic here
        st.dataframe(df.sort_values(by='Timestamp', ascending=False), use_container_width=True)
        
        st.subheader("Team Readiness (Last 24h)")
        avg_hrv = df.groupby('User')['HRV'].mean()
        st.bar_chart(avg_hrv)
        
        st.download_button("Export CSV Database", df.to_csv(index=False), "team_report.csv")
    else:
        st.warning("No student data available yet.")
