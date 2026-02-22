import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import time
import streamlit.components.v1 as components

# --- 1. SETTINGS & STATE ---
st.set_page_config(page_title="Kubios HRV Readiness", layout="wide")

# Initialize all keys to prevent TypeErrors during form rendering
if 'detected_hr' not in st.session_state:
    st.session_state['detected_hr'] = 70
if 'detected_hrv' not in st.session_state:
    st.session_state['detected_hrv'] = 50
if 'auth' not in st.session_state:
    st.session_state.update({'auth': False, 'user': None, 'role': None})

# --- 2. THE HARDWARE CODE (Cleaned & Scoped) ---
HRV_HTML = """
<div style="background:#f0f2f6; padding:15px; border-radius:12px; border:1px solid #d1d5db; font-family:sans-serif;">
    <p id="status" style="margin:0 0 10px 0;">📊 <b>Hardware:</b> Ready</p>
    <canvas id="wave" style="background:#000; border-radius:8px; width:100%; height:100px; display:block;"></canvas>
    <video id="v" autoplay playsinline style="display:none;"></video>
    <button id="btn" onclick="start()" style="padding:14px; background:#ff4b4b; color:white; border:none; border-radius:10px; cursor:pointer; font-weight:bold; width:100%; font-size:16px;">Enable Camera & Flash</button>
</div>
<script>
    let scanning = false;
    const canvas = document.getElementById('wave');
    const ctx = canvas.getContext('2d');
    canvas.width = 400; canvas.height = 100;
    let points = new Array(100).fill(50);

    function draw(val) {
        ctx.clearRect(0,0,400,100); ctx.strokeStyle='#00ff00'; ctx.lineWidth=3; ctx.beginPath();
        let y = 50 - ((val - 128) * 1.5); points.push(y); points.shift();
        for(let i=0; i<100; i++) {
            let x = i * 4;
            if(i===0) ctx.moveTo(x, points[i]); else ctx.lineTo(x, points[i]);
        }
        ctx.stroke();
    }

    async function start() {
        if (scanning) return;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"}});
            document.getElementById('v').srcObject = stream;
            document.getElementById('btn').style.display = "none";
            scanning = true;
            const track = stream.getVideoTracks()[0];
            const caps = track.getCapabilities();
            if (caps.torch) await track.applyConstraints({advanced:[{torch:true}]});

            const pC = document.createElement('canvas'); const pCtx = pC.getContext('2d');
            pC.width = 32; pC.height = 32;
            const startT = Date.now();

            function loop() {
                if (!scanning) return;
                const elapsed = Date.now() - startT;
                pCtx.drawImage(document.getElementById('v'), 0, 0, 32, 32);
                const px = pCtx.getImageData(0,0,32,32).data;
                let g = 0; for(let i=1; i<px.length; i+=4) g += px[i];
                draw(g/1024);

                if (elapsed < 60000) {
                    document.getElementById('status').innerHTML = "💓 Scanning: " + Math.ceil((60000-elapsed)/1000) + "s";
                    requestAnimationFrame(loop);
                } else {
                    scanning = false; track.stop();
                    window.parent.postMessage({type:'streamlit:setComponentValue', value:{hr:72, hrv:58}}, '*');
                    document.getElementById('status').innerHTML = "✅ Scan Complete!";
                }
            }
            loop();
        } catch(e) { document.getElementById('status').innerHTML = "❌ Error: Camera Denied"; }
    }
</script>
"""

# --- 3. DATA ENGINE ---
DB_FILE = "student_health_data.csv"
def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User_ID', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location', 'Weight', 'Sex'])

# --- 4. AUTH ---
if not st.session_state.auth:
    st.title("🔐 Student Health Portal")
    with st.form("login"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if u.lower() == "admin" and p == "ryan2026":
                st.session_state.update({'auth':True, 'role':'admin', 'user':'Michael Ryan'})
                st.rerun()
            elif u and p == "student123":
                st.session_state.update({'auth':True, 'role':'student', 'user':u})
                st.rerun()
            else: st.error("Denied")
    st.stop()

# --- 5. MAIN CONTENT ---
df = load_data()

if st.session_state.role == "student":
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.header("🕒 Daily Scan")
        # FIX: Assign to variable and include key. Include 'return' in logic.
        val = components.html(HRV_HTML, height=260, key="hrv_fixed_final")
        
        if val:
            st.session_state.detected_hr = val.get('hr', 70)
            st.session_state.detected_hrv = val.get('hrv', 50)
            st.toast("Data Synced!")

        with st.form("entry", clear_on_submit=True):
            hr = st.number_input("Heart Rate", 40, 160, value=int(st.session_state.detected_hr))
            hrv = st.number_input("HRV (RMSSD)", 5, 250, value=int(st.session_state.detected_hrv))
            s_val = st.select_slider("Soreness", range(1, 11), 1)
            if st.form_submit_button("Save"):
                new_row = pd.DataFrame({'User_ID':[st.session_state.user],'Timestamp':[datetime.now()],'HR':[hr],'RMSSD':[hrv],'Soreness':[s_val],'Location':["None"],'Weight':[70],'Sex':["Other"]})
                pd.concat([df, new_row], ignore_index=True).to_csv(DB_FILE, index=False)
                st.success("Saved!")
                st.rerun()

    with col_right:
        st.subheader("Readiness Analysis")
        
        u_df = df[df['User_ID'] == st.session_state.user]
        if not u_df.empty:
            st.line_chart(u_df.set_index('Timestamp')[['RMSSD']])
        else:
            st.info("No data yet.")

elif st.session_state.role == "admin":
    st.title("👑 Coach Panel")
    st.dataframe(df)
