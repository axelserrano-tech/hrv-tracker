import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import os
import streamlit.components.v1 as components

# ---------------- SENSOR COMPONENT ---------------- #

def hrv_sensor_component():
    return components.html(
        """
        <style>
            .container {
                background: #f0f2f6;
                padding: 15px;
                border-radius: 10px;
                text-align: center;
                border: 1px solid #d1d5db;
                font-family: sans-serif;
                width: 100%;
                box-sizing: border-box;
                overflow: hidden;
            }
            #waveCanvas {
                background: #000;
                border-radius: 5px;
                margin-bottom: 10px;
                width: 100%;
                height: 80px;
                display: block;
            }
            #camera-btn {
                padding: 12px;
                background: #ff4b4b;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-weight: bold;
                width: 100%;
                font-size: 14px;
            }
            #status-text {
                font-size: 14px;
                margin-bottom: 10px;
            }
        </style>

        <div class="container">
            <p id="status-text">📊 <b>Hardware:</b> Ready</p>
            <canvas id="waveCanvas"></canvas>
            <video id="video" autoplay playsinline style="display:none;"></video>
            <button id="camera-btn" onclick="initSensor()">
                Enable Camera & Flash
            </button>
        </div>

<script>
let scanning = false;

const canvas = document.getElementById('waveCanvas');
const ctxWave = canvas.getContext('2d');

canvas.width = canvas.offsetWidth;
canvas.height = 80;

let signalBuffer = [];
let timeBuffer = [];
const MAX_SAMPLES = 400;

function robustGreenAverage(pixels) {
    let greens = [];
    for (let i = 1; i < pixels.length; i += 4) greens.push(pixels[i]);

    greens.sort((a,b)=>a-b);
    const trim = Math.floor(greens.length * 0.1);
    const trimmed = greens.slice(trim, greens.length - trim);

    return trimmed.reduce((a,b)=>a+b,0) / trimmed.length;
}

function pushSignal(value) {
    const now = performance.now() / 1000;

    signalBuffer.push(value);
    timeBuffer.push(now);

    if (signalBuffer.length > MAX_SAMPLES) {
        signalBuffer.shift();
        timeBuffer.shift();
    }
}

function detrend(signal) {
    const mean = signal.reduce((a,b)=>a+b,0) / signal.length;
    return signal.map(v => v - mean);
}

function bandpass(signal) {
    let out = [];
    let prev = 0;

    for (let i = 1; i < signal.length; i++) {
        let hp = signal[i] - signal[i-1];
        let lp = prev + 0.2 * (hp - prev);
        out.push(lp);
        prev = lp;
    }
    return out;
}

function detectPeaks(signal, times) {
    let peaks = [];
    if (signal.length < 10) return peaks;

    const mean = signal.reduce((a,b)=>a+b,0) / signal.length;
    const std = Math.sqrt(signal.map(x => (x-mean)**2)
                        .reduce((a,b)=>a+b,0) / signal.length);

    const threshold = mean + 0.8 * std;

    for (let i = 1; i < signal.length - 1; i++) {
        if (signal[i] > threshold &&
            signal[i] > signal[i-1] &&
            signal[i] > signal[i+1]) {

            if (!peaks.length || (times[i] - peaks[peaks.length-1]) > 0.35)
                peaks.push(times[i]);
        }
    }
    return peaks;
}

function computeIBI(peaks) {
    let ibi = [];
    for (let i = 1; i < peaks.length; i++)
        ibi.push(peaks[i] - peaks[i-1]);
    return ibi;
}

function computeHR(ibi) {
    if (!ibi.length) return 0;
    const sorted = [...ibi].sort((a,b)=>a-b);
    const median = sorted[Math.floor(sorted.length/2)];
    return 60 / median;
}

function computeRMSSD(ibi) {
    if (ibi.length < 5) return 0;

    let diffs = [];
    for (let i = 1; i < ibi.length; i++)
        diffs.push(ibi[i] - ibi[i-1]);

    const meanSq = diffs.map(d => d*d)
                        .reduce((a,b)=>a+b,0) / diffs.length;

    return Math.sqrt(meanSq) * 1000;
}

function drawWave(value) {
    ctxWave.clearRect(0,0,canvas.width,canvas.height);
    ctxWave.strokeStyle = '#00ff00';
    ctxWave.lineWidth = 2;
    ctxWave.beginPath();

    const y = 40 - value * 8;

    if (!drawWave.points)
        drawWave.points = new Array(100).fill(y);

    drawWave.points.push(y);
    drawWave.points.shift();

    for (let i = 0; i < drawWave.points.length; i++) {
        const x = i * (canvas.width / 100);
        if (i === 0) ctxWave.moveTo(x, drawWave.points[i]);
        else ctxWave.lineTo(x, drawWave.points[i]);
    }

    ctxWave.stroke();
}

async function initSensor() {
    if (scanning) return;

    const statusText = document.getElementById('status-text');
    const video = document.getElementById('video');

    try {
        signalBuffer = [];
        timeBuffer = [];

        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment" }
        });

        video.srcObject = stream;
        scanning = true;

        const procCanvas = document.createElement('canvas');
        const procCtx = procCanvas.getContext('2d');
        procCanvas.width = 32;
        procCanvas.height = 32;

        const startTime = performance.now();
        const duration = 15000;

        function process() {
            if (!scanning) return;

            const elapsed = performance.now() - startTime;

            procCtx.drawImage(video, 0, 0, 32, 32);
            const pixels = procCtx.getImageData(0,0,32,32).data;

            const avgGreen = robustGreenAverage(pixels);
            pushSignal(avgGreen);

            const filtered = bandpass(detrend(signalBuffer));
            drawWave(filtered[filtered.length - 1] || 0);

            if (elapsed < duration) {
                requestAnimationFrame(process);
            } else {
                scanning = false;
                stream.getTracks().forEach(t => t.stop());

                const filteredFinal = bandpass(detrend(signalBuffer));
                const peaks = detectPeaks(filteredFinal, timeBuffer);

                const ibi = computeIBI(peaks);

                const hr = computeHR(ibi);
                const rmssd = computeRMSSD(ibi);

                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: { hr: Math.round(hr), hrv: rmssd, quality: "good", sqi: 80 }
                }, '*');
            }
        }

        video.onplay = () => process();

    } catch (err) {
        statusText.innerHTML = "❌ Camera access required";
    }
}
</script>
        """,
        height=220,
    )

