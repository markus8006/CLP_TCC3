// static/scripts/detalhes.js

// CONFIG
const POLL_INTERVAL = 4000; // ms, ajuste se quiser
const API_PATH = (ip, vlan) => {
    const base = `/api/get/data/clp/${encodeURIComponent(ip)}`;
    if (vlan !== null && vlan !== undefined && vlan !== '') {
        return `${base}?vlan=${encodeURIComponent(vlan)}`;
    }
    return base;
};

const TAGS_PATH = (ip, vlan, tag) => {
    let base = `/api/clps/${encodeURIComponent(ip)}/tags`;
    if (tag) {
        base += `/${encodeURIComponent(tag)}`;
    }
    if (vlan !== null && vlan !== undefined && vlan !== '') {
        base += tag ? `?vlan=${encodeURIComponent(vlan)}` : `?vlan=${encodeURIComponent(vlan)}`;
    }
    return base;
};

const SCRIPTS_ENDPOINT = (plcId, scriptId = null) => {
    const base = `/api/plcs/${encodeURIComponent(plcId)}/scripts`;
    return scriptId ? `${base}/${encodeURIComponent(scriptId)}` : base;
};

let monacoEditorInstance = null;
let currentScripts = [];
let selectedScriptId = null;
let scriptLanguages = {};

let pollingIntervalId = null;
let isPollingRunning = false;
let tagManagementInitialized = false;
let autoDiscoveryInitialized = false;
let registerExchangeInitialized = false;
let chartWarningLogged = false;

// Paleta de cores para tema escuro
const themeColors = [
    'rgba(132, 0, 255, 0.9)',       // Roxo primário
    'rgba(204, 0, 255, 0.8)',       // Secundário
    'rgba(0, 255, 153, 0.8)',       // Verde status online
    'rgba(255, 59, 59, 0.8)',       // Vermelho para alarmes
    'rgba(255, 196, 196, 0.8)',     // Rosa para violado
    'rgba(255, 153, 0, 0.8)'        // Laranja para limite baixo
];

function monacoLanguageFor(language) {
    const key = (language || '').toLowerCase();
    if (key === 'python') return 'python';
    if (key === 'st') return 'pascal';
    if (key === 'ladder') return 'plaintext';
    return key || 'plaintext';
}

// state
const charts = new Map(); // registerId -> Chart instance
const chartDataBuffers = new Map(); // registerId -> {labels:[], values:[], rawPoints:[]}

// util: pega IP do template (data-ip dos botões)
function getClpIpFromDom() {
    const btnConnect = document.getElementById('btnConnect');
    const btnDisconnect = document.getElementById('btnDisconnect');
    return (btnConnect && btnConnect.dataset.ip) || (btnDisconnect && btnDisconnect.dataset.ip) || null;
}

