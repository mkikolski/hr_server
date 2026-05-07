// HRV Biofeedback Control Panel JavaScript
const ws = new WebSocket(`ws://${location.host}/ws/panel`);

// UI Elements
const indPolar = document.getElementById('ind-polar');
const indHeadset = document.getElementById('ind-headset');
const sysLog = document.getElementById('sys-log');
const steps = document.querySelectorAll('.step');
const elapsedTimeEl = document.getElementById('time-elapsed');
const totalTimeEl = document.getElementById('time-total');
const hrValueEl = document.getElementById('hr-value');
const rmssdEl = document.getElementById('rmssd-value');
const sdnnEl = document.getElementById('sdnn-value');
const heartIcon = document.querySelector('.heart-icon');
const btnAction = document.getElementById('btn-action');
const btnSkip = document.getElementById('btn-skip');
const btnStop = document.getElementById('btn-stop');
const therapyControls = document.getElementById('therapy-controls');
const btnBirds = document.getElementById('btn-birds');
const btnRestartSession = document.getElementById('btn-restart-session');
const resBaseline = document.getElementById('res-baseline');
const resFreq = document.getElementById('res-freq');
const resRate = document.getElementById('res-rate');
const hrvSegmentsCont = document.getElementById('hrv-segments-container');
const hrvSegmentsList = document.getElementById('hrv-segments-list');

// HR Chart
const chartCanvas = document.getElementById('hr-chart');
const ctx = chartCanvas.getContext('2d');
let hrHistory = [];
const maxDataPoints = 60;

// HRV Chart
const hrvCardEl = document.getElementById('hrv-card');
const hrvChartCanvas = document.getElementById('hrv-chart');
const hrvCtx = hrvChartCanvas.getContext('2d');
const hrvMaxEl = document.getElementById('hrv-max-value');
const hrvMinEl = document.getElementById('hrv-min-value');
let rmssdHistory = [];

// State management
let currentState = 'IDLE';

// Resize both canvases
function resizeCanvas() {
    chartCanvas.width = chartCanvas.parentElement.clientWidth;
    chartCanvas.height = chartCanvas.parentElement.clientHeight;
    hrvChartCanvas.width = hrvChartCanvas.parentElement.clientWidth;
    hrvChartCanvas.height = hrvChartCanvas.parentElement.clientHeight;
    drawChart();
    drawHrvChart();
}
window.addEventListener('resize', resizeCanvas);

function logMsg(msg) {
    const d = new Date();
    const timeStr = d.toLocaleTimeString([], { hour12: false });
    const el = document.createElement('div');
    el.className = 'log-msg';
    el.innerHTML = `<span class="time">[${timeStr}]</span> ${msg}`;
    sysLog.appendChild(el);
    sysLog.scrollTop = sysLog.scrollHeight;
}

function updateSteps(newState) {
    let found = false;
    steps.forEach(step => {
        const stepName = step.dataset.step;
        step.classList.remove('active');
        if (stepName === newState) {
            step.classList.add('active');
            found = true;
        } else if (!found) {
            step.classList.add('completed');
        } else {
            step.classList.remove('completed');
        }
    });

    if (newState === 'BASELINE_COMPLETE' || newState === 'CALIBRATION_COMPLETE') {
        const mapping = {
            'BASELINE_COMPLETE': 'HR_BASELINE',
            'CALIBRATION_COMPLETE': 'HRV_CALIBRATION'
        };
        const prevStep = document.querySelector(`.step[data-step="${mapping[newState]}"]`);
        if (prevStep) {
            prevStep.classList.remove('completed');
            prevStep.classList.add('active');
        }
    }
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
}

function updateButtons(state) {
    btnAction.disabled = false;
    btnAction.classList.remove('hidden');
    btnSkip.classList.add('hidden');
    btnStop.classList.remove('hidden');

    switch (state) {
        case 'IDLE':
            btnAction.textContent = 'Connect Polar';
            btnStop.classList.add('hidden');
            break;
        case 'CONNECTING_POLAR':
            btnAction.textContent = 'Connecting Polar...';
            btnAction.disabled = true;
            break;
        case 'CONNECTING_HEADSET':
            btnAction.textContent = 'Waiting for Headset...';
            btnAction.disabled = true;
            break;
        case 'READY':
            btnAction.textContent = 'Start Setup';
            break;
        case 'CALIBRATION_TUTORIAL':
        case 'HRV_TUTORIAL':
            btnAction.innerHTML = '<span class="pulse-ring" style="display:inline-block; width:8px; height:8px; margin-right:8px; vertical-align:middle;"></span> Tutorial playing... (Click to override)';
            btnSkip.classList.remove('hidden');
            break;
        case 'HR_BASELINE':
        case 'HRV_CALIBRATION':
            btnAction.textContent = 'In Progress...';
            btnAction.disabled = true;
            break;
        case 'BASELINE_COMPLETE':
        case 'CALIBRATION_COMPLETE':
            btnAction.textContent = 'Proceed';
            break;
        case 'THERAPY':
            btnAction.classList.add('hidden');
            therapyControls.classList.remove('hidden');
            break;
        case 'COMPLETE':
            btnAction.textContent = 'New Session';
            btnStop.classList.add('hidden');
            break;
    }

    if (state !== 'THERAPY') {
        therapyControls.classList.add('hidden');
    }
}

