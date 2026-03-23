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
const resBaseline = document.getElementById('res-baseline');
const resFreq = document.getElementById('res-freq');
const resRate = document.getElementById('res-rate');
const hrvSegmentsCont = document.getElementById('hrv-segments-container');
const hrvSegmentsList = document.getElementById('hrv-segments-list');
const chartCanvas = document.getElementById('hr-chart');
const ctx = chartCanvas.getContext('2d');

// Chart data
let hrHistory = [];
const maxDataPoints = 60;

// State management
let currentState = 'IDLE';

// Resize canvas
function resizeCanvas() {
    chartCanvas.width = chartCanvas.parentElement.clientWidth;
    chartCanvas.height = chartCanvas.parentElement.clientHeight;
    drawChart();
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

    // Special cases
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
            break;
        case 'COMPLETE':
            btnAction.textContent = 'New Session';
            btnStop.classList.add('hidden');
            break;
    }
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

    // Find min/max for scaling
    // Add margin to min/max
    const minHR = Math.max(0, Math.min(...hrHistory.map(d => d.hr)) - 5);
    const maxHR = Math.max(...hrHistory.map(d => d.hr)) + 5;
    const range = Math.max(10, maxHR - minHR);

    const stepX = (w - padding * 2) / (maxDataPoints - 1);
    
    // Draw grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i <= 4; i++) {
        const y = padding + i * ((h - padding*2) / 4);
        ctx.moveTo(padding, y);
        ctx.lineTo(w - padding, y);
    }
    ctx.stroke();

    // Draw line
    ctx.beginPath();
    ctx.strokeStyle = '#f85149'; // accent-red
    ctx.lineWidth = 3;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    hrHistory.forEach((dataPoint, i) => {
        // We want the most recent points on the right.
        const xIndex = maxDataPoints - hrHistory.length + i;
        const x = padding + xIndex * stepX;
        const normalizedY = (dataPoint.hr - minHR) / range;
        const y = h - padding - (normalizedY * (h - padding * 2));
        
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
    
    // Fill under line
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, 'rgba(248, 81, 73, 0.2)');
    grad.addColorStop(1, 'rgba(248, 81, 73, 0)');
    ctx.lineTo(w - padding, h - padding);
    const firstXIndex = maxDataPoints - hrHistory.length;
    ctx.lineTo(padding + firstXIndex * stepX, h - padding);
    ctx.fillStyle = grad;
    ctx.fill();
}


// WebSocket Handlers
ws.onopen = () => logMsg("Connected to Server");
ws.onclose = () => logMsg("Disconnected from Server");

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'state') {
        currentState = data.state;
        updateSteps(data.state);
        updateButtons(data.state);
        
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
        
        // Only keep 1 point per second for the chart, roughly
        // If we want smooth, we can just push every point, but keep array bounded
        hrHistory.push({ hr: data.heartrate, time: data.timestamp });
        if (hrHistory.length > maxDataPoints) hrHistory.shift();
        drawChart();
    }
    
    else if (data.type === 'baseline_result') {
        resBaseline.textContent = data.mean_hr + " BPM";
        logMsg(`Baseline completed: ${data.mean_hr} BPM (${data.sample_count} samples)`);
    }
    
    else if (data.type === 'hrv_segment') {
        logMsg(`HRV Calib: Segment ${data.segment}/${data.total_segments} at ${data.breathing_rate} br/min`);
    }
    
    else if (data.type === 'resonant_result') {
        resFreq.textContent = data.frequency.toFixed(3) + " Hz";
        resRate.textContent = `(${data.frequency} breaths/min)`; // The incoming value from backend was the breaths/min actually! Let's display it nicely.
        
        // We know from backend: frequency field holds the BPM rate. Frequency in Hz = rate/60.
        const hz = (data.frequency / 60).toFixed(3);
        resFreq.textContent = hz + " Hz";
        resRate.textContent = `(${data.frequency.toFixed(1)} breaths/min)`;
        
        logMsg(`Resonant Frequency found: ${data.frequency.toFixed(1)} br/min`);
        
        // Show segments
        hrvSegmentsList.innerHTML = '';
        const amps = data.amplitudes;
        for (const [rate, amp] of Object.entries(amps).sort((a,b) => b[0]-a[0])) {
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
        // Refresh page for entirely new session
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

// Init
setTimeout(resizeCanvas, 100);