function getClpVlanFromDom() {
    const btnConnect = document.getElementById('btnConnect');
    const btnDisconnect = document.getElementById('btnDisconnect');
    const raw = (btnConnect && btnConnect.dataset.vlan) || (btnDisconnect && btnDisconnect.dataset.vlan) || null;
    if (raw === null || raw === undefined || raw === '') {
        return null;
    }
    const parsed = Number(raw);
    return Number.isNaN(parsed) ? raw : parsed;
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

// cria um painel recolhível para o registrador
function ensureRegisterCard(registerId, unit, registerName, registerTag = null, registerAddress = null) {
    const accordion = document.getElementById('register-accordion');
    if (!accordion) return null;

    let card = document.getElementById(`register-card-${registerId}`);
    let isNewCard = false;

    if (!card) {
        card = document.createElement('details');
        card.className = 'register-panel';
        card.id = `register-card-${registerId}`;
        card.dataset.registerId = registerId;
        isNewCard = true;

        const summary = document.createElement('summary');
        const nameEl = document.createElement('span');
        nameEl.className = 'register-summary__name';
        summary.appendChild(nameEl);

        const statusEl = document.createElement('span');
        statusEl.className = 'register-summary__status';
        statusEl.id = `register-status-${registerId}`;
        statusEl.dataset.state = 'unknown';
        statusEl.textContent = 'Aguardando dados';
        summary.appendChild(statusEl);

        const valueEl = document.createElement('span');
        valueEl.className = 'register-summary__value';
        valueEl.id = `register-val-${registerId}`;
        valueEl.textContent = '--';
        summary.appendChild(valueEl);

        const body = document.createElement('div');
        body.className = 'register-panel-body';

        const chartWrapper = document.createElement('div');
        chartWrapper.className = 'register-chart-wrapper';

        const canvas = document.createElement('canvas');
        canvas.id = `chart-register-${registerId}`;
        canvas.width = 600;
        canvas.height = 220;
        canvas.setAttribute('role', 'img');
        canvas.setAttribute('aria-label', `Histórico do registrador ${registerName || registerId}`);
        chartWrapper.appendChild(canvas);

        const legend = document.createElement('div');
        legend.className = 'register-legend';
        legend.id = `alarm-legend-${registerId}`;

        body.append(chartWrapper, legend);
        card.append(summary, body);

        card.addEventListener('toggle', () => {
            if (!card.open) return;
            requestAnimationFrame(() => {
                const chart = charts.get(registerId);
                if (chart) {
                    chart.resize();
                    chart.update('none');
                }
            });
        });

        accordion.appendChild(card);
    }

    const summary = card.querySelector('summary');
    const nameEl = summary.querySelector('.register-summary__name');

    const displaySegments = [];
    if (registerTag) {
        displaySegments.push(registerTag);
    }
    const fallbackName = registerName || `Registrador ${registerId}`;
    displaySegments.push(fallbackName);
    if (registerAddress) {
        displaySegments.push(`@ ${registerAddress}`);
    }
    nameEl.textContent = displaySegments.join(' • ');

    card.dataset.tag = registerTag || '';
    card.dataset.address = registerAddress || '';
    card.dataset.unit = unit || '';

    const canvas = card.querySelector(`#chart-register-${registerId}`);
    if (canvas) {
        const descriptor = registerTag || registerName || registerId;
        canvas.setAttribute('aria-label', `Histórico do registrador ${descriptor}`);
    }

    if (isNewCard) {
        return card;
    }

    return card;
}


// cria ou atualiza um chart a partir dos buffers
function createOrUpdateChart(registerId, unit, def) {
    const canvasId = `chart-register-${registerId}`;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    // 🔧 fixar tamanho real do canvas (evita height crescendo)
    const parentWidth = canvas.parentElement ? canvas.parentElement.clientWidth : 0;
    canvas.width = parentWidth > 0 ? parentWidth : 600;
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

    // 🔥 reset completo: destrói chart antigo antes de criar novo
    if (charts.has(registerId)) {
        charts.get(registerId).destroy();
        charts.delete(registerId);
    }

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
                        label: function (context) {
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

    const legendEl = document.getElementById(`alarm-legend-${registerId}`);
    if (legendEl) {
        const unitLabel = unit ? ` — unidade: ${unit}` : '';
        if (def) {
            legendEl.innerHTML = `<strong>Definição:</strong> ${def.name ?? '(sem nome)'} — tipo: ${def.condition_type}${def.setpoint != null ? ` | setpoint: ${def.setpoint}` : ''}${unitLabel}`;
        } else {
            legendEl.innerHTML = `<strong>Definição:</strong> (nenhuma)${unitLabel}`;
        }
    }
}

// processa o payload da API e alimenta buffers e gráficos
function processApiPayload(payload) {
    if (!payload) return;

    // novo modelo: payload.registers é um objeto { id: "nome", ... }
    const registersMap = payload.registers || {};
    const registers = Object.keys(registersMap); // array de ids (strings)

    const data = payload.data || [];
    const defs = payload.definitions_alarms || [];
    const alarms = payload.alarms || [];

    // indexa definições por register_id (usar string keys)
    const defsByRegister = {};
    for (const d of defs) {
        if (d.register_id == null) continue;
        defsByRegister[String(d.register_id)] = d;
    }

    // agrupa dados por register_id (usar string keys)
    const dataByRegister = {};
    for (const p of data) {
        const rid = String(p.register_id);
        if (!dataByRegister[rid]) dataByRegister[rid] = [];
        dataByRegister[rid].push(p);
    }

    const MAX_POINTS = 100;

    for (const rid of registers) {
        const info = registersMap[rid];
        const registerInfo = (info && typeof info === 'object') ? info : { name: info };
        const registerName = registerInfo.name || null;
        const registerTag = registerInfo.tag_name || registerInfo.tag || null;
        const registerAddress = registerInfo.address || null;
        const series = (dataByRegister[rid] || []).slice().sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

        const newLabels = [];
        const newValues = [];
        const newRawPoints = [];
        const seenTs = new Set();
        let violatedCount = 0;

        for (const pt of series) {
            if (seenTs.has(pt.timestamp)) continue;
            seenTs.add(pt.timestamp);

            const value = Number(pt.value_float ?? pt.value_int ?? pt.raw_value ?? NaN);
            const def = defsByRegister[rid];
            const violated = violatesCondition(value, def);
            if (violated) violatedCount++;

            newLabels.push(fmtShort(pt.timestamp));
            newValues.push(value);
            newRawPoints.push({ timestamp: pt.timestamp, value, violated, payload: pt });

            if (newLabels.length >= MAX_POINTS) break;
        }

        const buffer = { labels: newLabels, values: newValues, rawPoints: newRawPoints };
        chartDataBuffers.set(rid, buffer);

        console.log(`[DEBUG] Register ${rid} (${registerTag || registerName || 'sem identificação'}): ${newLabels.length} pontos processados, ${violatedCount} violados.`);

        const unit = (series.at(-1)?.unit) ?? (defsByRegister[rid]?.unit) ?? '';
        ensureRegisterCard(rid, unit, registerName, registerTag, registerAddress);
        const last = buffer.rawPoints.at(-1);
        const statusEl = document.getElementById(`register-status-${rid}`);
        if (statusEl) {
            if (last) {
                statusEl.textContent = last.violated ? 'Violado' : 'Normal';
                statusEl.dataset.state = last.violated ? 'violated' : 'ok';
            } else {
                statusEl.textContent = 'Sem dados';
                statusEl.dataset.state = 'unknown';
            }
        }
        const valEl = document.getElementById(`register-val-${rid}`);
        if (valEl) {
            if (last) {
                const formatted = Number.isFinite(last.value) ? last.value : String(last.value ?? '--');
                valEl.textContent = unit ? `${formatted} ${unit}` : `${formatted}`;
                valEl.style.color = last.violated ? themeColors[3] : themeColors[2];
                valEl.style.fontWeight = last.violated ? 'bold' : 'normal';
            } else {
                valEl.textContent = '--';
                valEl.style.color = 'var(--text-muted)';
                valEl.style.fontWeight = 'normal';
            }
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
    const vlan = getClpVlanFromDom();
    try {
        const res = await fetch(API_PATH(ip, vlan), { cache: 'no-store' });
        if (res.ok) processApiPayload(await res.json());
        else console.error('Erro ao buscar dados do CLP:', res.status);
    } catch (err) {
        console.error('Erro no polling do CLP:', err);
    }
}

function startPolling() {
    if (isPollingRunning) {
        return;
    }
    if (typeof Chart === 'undefined') {
        if (!chartWarningLogged) {
            console.error('Chart.js não encontrado.');
            chartWarningLogged = true;
        }
        return;
    }

    pollOnce();
    pollingIntervalId = setInterval(pollOnce, POLL_INTERVAL);
    isPollingRunning = true;
}

function stopPolling() {
    if (!isPollingRunning) {
        return;
    }
    if (pollingIntervalId) {
        clearInterval(pollingIntervalId);
        pollingIntervalId = null;
    }
    isPollingRunning = false;
}

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

function parseJsonAttribute(value, fallback = null) {
    if (!value) return fallback;
    try {
        return JSON.parse(value);
    } catch (error) {
        console.warn('Falha ao interpretar atributo JSON', value, error);
        return fallback;
    }
}

function initAutoDiscoverySync() {
    const button = document.getElementById('auto-discovery-sync');
    const feedback = document.getElementById('auto-discovery-feedback');
    if (!button) return;

    const plcId = Number(button.dataset.plcId);
    if (!Number.isFinite(plcId) || plcId <= 0) {
        return;
    }

    function setFeedback(message, type) {
        if (!feedback) return;
        feedback.textContent = '';
        feedback.className = 'protocol-feedback';
        if (type) {
            feedback.classList.add(type);
        }
        if (message) {
            feedback.textContent = message;
        }
    }

    button.addEventListener('click', async () => {
        button.disabled = true;
        setFeedback('Sincronizando tags e registradores…', 'loading');
        try {
            const response = await fetch(`/api/plcs/${encodeURIComponent(plcId)}/discover`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.message || 'Não foi possível sincronizar as tags.');
            }

            if (Array.isArray(payload.tags)) {
                renderTagList(payload.tags);
            }

            const created = Number(payload.registers_created || 0);
            const updated = Number(payload.registers_updated || 0);
            const statusType = created + updated > 0 ? 'success' : 'loading';
            const message = payload.message || 'Sincronização concluída.';
            setFeedback(message, statusType);

            if (typeof pollOnce === 'function') {
                pollOnce();
            }
        } catch (error) {
            console.error(error);
            setFeedback(error.message || 'Falha ao sincronizar as tags.', 'error');
        } finally {
            button.disabled = false;
        }
    });
}

function initRegisterExchange() {
    const dropzone = document.getElementById('register-import-area');
    const fileInput = document.getElementById('register-import-input');
    const feedbackEl = document.getElementById('register-import-feedback');
    const exportCurrentBtn = document.getElementById('register-export-current');
    const exportAllBtn = document.getElementById('register-export-all');
    const formatSelect = document.getElementById('register-export-format');

    const plcId = dropzone ? Number(dropzone.dataset.plcId) : NaN;

    function showFeedback(message, type, details) {
        if (!feedbackEl) return;
        feedbackEl.innerHTML = '';
        feedbackEl.className = 'register-feedback';
        if (type) {
            feedbackEl.classList.add(type);
        }
        if (message) {
            const textNode = document.createElement('span');
            textNode.textContent = message;
            feedbackEl.appendChild(textNode);
        }
        if (Array.isArray(details) && details.length > 0) {
            const list = document.createElement('ul');
            list.className = 'text-muted';
            details.forEach((detail) => {
                const li = document.createElement('li');
                li.textContent = detail;
                list.appendChild(li);
            });
            feedbackEl.appendChild(list);
        }
    }

    async function handleFiles(fileList) {
        if (!dropzone || !fileList || fileList.length === 0) return;
        if (!Number.isFinite(plcId) || plcId <= 0) {
            showFeedback('Identificador do CLP inválido para importação.', 'error');
            return;
        }
        const file = fileList[0];
        const formData = new FormData();
        formData.append('file', file, file.name);
        formData.append('clp_id', String(plcId));

        try {
            showFeedback('Importando mapa de registradores…', 'loading');
            const response = await fetch('/api/registers/import', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': getCsrfToken() },
                body: formData,
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.message || 'Não foi possível importar o ficheiro.');
            }

            const created = payload.created ?? 0;
            const errors = payload.errors || [];
            const message = errors.length
                ? `Importação concluída com ${created} registradores adicionados. Algumas linhas exigem revisão.`
                : `Importação concluída: ${created} registradores adicionados.`;
            showFeedback(message, errors.length ? 'loading' : 'success', errors);

            if (fileInput) {
                fileInput.value = '';
            }
        } catch (error) {
            console.error(error);
            showFeedback(error.message || 'Falha ao importar o mapa.', 'error');
        }
    }

    async function triggerExport(scope) {
        const format = (formatSelect && formatSelect.value) || 'csv';
        let url = '';
        if (scope === 'current') {
            if (!Number.isFinite(plcId) || plcId <= 0) {
                showFeedback('CLP inválido para exportação.', 'error');
                return;
            }
            url = `/api/registers/export?clp_id=${encodeURIComponent(plcId)}&format=${encodeURIComponent(format)}`;
        } else {
            url = `/api/registers/export/all?format=${encodeURIComponent(format)}`;
        }

        try {
            showFeedback('Preparando exportação…', 'loading');
            const response = await fetch(url, { credentials: 'same-origin' });
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload.message || 'Não foi possível exportar os registradores.');
            }

            const blob = await response.blob();
            let filename = 'export.csv';
            const disposition = response.headers.get('Content-Disposition');
            if (disposition) {
                const match = disposition.match(/filename="?([^";]+)"?/i);
                if (match && match[1]) {
                    filename = match[1];
                }
            }

            const link = document.createElement('a');
            const href = URL.createObjectURL(blob);
            link.href = href;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(href);
            showFeedback('Exportação preparada com sucesso.', 'success');
        } catch (error) {
            console.error(error);
            showFeedback(error.message || 'Falha ao exportar os registradores.', 'error');
        }
    }

    if (dropzone) {
        ['dragenter', 'dragover'].forEach((eventName) => {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                dropzone.classList.add('dragover');
            });
        });
        ['dragleave', 'drop'].forEach((eventName) => {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                if (eventName === 'drop') {
                    handleFiles(event.dataTransfer?.files);
                }
                dropzone.classList.remove('dragover');
            });
        });
        dropzone.addEventListener('click', () => {
            if (fileInput) fileInput.click();
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', () => {
            handleFiles(fileInput.files);
        });
    }

    if (exportCurrentBtn) {
        exportCurrentBtn.addEventListener('click', () => triggerExport('current'));
    }
    if (exportAllBtn) {
        exportAllBtn.addEventListener('click', () => triggerExport('all'));
    }
}

