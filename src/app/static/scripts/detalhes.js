// static/scripts/detalhes.js

// CONFIG
const POLL_INTERVAL = 4000; // ms, ajuste se quiser
const API_PATH = ip => `/api/get/data/clp/${encodeURIComponent(ip)}`;

// Paleta de cores para tema escuro
const themeColors = [
    'rgba(132, 0, 255, 0.9)',       // Roxo primário
    'rgba(204, 0, 255, 0.8)',       // Secundário
    'rgba(0, 255, 153, 0.8)',       // Verde status online
    'rgba(255, 59, 59, 0.8)',       // Vermelho para alarmes
    'rgba(255, 196, 196, 0.8)',     // Rosa para violado
    'rgba(255, 153, 0, 0.8)'        // Laranja para limite baixo
];

// state
const charts = new Map(); // registerId -> Chart instance
const chartDataBuffers = new Map(); // registerId -> {labels:[], values:[]}

// util: pega IP do template (data-ip dos botões)
function getClpIpFromDom() {
    const btnConnect = document.getElementById('btnConnect');
    const btnDisconnect = document.getElementById('btnDisconnect');
    return (btnConnect && btnConnect.dataset.ip) || (btnDisconnect && btnDisconnect.dataset.ip) || null;
}

// util: format timestamp pra algo legível
function fmtShort(ts) {
    try {
        const d = new Date(ts);
        return d.toLocaleTimeString();
    } catch (e) {
        return ts;
    }
}

// verifica violação baseado na definição
function violatesCondition(value, def) {
    if (!def) return false;
    const cond = (def.condition_type || '').toLowerCase();
    const sp = Number(def.setpoint ?? NaN);
    const dband = Number(def.deadband ?? 0);
    const low = def.threshold_low != null ? Number(def.threshold_low) : (def.low ?? NaN);
    const high = def.threshold_high != null ? Number(def.threshold_high) : (def.high ?? NaN);

    if (Number.isNaN(value)) return false;

    if (cond === 'above') {
        return value > sp;
    } else if (cond === 'below') {
        return value < sp;
    } else if (cond === 'outside_range') {
        if (Number.isFinite(low) && Number.isFinite(high)) {
            return value < low || value > high;
        }
        return false;
    } else if (cond === 'inside_range') {
        if (Number.isFinite(low) && Number.isFinite(high)) {
            return value >= low && value <= high;
        }
        return false;
    }
    return false;
}