function resetResultsDisplay() {
    resBaseline.textContent = '-- BPM';
    resFreq.textContent = '-- Hz';
    resRate.textContent = '(-- breaths/min)';
    hrvSegmentsCont.classList.add('hidden');
    hrvSegmentsList.innerHTML = '';
}

function heartbeatAnim() {
    heartIcon.classList.add('heart-beat');
    setTimeout(() => heartIcon.classList.remove('heart-beat'), 150);
}

function drawChart() {
    ctx.clearRect(0, 0, chartCanvas.width, chartCanvas.height);
    if (hrHistory.length < 2) return;

    const w = chartCanvas.width;
    const h = chartCanvas.height;
    const padding = 20;

    const minHR = Math.max(0, Math.min(...hrHistory.map(d => d.hr)) - 5);
    const maxHR = Math.max(...hrHistory.map(d => d.hr)) + 5;
    const range = Math.max(10, maxHR - minHR);

    const stepX = (w - padding * 2) / (maxDataPoints - 1);

    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i <= 4; i++) {
        const y = padding + i * ((h - padding * 2) / 4);
        ctx.moveTo(padding, y);
        ctx.lineTo(w - padding, y);
    }
    ctx.stroke();

    ctx.beginPath();
    ctx.strokeStyle = '#f85149';
    ctx.lineWidth = 3;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    hrHistory.forEach((dataPoint, i) => {
        const xIndex = maxDataPoints - hrHistory.length + i;
        const x = padding + xIndex * stepX;
        const normalizedY = (dataPoint.hr - minHR) / range;
        const y = h - padding - (normalizedY * (h - padding * 2));
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, 'rgba(248, 81, 73, 0.2)');
    grad.addColorStop(1, 'rgba(248, 81, 73, 0)');
    ctx.lineTo(w - padding, h - padding);
    const firstXIndex = maxDataPoints - hrHistory.length;
    ctx.lineTo(padding + firstXIndex * stepX, h - padding);
    ctx.fillStyle = grad;
    ctx.fill();
}

function drawHrvChart() {
    if (!hrvChartCanvas.width || !hrvChartCanvas.height) return;
    hrvCtx.clearRect(0, 0, hrvChartCanvas.width, hrvChartCanvas.height);
    if (rmssdHistory.length < 2) return;

    const w = hrvChartCanvas.width;
    const h = hrvChartCanvas.height;
    const padding = 20;

    const values = rmssdHistory.map(d => d.rmssd);
    const minV = Math.max(0, Math.min(...values) - 5);
    const maxV = Math.max(...values) + 5;
    const range = Math.max(5, maxV - minV);

    const stepX = (w - padding * 2) / (maxDataPoints - 1);

    // Grid
    hrvCtx.strokeStyle = 'rgba(255,255,255,0.05)';
    hrvCtx.lineWidth = 1;
    hrvCtx.beginPath();
    for (let i = 0; i <= 4; i++) {
        const y = padding + i * ((h - padding * 2) / 4);
        hrvCtx.moveTo(padding, y);
        hrvCtx.lineTo(w - padding, y);
    }
    hrvCtx.stroke();

    // Line
    hrvCtx.beginPath();
    hrvCtx.strokeStyle = '#3fb950';
    hrvCtx.lineWidth = 3;
    hrvCtx.lineJoin = 'round';
    hrvCtx.lineCap = 'round';

    rmssdHistory.forEach((dataPoint, i) => {
        const xIndex = maxDataPoints - rmssdHistory.length + i;
        const x = padding + xIndex * stepX;
        const normalizedY = (dataPoint.rmssd - minV) / range;
        const y = h - padding - (normalizedY * (h - padding * 2));
        if (i === 0) hrvCtx.moveTo(x, y);
        else hrvCtx.lineTo(x, y);
    });
    hrvCtx.stroke();

    // Fill
    const grad = hrvCtx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, 'rgba(63, 185, 80, 0.2)');
    grad.addColorStop(1, 'rgba(63, 185, 80, 0)');
    hrvCtx.lineTo(w - padding, h - padding);
    const firstXIndex = maxDataPoints - rmssdHistory.length;
    hrvCtx.lineTo(padding + firstXIndex * stepX, h - padding);
    hrvCtx.fillStyle = grad;
    hrvCtx.fill();
}