function renderTagList(tags) {
    const list = document.getElementById('tag-list-container');
    if (!list) return;

    list.innerHTML = '';
    if (!Array.isArray(tags) || tags.length === 0) {
        const placeholder = document.createElement('li');
        placeholder.id = 'no-tags-msg';
        placeholder.textContent = 'Nenhuma tag associada.';
        list.appendChild(placeholder);
        return;
    }

    tags.forEach((tag) => {
        const item = document.createElement('li');
        item.className = 'tag-item';
        item.innerHTML = `<span>${tag}</span><span class="remove-tag" data-tag="${tag}" title="Remover Tag">&times;</span>`;
        list.appendChild(item);
    });

    ensureNoTagsMessage();
}

function ensureNoTagsMessage() {
    const list = document.getElementById('tag-list-container');
    if (!list) return;
    const hasTags = list.querySelectorAll('.tag-item').length > 0;
    let placeholder = document.getElementById('no-tags-msg');
    if (!hasTags) {
        if (!placeholder) {
            placeholder = document.createElement('li');
            placeholder.id = 'no-tags-msg';
            placeholder.textContent = 'Nenhuma tag associada.';
            list.appendChild(placeholder);
        }
    } else if (placeholder) {
        placeholder.remove();
    }
}

function appendTagToList(tag) {
    const list = document.getElementById('tag-list-container');
    if (!list) return;

    const item = document.createElement('li');
    item.className = 'tag-item';
    item.innerHTML = `<span>${tag}</span><span class="remove-tag" data-tag="${tag}" title="Remover Tag">&times;</span>`;
    list.appendChild(item);
    ensureNoTagsMessage();
}