// cria um canvas/card para o registrador
function ensureRegisterCard(registerId, unit, registerAddr) {
    const container = document.getElementById('registers-container');
    let card = document.getElementById(`register-card-${registerId}`);
    if (card) return card;

    card = document.createElement('div');
    card.className = 'register-card';
    card.id = `register-card-${registerId}`;
    card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div class="register-addr">Register ${registerAddr ?? registerId}</div>
                <div style="font-size:0.85em; color:var(--text-muted)">Unidade: ${unit ?? '-'}</div>
            </div>
            <div class="register-val" id="register-val-${registerId}">--</div>
        </div>
        <canvas id="chart-register-${registerId}" width="600" height="220" style="width:100%; height:220px; margin-top:8px;"></canvas>
        <div id="alarm-legend-${registerId}" style="margin-top:6px; font-size:0.85em; color: var(--text-muted);"></div>
    `;
    container.appendChild(card);
    return card;
}

// cria ou atualiza um chart a partir dos buffers
function createOrUpdateChart(registerId, unit, def) {
    const canvasId = `chart-register-${registerId}`;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    // 🔧 fixar tamanho real do canvas (evita height crescendo)
    canvas.width = canvas.clientWidth;
    canvas.height = 220;

    const buffer = chartDataBuffers.get(registerId) || { labels: [], values: [], rawPoints: [] };
    const labels = buffer.labels;
    const values = buffer.values;

    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, canvas.width, 0);
    gradient.addColorStop(0, themeColors[0]);
    gradient.addColorStop(1, themeColors[1]);

    const valueDataset = {
        label: `Valor ${unit ? `(${unit})` : ''}`,
        data: values,
        fill: false,
        tension: 0.3,
        pointRadius: buffer.rawPoints.map(p => p.violated ? 7 : 5),
        pointBackgroundColor: buffer.rawPoints.map(p => p.violated ? themeColors[3] : themeColors[0]),
        pointBorderColor: buffer.rawPoints.map(p => p.violated ? themeColors[3] : themeColors[1]),
        pointBorderWidth: buffer.rawPoints.map(p => p.violated ? 4 : 2),
        borderWidth: 3,
        borderColor: gradient,
    };

    const limitDatasets = [];
    if (def) {
        const cond = (def.condition_type || '').toLowerCase();
        const n = labels.length || 1;
        if (cond === 'above' || cond === 'below') {
            const sp = Number(def.setpoint ?? NaN);
            if (!Number.isNaN(sp)) {
                limitDatasets.push({
                    label: `Setpoint (${sp})`,
                    data: new Array(n).fill(sp),
                    fill: false,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    borderWidth: 2,
                    borderColor: themeColors[2],
                });
            }
        } else if (cond === 'outside_range' || cond === 'inside_range') {
            const low = def.threshold_low != null ? Number(def.threshold_low) : null;
            const high = def.threshold_high != null ? Number(def.threshold_high) : null;
            if (low !== null && !Number.isNaN(low)) {
                limitDatasets.push({
                    label: `Low (${low})`,
                    data: new Array(n).fill(low),
                    fill: false,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    borderWidth: 2,
                    borderColor: themeColors[5],
                });
            }
            if (high !== null && !Number.isNaN(high)) {
                limitDatasets.push({
                    label: `High (${high})`,
                    data: new Array(n).fill(high),
                    fill: false,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    borderWidth: 2,
                    borderColor: themeColors[3],
                });
            }
        }
    }

    const datasets = [valueDataset, ...limitDatasets];

    if (charts.has(registerId)) {
        const chart = charts.get(registerId);
        chart.data.labels = labels;
        chart.data.datasets = datasets;
        chart.update();
    } else {
        const chart = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets },
            options: {
                animation: false,
                maintainAspectRatio: false,
                responsive: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#fff',
                            font: { weight: 'bold', size: 11 },
                            padding: 10
                        }
                    },
                    tooltip: {
                        backgroundColor: '#1b0030',
                        titleColor: '#fff',
                        bodyColor: '#fff',
                        borderColor: themeColors[1],
                        borderWidth: 2,
                        displayColors: true,
                        callbacks: {
                            label: function(context) {
                                const v = context.raw;
                                const p = buffer.rawPoints[context.dataIndex];
                                let msg = `${context.dataset.label}: ${v}`;
                                if (p?.violated) msg += ' ⚠️ (Violado!)';
                                if (p?.payload && p.payload.timestamp) {
                                    msg += ` | ${fmtShort(p.payload.timestamp)}`;
                                }
                                return msg;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(132, 0, 255, 0.15)' },
                        ticks: { color: '#fff', maxTicksLimit: 8 },
                    },
                    y: {
                        grid: { color: 'rgba(132, 0, 255, 0.08)' },
                        ticks: { color: '#fff' }
                    }
                }
            }
        });
        charts.set(registerId, chart);
    }

    const legendEl = document.getElementById(`alarm-legend-${registerId}`);
    if (legendEl) {
        if (def) {
            legendEl.innerHTML = `<strong>Definição:</strong> ${def.name ?? '(sem nome)'} — tipo: ${def.condition_type} ${def.setpoint != null ? `| setpoint: ${def.setpoint}` : ''}`;
        } else {
            legendEl.innerHTML = `<strong>Definição:</strong> (nenhuma)`;
        }
    }
}

// processa o payload da API e alimenta buffers e gráficos
function processApiPayload(payload) {
    if (!payload) return;
    const registers = payload.register_ids || [];
    const data = payload.data || [];
    const defs = payload.definitions_alarms || [];
    const alarms = payload.alarms || [];

    const defsByRegister = {};
    for (const d of defs) {
        if (d.register_id == null) continue;
        defsByRegister[d.register_id] = d;
    }

    const dataByRegister = {};
    for (const p of data) {
        const rid = p.register_id;
        if (!dataByRegister[rid]) dataByRegister[rid] = [];
        dataByRegister[rid].push(p);
    }

    for (const rid of registers) {
        const series = dataByRegister[rid] || [];
        series.sort((a,b) => new Date(a.timestamp) - new Date(b.timestamp));

        let buffer = chartDataBuffers.get(rid);
        if (!buffer) buffer = { labels: [], values: [], rawPoints: [] };

        const seen = new Set(buffer.rawPoints.map(p => p.timestamp));
        for (const pt of series) {
            if (seen.has(pt.timestamp)) continue;
            const value = Number(pt.value_float ?? pt.value_int ?? pt.raw_value ?? NaN);
            const def = defsByRegister[rid];
            const violated = violatesCondition(value, def);
            buffer.labels.push(fmtShort(pt.timestamp));
            buffer.values.push(value);
            buffer.rawPoints.push({ timestamp: pt.timestamp, value, violated, payload: pt });
            if (buffer.labels.length > 100) {
                buffer.labels.shift();
                buffer.values.shift();
                buffer.rawPoints.shift();
            }
        }
        chartDataBuffers.set(rid, buffer);

        const unit = (series.at(-1)?.unit) ?? (defsByRegister[rid]?.unit) ?? '';
        ensureRegisterCard(rid, unit, rid);
        const last = buffer.rawPoints.at(-1);
        const valEl = document.getElementById(`register-val-${rid}`);
        if (valEl) {
            valEl.textContent = last ? `${last.value} ${unit}` : '--';
            valEl.style.color = last?.violated ? themeColors[3] : themeColors[2];
            valEl.style.fontWeight = last?.violated ? 'bold' : 'normal';
        }

        createOrUpdateChart(rid, unit, defsByRegister[rid] ?? null);
    }

    const logContainer = document.getElementById('logContainer');
    if (logContainer && alarms.length > 0) {
        logContainer.innerHTML = alarms.map(a => {
            const t = new Date(a.triggered_at).toLocaleString();
            return `<div style="color: ${a.state === 'active' ? themeColors[3] : themeColors[2]}">[${t}] Alarm: ${a.message || '(sem mensagem)'} (register ${a.register_id}) state=${a.state}</div>`;
        }).join('');
        logContainer.scrollTop = logContainer.scrollHeight;
    }
}

async function pollOnce() {
    const ip = getClpIpFromDom();
    if (!ip) return;
    try {
        const res = await fetch(API_PATH(ip), { cache: 'no-store' });
        if (res.ok) processApiPayload(await res.json());
        else console.error('Erro ao buscar dados do CLP:', res.status);
    } catch (err) {
        console.error('Erro no polling do CLP:', err);
    }
}

function startPolling() {
    pollOnce();
    setInterval(pollOnce, POLL_INTERVAL);
}

window.addEventListener('DOMContentLoaded', () => {
    if (typeof Chart === 'undefined') {
        console.error('Chart.js não encontrado.');
        return;
    }
    startPolling();
});


