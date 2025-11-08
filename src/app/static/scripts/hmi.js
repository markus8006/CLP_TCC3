(function () {
  const feedbackEl = document.getElementById('hmi-feedback');
  const synopticCanvas = document.getElementById('synoptic-canvas');
  const trendSelect = document.getElementById('trend-register-picker');
  const manualSelect = document.getElementById('manual-register');
  const manualForm = document.getElementById('manual-command-form');
  const manualValueInput = document.getElementById('manual-value');
  const manualNoteInput = document.getElementById('manual-note');
  const manualHistoryList = document.getElementById('manual-history-list');
  const alarmList = document.getElementById('alarm-list');
  const reportMetricsDl = document.getElementById('report-metrics');
  const refreshBtn = document.getElementById('refresh-hmi');
  const exportBtn = document.getElementById('export-historian');
  const panelToolList = document.getElementById('synoptic-tool-list');
  const panelPlcList = document.getElementById('panel-plc-list');
  const panelHelpText = document.getElementById('panel-help-text');
  const panelHelpButton = document.getElementById('panel-help-button');

  const context = window.HMI_CONTEXT || {};
  let trendChart;
  const toolDefinitions = [
    {
      id: 'add-component',
      label: 'Adicionar componente',
      description:
        'Clique em uma área vazia do sinótico para posicionar o novo componente e vincular ao CLP correspondente.',
    },
    {
      id: 'select-plc',
      label: 'Selecionar CLP',
      description:
        'Use esta ferramenta para destacar um CLP no sinótico e editar suas propriedades ou registrar observações.',
    },
    {
      id: 'help-guided',
      label: 'Ver instruções rápidas',
      description:
        'Mostra um passo a passo para revisar conexões, ajustar legendas e compartilhar a captura com a equipe.',
    },
  ];

  function setPanelHelp(message) {
    if (!panelHelpText) return;
    panelHelpText.textContent = message;
  }

  function buildToolPanel() {
    if (!panelToolList) return;
    panelToolList.innerHTML = '';
    toolDefinitions.forEach((tool) => {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'panel-tool-button';
      button.dataset.toolId = tool.id;
      button.setAttribute('aria-pressed', 'false');
      button.innerHTML = `${tool.label}<small>${tool.description.split('.')[0]}.</small>`;
      button.addEventListener('click', () => {
        if (!panelToolList) return;
        panelToolList.querySelectorAll('.panel-tool-button').forEach((btn) => {
          btn.setAttribute('aria-pressed', String(btn === button));
        });
        setPanelHelp(tool.description);
        const event = new CustomEvent('hmi:tool-selected', {
          detail: { toolId: tool.id, timestamp: Date.now() },
        });
        document.dispatchEvent(event);
      });
      item.appendChild(button);
      panelToolList.appendChild(item);
    });
  }

  function renderPanelPlcs(areas) {
    if (!panelPlcList) return;
    panelPlcList.innerHTML = '';
    if (!areas || !areas.length) {
      const info = document.createElement('p');
      info.className = 'empty-placeholder';
      info.textContent = 'Nenhum CLP cadastrado. Utilize “Adicionar componente” para começar.';
      panelPlcList.appendChild(info);
      return;
    }

    areas.forEach((area) => {
      const areaEl = document.createElement('div');
      areaEl.className = 'panel-plc-area';
      const title = document.createElement('h3');
      title.textContent = area.name || 'Área sem nome';
      areaEl.appendChild(title);

      (area.plcs || []).forEach((plc) => {
        const plcEl = document.createElement('div');
        plcEl.className = 'panel-plc';
        plcEl.dataset.status = plc.status || 'unknown';
        const plcTitle = document.createElement('strong');
        plcTitle.textContent = plc.name || 'CLP sem nome';
        plcEl.appendChild(plcTitle);

        if (plc.registers && plc.registers.length) {
          const list = document.createElement('ul');
          list.className = 'panel-register-list';
          plc.registers.slice(0, 6).forEach((reg) => {
            const li = document.createElement('li');
            const value = reg.last_value != null ? reg.last_value : '--';
            li.textContent = `${reg.name || 'Registrador'} · ${value}${reg.unit ? ` ${reg.unit}` : ''}`;
            list.appendChild(li);
          });
          plcEl.appendChild(list);
        }

        areaEl.appendChild(plcEl);
      });

      panelPlcList.appendChild(areaEl);
    });
  }

  function setFeedback(message, isError = false) {
    if (!feedbackEl) return;
    feedbackEl.textContent = message || '';
    feedbackEl.classList.toggle('error', Boolean(isError));
  }

  async function fetchJSON(url, options) {
    const opts = options || {};
    opts.headers = Object.assign(
      {
        'Accept': 'application/json'
      },
      opts.headers || {}
    );
    if (context.csrfToken) {
      opts.headers['X-CSRFToken'] = context.csrfToken;
    }
    const response = await fetch(url, opts);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const err = new Error(payload.message || `Erro ao comunicar com ${url}`);
      err.payload = payload;
      err.status = response.status;
      throw err;
    }
    return response.json();
  }

  function formatTimestamp(ts) {
    if (!ts) return '--';
    try {
      return new Date(ts).toLocaleString();
    } catch (error) {
      return ts;
    }
  }

  function renderSynoptic(areas) {
    if (!synopticCanvas) return;
    synopticCanvas.innerHTML = '';
    if (!areas || !areas.length) {
      synopticCanvas.innerHTML =
        '<p class="empty-placeholder">Nenhum CLP cadastrado para esta planta. Use “Adicionar componente” no painel lateral.</p>';
      return;
    }

    areas.forEach((area) => {
      area.plcs.forEach((plc) => {
        const node = document.createElement('div');
        node.className = 'synoptic-node';
        node.dataset.status = plc.status;
        node.innerHTML = `
          <h3>${plc.name}</h3>
          <dl>
            <dt>Protocolo</dt>
            <dd>${plc.protocol || '--'}</dd>
            <dt>Status</dt>
            <dd>${plc.status}</dd>
          </dl>
        `;

        if (Array.isArray(plc.registers) && plc.registers.length) {
          const regs = document.createElement('dl');
          plc.registers.slice(0, 4).forEach((reg) => {
            const dt = document.createElement('dt');
            dt.textContent = reg.name;
            const dd = document.createElement('dd');
            const value = reg.last_value != null ? reg.last_value : '--';
            dd.textContent = `${value}${reg.unit ? ` ${reg.unit}` : ''}`;
            regs.append(dt, dd);
          });
          node.appendChild(regs);
        }

        synopticCanvas.appendChild(node);
      });
    });
  }

  function populateRegisterSelect(selectEl, options) {
    if (!selectEl) return;
    selectEl.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Selecione...';
    selectEl.appendChild(placeholder);

    options.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.id;
      option.textContent = item.label;
      option.dataset.status = item.status;
      selectEl.appendChild(option);
    });
  }

  function updateReportMetrics(metrics) {
    if (!reportMetricsDl) return;
    reportMetricsDl.innerHTML = '';
    if (!metrics) return;
    Object.entries(metrics).forEach(([key, value]) => {
      const dt = document.createElement('dt');
      const dd = document.createElement('dd');
      const label = key
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase());
      dt.textContent = label;
      dd.textContent = value;
      reportMetricsDl.append(dt, dd);
    });
  }

  function renderAlarms(alarms) {
    if (!alarmList) return;
    alarmList.innerHTML = '';
    if (!alarms || !alarms.length) {
      const li = document.createElement('li');
      li.className = 'empty-placeholder';
      li.textContent = 'Nenhum alarme ativo. O painel atualizará automaticamente quando um evento ocorrer.';
      alarmList.appendChild(li);
      return;
    }

    alarms.forEach((alarm) => {
      const li = document.createElement('li');
      li.className = 'alarm-item';
      li.dataset.priority = alarm.priority || 'medium';
      li.innerHTML = `
        <div>
          <strong>${alarm.message}</strong>
          <div class="alarm-meta">${alarm.plc || '--'} · ${alarm.register || '--'}</div>
        </div>
        <div class="alarm-meta">${formatTimestamp(alarm.triggered_at)}</div>
      `;
      alarmList.appendChild(li);
    });
  }

  function renderManualHistory(commands) {
    if (!manualHistoryList) return;
    manualHistoryList.innerHTML = '';
    if (!commands || !commands.length) {
      const li = document.createElement('li');
      li.className = 'empty-placeholder';
      li.textContent = 'Sem comandos manuais registrados. Utilize o formulário acima para registrar intervenções.';
      manualHistoryList.appendChild(li);
      return;
    }

    commands.forEach((command) => {
      const li = document.createElement('li');
      const status = (command.status || '').toUpperCase();
      li.innerHTML = `
        <span><strong>${command.command_type}</strong> → ${command.value_numeric ?? command.value_text ?? '--'}</span>
        <span>${command.executed_by} · ${formatTimestamp(command.created_at)}${status ? ` · ${status}` : ''}</span>
        ${command.note ? `<span>${command.note}</span>` : ''}
        ${command.reviewer_note ? `<span>${command.reviewer_note}</span>` : ''}
      `;
      manualHistoryList.appendChild(li);
    });
  }

  function ensureTrendChart() {
    if (trendChart) return trendChart;
    const canvas = document.getElementById('trend-chart');
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    trendChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Valor',
            data: [],
            borderColor: '#1dd3b0',
            backgroundColor: 'rgba(29, 211, 176, 0.15)',
            tension: 0.25,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          x: {
            type: 'category',
          },
          y: {
            beginAtZero: false,
          },
        },
      },
    });
    return trendChart;
  }

  async function loadTrend(registerId) {
    if (!registerId) {
      setFeedback('Selecione um registrador para visualizar a tendência.');
      return;
    }
    try {
      const data = await fetchJSON(`/api/hmi/register/${registerId}/trend`);
      const chart = ensureTrendChart();
      if (!chart) return;
      chart.data.labels = data.points.map((pt) => formatTimestamp(pt.timestamp));
      chart.data.datasets[0].data = data.points.map((pt) => pt.value ?? null);
      chart.update();
      const subtitle = document.getElementById('trend-subtitle');
      if (subtitle && data.register) {
        subtitle.textContent = `${data.register.name} (${data.register.unit || 'sem unidade'})`;
      }
      setFeedback('Tendência atualizada.');
    } catch (error) {
      setFeedback(error.message, true);
    }
  }

  async function executeManualCommand(event) {
    event.preventDefault();
    if (!context.canControl) return;
    const registerId = manualSelect.value;
    if (!registerId) {
      setFeedback('Selecione o registrador para enviar o comando.', true);
      return;
    }
    const value = manualValueInput.value;
    const note = manualNoteInput.value;
    if (!note || note.trim().length < 5) {
      setFeedback('Inclua uma observação com pelo menos 5 caracteres.', true);
      return;
    }

    try {
      const response = await fetchJSON(`/api/hmi/register/${registerId}/manual`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          value: value,
          note: note,
          command_type: 'setpoint',
        }),
      });
      setFeedback(response?.message || 'Comando enfileirado para aprovação.');
      manualValueInput.value = '';
      manualNoteInput.value = '';
      await Promise.all([loadManualHistory(), loadTrend(registerId)]);
    } catch (error) {
      setFeedback(error.message, true);
    }
  }

  async function loadManualHistory() {
    try {
      const data = await fetchJSON('/api/hmi/manual-commands');
      renderManualHistory(data.commands || []);
    } catch (error) {
      setFeedback(error.message, true);
    }
  }

  async function loadAlarms() {
    try {
      const data = await fetchJSON('/api/hmi/alarms');
      renderAlarms(data.alarms || []);
    } catch (error) {
      setFeedback(error.message, true);
    }
  }

  async function loadOverview() {
    try {
      const data = await fetchJSON('/api/hmi/overview');
      renderSynoptic(data.areas || []);
      renderPanelPlcs(data.areas || []);
      populateRegisterSelect(trendSelect, data.register_options || []);
      if (manualSelect) {
        populateRegisterSelect(manualSelect, data.register_options || []);
      }
      updateReportMetrics(data.report_metrics || {});
      setFeedback('Dados atualizados.');
    } catch (error) {
      setFeedback(error.message, true);
    }
  }

  async function exportHistorian() {
    try {
      const data = await fetchJSON('/api/historian/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      setFeedback(`Histórico exportado (${data.rows} registros) em ${data.file}.`);
    } catch (error) {
      setFeedback(error.message, true);
    }
  }

  async function refreshAll() {
    await Promise.all([loadOverview(), loadAlarms(), loadManualHistory()]);
    const selected = trendSelect && trendSelect.value;
    if (selected) {
      await loadTrend(selected);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    buildToolPanel();
    refreshAll();

    if (trendSelect) {
      trendSelect.addEventListener('change', (event) => {
        const registerId = event.target.value;
        if (registerId) {
          loadTrend(registerId);
          setPanelHelp(
            'Tendência atualizada. Utilize os filtros do painel para comparar registradores relacionados.'
          );
        }
      });
    }

    if (manualForm && context.canControl) {
      manualForm.addEventListener('submit', executeManualCommand);
    }

    if (refreshBtn) {
      refreshBtn.addEventListener('click', refreshAll);
    }

    if (exportBtn && context.isAdmin) {
      exportBtn.addEventListener('click', exportHistorian);
    }

    if (panelHelpButton) {
      panelHelpButton.addEventListener('click', () => {
        setPanelHelp('Solicitação enviada. A equipe será notificada pelo centro de operações.');
        setFeedback('Suporte notificado. Aguarde contato da equipe.', false);
        const event = new CustomEvent('hmi:help-requested', {
          detail: { source: 'panel', timestamp: Date.now() },
        });
        document.dispatchEvent(event);
      });
    }
  });
})();