function removeTagFromList(tag) {
    const list = document.getElementById('tag-list-container');
    if (!list) return;
    const escaped = window.CSS && typeof window.CSS.escape === 'function'
        ? CSS.escape(tag)
        : tag.replace(/"/g, '\\"');
    const el = list.querySelector(`.remove-tag[data-tag="${escaped}"]`);
    if (el) {
        const parent = el.closest('.tag-item');
        if (parent) parent.remove();
    }
    ensureNoTagsMessage();
}

function showTagMessage(message, type = 'info') {
    const container = document.getElementById('tagMessage');
    if (!container) return;
    container.textContent = message;
    container.className = `tag-message tag-${type}`;
}

async function sendTagRequest(ip, vlan, method, body) {
    const hasBody = method !== 'DELETE' && body;
    const headers = { 'X-CSRFToken': getCsrfToken() };
    if (hasBody) {
        headers['Content-Type'] = 'application/json';
    }
    const url = TAGS_PATH(ip, vlan, method === 'DELETE' ? body?.tag : null);
    const response = await fetch(url, {
        method,
        headers,
        body: hasBody ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.message || 'Operação de tags falhou.');
    }
    return response.json().catch(() => ({}));
}

function initTagManagement() {
    const form = document.getElementById('formAddTag');
    const input = document.getElementById('inputTag');
    const list = document.getElementById('tag-list-container');
    const ip = getClpIpFromDom();
    const vlan = getClpVlanFromDom();

    if (!form || !input || !list || !ip) {
        return;
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const raw = input.value.trim();
        if (!raw) return;
        try {
            const payload = await sendTagRequest(ip, vlan, 'POST', { tag: raw });
            const added = payload.tag || raw.toLowerCase();
            appendTagToList(added);
            input.value = '';
            showTagMessage('Tag adicionada com sucesso!', 'success');
        } catch (error) {
            console.error(error);
            showTagMessage(error.message || 'Não foi possível adicionar a tag.', 'error');
        }
    });

    list.addEventListener('click', async (event) => {
        const target = event.target;
        if (!target.classList.contains('remove-tag')) return;
        const tag = target.dataset.tag;
        if (!tag) return;
        try {
            await sendTagRequest(ip, vlan, 'DELETE', { tag });
            removeTagFromList(tag);
            showTagMessage(`Tag "${tag}" removida.`, 'success');
        } catch (error) {
            console.error(error);
            showTagMessage(error.message || 'Não foi possível remover a tag.', 'error');
        }
    });

    ensureNoTagsMessage();
}