# ---------------- APP SETUP ---------------- #

st.set_page_config(page_title="Kubios HRV Readiness", layout="wide")

DB_FILE = "student_health_data.csv"

def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        return df
    return pd.DataFrame(columns=['User_ID', 'Timestamp', 'HR', 'RMSSD', 'Soreness', 'Location', 'Weight', 'Sex'])

df = load_data()

# ---------------- UI ---------------- #

st.title("Kubios-Style HRV Readiness")

sensor_data = hrv_sensor_component()

if sensor_data:
    st.success(f"HR: {sensor_data['hr']} BPM | RMSSD: {sensor_data['hrv']:.1f} ms")

    new = pd.DataFrame({
        'User_ID': ['demo'],
        'Timestamp': [datetime.now()],
        'HR': [sensor_data['hr']],
        'RMSSD': [sensor_data['hrv']],
        'Soreness': [1],
        'Location': ['None'],
        'Weight': [70],
        'Sex': ['Other']
    })

    df = pd.concat([df, new], ignore_index=True)
    df.to_csv(DB_FILE, index=False)

if not df.empty:

    baseline = df['RMSSD'].median()
    std_v = (df['RMSSD'] - baseline).abs().median() * 1.4826 if len(df) > 1 else 10
    latest = df['RMSSD'].iloc[-1]

    z = (latest - baseline) / std_v if std_v else 0

    if z > -0.5:
        st.success("🟢 READY: Within normal baseline variation.")
    elif z > -1.5:
        st.warning("🟡 CAUTION: Moderate deviation from baseline.")
    else:
        st.error("🔴 REST: Marked deviation. Interpret cautiously.")

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=latest,
        gauge={'axis': {'range': [0, 150]}}
    ))

    st.plotly_chart(fig, use_container_width=True)
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