// WebSocket Handlers
ws.onopen = () => logMsg("Connected to Server");
ws.onclose = () => logMsg("Disconnected from Server");

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'state') {
        const wasTherapy = currentState === 'THERAPY';
        currentState = data.state;
        updateSteps(data.state);
        updateButtons(data.state);

        // Reset HRV history and extremes when leaving therapy (restart or stop)
        if (wasTherapy && data.state !== 'THERAPY') {
            rmssdHistory = [];
            hrvMaxEl.textContent = '-- ms';
            hrvMinEl.textContent = '-- ms';
        }

        // Clear results on return to READY (after restart)
        if (data.state === 'READY' && wasTherapy) {
            resetResultsDisplay();
        }

        if (data.state === 'COMPLETE') {
            elapsedTimeEl.textContent = "00:00";
            totalTimeEl.textContent = "--:--";
        } else {
            elapsedTimeEl.textContent = formatTime(data.elapsed);
            if (data.total > 0) {
                totalTimeEl.textContent = formatTime(data.total);
            } else if (data.state !== 'THERAPY') {
                totalTimeEl.textContent = "--:--";
            }
        }
    }

    else if (data.type === 'connection_status') {
        if (data.polar) indPolar.classList.add('connected');
        else indPolar.classList.remove('connected');

        if (data.headset) indHeadset.classList.add('connected');
        else indHeadset.classList.remove('connected');
    }

    else if (data.type === 'hr_update') {
        hrValueEl.textContent = data.heartrate;
        rmssdEl.textContent = data.rmssd + " ms";
        sdnnEl.textContent = data.sdnn + " ms";
        heartbeatAnim();

        hrHistory.push({ hr: data.heartrate, time: data.timestamp });
        if (hrHistory.length > maxDataPoints) hrHistory.shift();
        drawChart();

        if (data.rmssd > 0) {
            rmssdHistory.push({ rmssd: data.rmssd, time: data.timestamp });
            if (rmssdHistory.length > maxDataPoints) rmssdHistory.shift();
            drawHrvChart();
        }

        if (data.max_rmssd !== null && data.max_rmssd !== undefined) {
            hrvMaxEl.textContent = data.max_rmssd.toFixed(1) + " ms";
        }
        if (data.min_rmssd !== null && data.min_rmssd !== undefined) {
            hrvMinEl.textContent = data.min_rmssd.toFixed(1) + " ms";
        }
    }

    else if (data.type === 'baseline_result') {
        resBaseline.textContent = data.mean_hr + " BPM";
        logMsg(`Baseline completed: ${data.mean_hr} BPM (${data.sample_count} samples)`);
    }

    else if (data.type === 'hrv_segment') {
        logMsg(`HRV Calib: Segment ${data.segment}/${data.total_segments} at ${data.breathing_rate} br/min`);
    }

    else if (data.type === 'resonant_result') {
        const hz = (data.frequency / 60).toFixed(3);
        resFreq.textContent = hz + " Hz";
        resRate.textContent = `(${data.frequency.toFixed(1)} breaths/min)`;
        logMsg(`Resonant Frequency found: ${data.frequency.toFixed(1)} br/min`);

        hrvSegmentsList.innerHTML = '';
        const amps = data.amplitudes;
        for (const [rate, amp] of Object.entries(amps).sort((a, b) => b[0] - a[0])) {
            const li = document.createElement('li');
            li.textContent = `${parseFloat(rate).toFixed(1)} br/min: Amplitude ${amp} BPM`;
            if (parseFloat(rate) === data.frequency) {
                li.classList.add('best');
                li.textContent += " (Max)";
            }
            hrvSegmentsList.appendChild(li);
        }
        hrvSegmentsCont.classList.remove('hidden');
    }

    else if (data.type === 'therapy_action_sent') {
        const labels = {
            start_birds_flyover: 'Birds Flyover'
        };
        logMsg(`Sent to headset: <strong>${labels[data.action] || data.action}</strong>`);
    }

    else if (data.type === 'session_complete') {
        logMsg(`Session saved to ${data.file}`);
    }

    else if (data.type === 'error') {
        logMsg(`ERROR: ${data.message}`);
        alert(`Error: ${data.message}`);
    }
};

// Button Actions
btnAction.addEventListener('click', () => {
    if (currentState === 'IDLE') {
        ws.send(JSON.stringify({ type: 'action', action: 'connect_polar' }));
    } else if (currentState === 'COMPLETE') {
        location.reload();
    } else {
        ws.send(JSON.stringify({ type: 'action', action: 'next_step' }));
    }
});

btnSkip.addEventListener('click', () => {
    ws.send(JSON.stringify({ type: 'action', action: 'skip_tutorial' }));
});

btnStop.addEventListener('click', () => {
    if (confirm("Are you sure you want to stop the session? Data will be saved.")) {
        ws.send(JSON.stringify({ type: 'action', action: 'stop_session' }));
    }
});

btnBirds.addEventListener('click', () => {
    ws.send(JSON.stringify({ type: 'action', action: 'start_birds_flyover' }));
});

btnRestartSession.addEventListener('click', () => {
    if (confirm("Restart the session? Current data will be saved and calibration will restart.")) {
        ws.send(JSON.stringify({ type: 'action', action: 'restart_session' }));
    }
});

// Init
setTimeout(resizeCanvas, 100);