function showScriptStatus(message, type = 'info', element) {
    const statusEl = element || document.getElementById('script-status');
    if (!statusEl) return;
    statusEl.textContent = message || '';
    statusEl.dataset.state = type;
}

function initProgrammingTabs() {
    const tabs = document.querySelectorAll('.programming-tab');
    const panels = document.querySelectorAll('.programming-panel');
    if (!tabs.length || !panels.length) return;

    const activate = (target) => {
        tabs.forEach((tab) => {
            tab.classList.toggle('active', tab.dataset.programmingTab === target);
        });
        panels.forEach((panel) => {
            panel.classList.toggle('active', panel.dataset.programmingPanel === target);
        });
        if (target === 'editor') {
            setTimeout(() => {
                if (monacoEditorInstance) {
                    monacoEditorInstance.layout();
                }
            }, 50);
        }
    };

    tabs.forEach((tab) => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.programmingTab;
            if (target) {
                activate(target);
            }
        });
    });

    const initial = Array.from(tabs).find((tab) => tab.classList.contains('active'))?.dataset.programmingTab || 'docs';
    activate(initial);
}

function populateLanguageOptions(select, languages) {
    if (!select) return;
    const entries = Object.entries(languages || {});
    const previous = select.value;
    select.innerHTML = '';
    if (!entries.length) {
        const option = document.createElement('option');
        option.value = 'python';
        option.textContent = 'Python';
        select.appendChild(option);
        select.value = 'python';
        return;
    }
    entries.forEach(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
    });
    if (entries.some(([value]) => value === previous)) {
        select.value = previous;
    }
}

function renderScriptList(scripts, languages, container) {
    const list = container || document.getElementById('script-list');
    if (!list) return;
    list.innerHTML = '';
    if (!scripts || !scripts.length) {
        const empty = document.createElement('li');
        empty.className = 'script-empty';
        empty.textContent = 'Nenhum script cadastrado.';
        list.appendChild(empty);
        return;
    }
    scripts.forEach((script) => {
        const item = document.createElement('li');
        item.dataset.scriptId = script.id;
        if (selectedScriptId === script.id) {
            item.classList.add('active');
        }
        const selectBtn = document.createElement('button');
        selectBtn.type = 'button';
        selectBtn.className = 'script-select';
        selectBtn.textContent = script.name;
        const lang = document.createElement('span');
        lang.className = 'script-language';
        lang.textContent = (languages && languages[script.language]) || script.language;
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'script-delete';
        deleteBtn.innerHTML = '&times;';
        deleteBtn.setAttribute('aria-label', `Excluir script ${script.name}`);
        item.appendChild(selectBtn);
        item.appendChild(lang);
        item.appendChild(deleteBtn);
        list.appendChild(item);
    });
}

function highlightSelectedScript(scriptId) {
    const list = document.getElementById('script-list');
    if (!list) return;
    list.querySelectorAll('li').forEach((item) => {
        const current = Number(item.dataset.scriptId);
        item.classList.toggle('active', scriptId != null && current === scriptId);
    });
}

async function loadScripts(plcId, languageSelect, listContainer, statusEl, nameInput) {
    try {
        const response = await fetch(SCRIPTS_ENDPOINT(plcId), { credentials: 'same-origin' });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.message || 'Erro ao carregar scripts.');
        }
        scriptLanguages = payload.languages || {};
        currentScripts = payload.scripts || [];
        populateLanguageOptions(languageSelect, scriptLanguages);
        renderScriptList(currentScripts, scriptLanguages, listContainer);
        if (selectedScriptId && !currentScripts.some((script) => script.id === selectedScriptId)) {
            selectedScriptId = null;
        }
        if (!selectedScriptId && currentScripts.length) {
            const first = currentScripts[0];
            selectedScriptId = first.id;
            if (nameInput) nameInput.value = first.name || '';
            if (languageSelect) {
                languageSelect.value = first.language;
            }
            if (monacoEditorInstance) {
                const lang = monacoLanguageFor(first.language);
                monaco.editor.setModelLanguage(monacoEditorInstance.getModel(), lang);
                monacoEditorInstance.setValue(first.content || '');
            }
        }
        highlightSelectedScript(selectedScriptId);
        if (!currentScripts.length) {
            showScriptStatus('Nenhum script cadastrado até o momento.', 'info', statusEl);
        }
    } catch (error) {
        console.error(error);
        showScriptStatus(error.message || 'Erro ao carregar scripts.', 'error', statusEl);
    }
}

async function saveCurrentScript(plcId, nameInput, languageSelect, statusEl) {
    if (!monacoEditorInstance) return;
    const name = nameInput?.value.trim();
    const language = languageSelect?.value || 'python';
    const content = monacoEditorInstance.getValue();
    if (!name) {
        showScriptStatus('Informe o nome do script.', 'error', statusEl);
        return;
    }
    if (!content.trim()) {
        showScriptStatus('O conteúdo do script está vazio.', 'error', statusEl);
        return;
    }
    try {
        const response = await fetch(SCRIPTS_ENDPOINT(plcId), {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ name, language, content }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.message || 'Erro ao guardar script.');
        }
        selectedScriptId = payload.id;
        showScriptStatus(`Script "${payload.name}" guardado com sucesso.`, 'success', statusEl);
        await loadScripts(plcId, languageSelect, document.getElementById('script-list'), statusEl, nameInput);
        highlightSelectedScript(selectedScriptId);
    } catch (error) {
        console.error(error);
        showScriptStatus(error.message || 'Erro ao guardar script.', 'error', statusEl);
    }
}

async function deleteScript(plcId, scriptId, statusEl) {
    try {
        const response = await fetch(SCRIPTS_ENDPOINT(plcId, scriptId), {
            method: 'DELETE',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': getCsrfToken() },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.message || 'Erro ao remover script.');
        }
        if (selectedScriptId === scriptId) {
            selectedScriptId = null;
            if (monacoEditorInstance) {
                monacoEditorInstance.setValue('');
            }
        }
        showScriptStatus('Script removido com sucesso.', 'success', statusEl);
        await loadScripts(
            plcId,
            document.getElementById('script-language'),
            document.getElementById('script-list'),
            statusEl,
            document.getElementById('script-name')
        );
        highlightSelectedScript(selectedScriptId);
    } catch (error) {
        console.error(error);
        showScriptStatus(error.message || 'Erro ao remover script.', 'error', statusEl);
    }
}

function initScriptEditor() {
    const container = document.getElementById('script-editor');
    if (!container) return;
    const plcId = Number(container.dataset.plcId);
    if (!plcId) return;

    const nameInput = document.getElementById('script-name');
    const languageSelect = document.getElementById('script-language');
    const saveButton = document.getElementById('script-save');
    const statusEl = document.getElementById('script-status');
    const listContainer = document.getElementById('script-list');

    if (typeof window.require === 'undefined') {
        console.error('Monaco loader não encontrado.');
        return;
    }

    window.require.config({
        paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' }
    });
    window.MonacoEnvironment = {
        getWorkerUrl() {
            const proxy = "self.MonacoEnvironment={baseUrl:'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/'};" +
                "importScripts('https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/base/worker/workerMain.js');";
            return `data:text/javascript;charset=utf-8,${encodeURIComponent(proxy)}`;
        }
    };

    window.require(['vs/editor/editor.main'], () => {
        monacoEditorInstance = monaco.editor.create(container, {
            value: '',
            language: monacoLanguageFor(languageSelect?.value || 'python'),
            theme: 'vs-dark',
            automaticLayout: true,
            minimap: { enabled: false },
        });

        const editorPanel = document.querySelector('[data-programming-panel="editor"]');
        if (editorPanel?.classList.contains('active')) {
            setTimeout(() => monacoEditorInstance?.layout(), 0);
        }

        loadScripts(plcId, languageSelect, listContainer, statusEl, nameInput);

        if (saveButton) {
            saveButton.addEventListener('click', () => {
                saveCurrentScript(plcId, nameInput, languageSelect, statusEl);
            });
        }

        if (languageSelect) {
            languageSelect.addEventListener('change', () => {
                if (!monacoEditorInstance) return;
                const lang = monacoLanguageFor(languageSelect.value);
                monaco.editor.setModelLanguage(monacoEditorInstance.getModel(), lang);
            });
        }

        if (listContainer) {
            listContainer.addEventListener('click', (event) => {
                const target = event.target;
                const item = target.closest('li');
                if (!item) return;
                const scriptId = Number(item.dataset.scriptId);
                if (target.classList.contains('script-delete')) {
                    if (scriptId) {
                        deleteScript(plcId, scriptId, statusEl);
                    }
                    return;
                }
                if (target.classList.contains('script-select') && scriptId) {
                    const script = currentScripts.find((entry) => entry.id === scriptId);
                    if (!script) return;
                    selectedScriptId = script.id;
                    highlightSelectedScript(script.id);
                    if (nameInput) nameInput.value = script.name || '';
                    if (languageSelect) {
                        languageSelect.value = script.language;
                        const lang = monacoLanguageFor(script.language);
                        monaco.editor.setModelLanguage(monacoEditorInstance.getModel(), lang);
                    }
                    if (monacoEditorInstance) {
                        monacoEditorInstance.setValue(script.content || '');
                        monacoEditorInstance.focus();
                    }
                    showScriptStatus(`Script "${script.name}" carregado.`, 'info', statusEl);
                }
            });
        }
    });
}

function refreshActiveCharts() {
    if (!charts.size) return;
    requestAnimationFrame(() => {
        charts.forEach((chart) => {
            if (chart && typeof chart.resize === 'function') {
                chart.resize();
                chart.update('none');
            }
        });
    });
}

function initDetailTabs() {
    const tabs = Array.from(document.querySelectorAll('[data-tab-target]'));
    const panels = Array.from(document.querySelectorAll('[data-tab-panel]'));
    if (!tabs.length || !panels.length) {
        return;
    }

    const activate = (target) => {
        tabs.forEach((tab) => {
            const isActive = tab.dataset.tabTarget === target;
            tab.classList.toggle('active', isActive);
            tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
            tab.setAttribute('tabindex', isActive ? '0' : '-1');
        });

        panels.forEach((panel) => {
            const isActive = panel.dataset.tabPanel === target;
            panel.classList.toggle('active', isActive);
            panel.toggleAttribute('hidden', !isActive);
            panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
        });

        if (target === 'operacao') {
            if (!tagManagementInitialized) {
                initTagManagement();
                tagManagementInitialized = true;
            }
            startPolling();
            refreshActiveCharts();
        } else {
            stopPolling();
        }

        if (target === 'configuracao') {
            if (!tagManagementInitialized) {
                initTagManagement();
                tagManagementInitialized = true;
            }
            if (!autoDiscoveryInitialized) {
                initAutoDiscoverySync();
                autoDiscoveryInitialized = true;
            }
        }

        if (target === 'seguranca' && !registerExchangeInitialized) {
            initRegisterExchange();
            registerExchangeInitialized = true;
        }
    };

    tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tabTarget;
            if (!target || tab.classList.contains('active')) {
                return;
            }
            activate(target);
        });

        tab.addEventListener('keydown', (event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
                return;
            }
            event.preventDefault();
            let newIndex = index;
            if (event.key === 'ArrowRight') {
                newIndex = (index + 1) % tabs.length;
            } else if (event.key === 'ArrowLeft') {
                newIndex = (index - 1 + tabs.length) % tabs.length;
            } else if (event.key === 'Home') {
                newIndex = 0;
            } else if (event.key === 'End') {
                newIndex = tabs.length - 1;
            }
            const nextTab = tabs[newIndex];
            if (nextTab) {
                nextTab.focus();
                nextTab.click();
            }
        });
    });

    const initialTab = tabs.find((tab) => tab.classList.contains('active'))?.dataset.tabTarget || tabs[0].dataset.tabTarget;
    activate(initialTab);
}

window.addEventListener('DOMContentLoaded', () => {
    initDetailTabs();
    initProgrammingTabs();
    initScriptEditor();
});
