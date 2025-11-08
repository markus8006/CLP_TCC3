(function () {
  const tableBody = document.getElementById('alarm-table-body');
  const refreshButton = document.getElementById('refresh-alarms');
  const searchInput = document.getElementById('alarm-search');
  const severitySelect = document.getElementById('alarm-severity');
  const sortSelect = document.getElementById('alarm-sort');
  const lastUpdatedEl = document.getElementById('alarm-last-updated');
  const summaryTotal = document.getElementById('summary-total');
  const summaryCritical = document.getElementById('summary-critical');
  const summaryHigh = document.getElementById('summary-high');
  const summaryMedium = document.getElementById('summary-medium');
  const summaryLow = document.getElementById('summary-low');

  if (!tableBody) {
    return;
  }

  const priorityLabels = {
    critical: 'Crítico',
    high: 'Alta',
    medium: 'Média',
    low: 'Baixa'
  };

  const priorityOrder = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3
  };

  let allAlarms = [];
  let autoRefreshTimer;

  function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  }

  function formatDate(iso) {
    if (!iso) return '--';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
      return iso;
    }
    return date.toLocaleString();
  }

  function formatAge(seconds) {
    if (seconds == null) return '--';
    const totalSeconds = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;

    if (hours > 0) {
      return `${hours}h ${minutes.toString().padStart(2, '0')}m`;
    }
    if (minutes > 0) {
      return `${minutes}m ${secs.toString().padStart(2, '0')}s`;
    }
    return `${secs}s`;
  }

  function updateSummary(alarms) {
    const counts = alarms.reduce(
      (acc, alarm) => {
        const key = (alarm.priority || 'medium').toLowerCase();
        acc.total += 1;
        if (acc[key] != null) {
          acc[key] += 1;
        }
        return acc;
      },
      { total: 0, critical: 0, high: 0, medium: 0, low: 0 }
    );

    summaryTotal.textContent = counts.total;
    summaryCritical.textContent = counts.critical;
    summaryHigh.textContent = counts.high;
    summaryMedium.textContent = counts.medium;
    summaryLow.textContent = counts.low;
  }

  function renderTable(alarms, filteredCount) {
    tableBody.innerHTML = '';

    if (!alarms.length) {
      const row = document.createElement('tr');
      row.className = 'empty-row';
      const cell = document.createElement('td');
      cell.colSpan = 6;
      cell.textContent =
        allAlarms.length && filteredCount === 0
          ? 'Nenhum alarme corresponde aos filtros selecionados.'
          : 'Nenhum alarme ativo no momento.';
      row.appendChild(cell);
      tableBody.appendChild(row);
      return;
    }

    alarms.forEach((alarm) => {
      const priority = (alarm.priority || 'medium').toLowerCase();
      const row = document.createElement('tr');
      row.dataset.priority = priority;

      const priorityCell = document.createElement('td');
      const badge = document.createElement('span');
      badge.className = 'priority-badge';
      badge.textContent = priorityLabels[priority] || alarm.priority || '—';
      priorityCell.appendChild(badge);

      const messageCell = document.createElement('td');
      messageCell.textContent = alarm.message || '—';

      const plcCell = document.createElement('td');
      plcCell.textContent = alarm.plc || '—';

      const registerCell = document.createElement('td');
      registerCell.textContent = alarm.register || '—';

      const triggeredCell = document.createElement('td');
      triggeredCell.textContent = formatDate(alarm.triggered_at);

      const ageCell = document.createElement('td');
      ageCell.textContent = formatAge(alarm.age_seconds);

      row.append(
        priorityCell,
        messageCell,
        plcCell,
        registerCell,
        triggeredCell,
        ageCell
      );
      tableBody.appendChild(row);
    });
  }

  function applyFilters() {
    const query = (searchInput?.value || '').trim().toLowerCase();
    const severity = severitySelect?.value || 'all';
    const sort = sortSelect?.value || 'priority';

    let filtered = allAlarms.slice();

    if (severity !== 'all') {
      filtered = filtered.filter((alarm) => (alarm.priority || '').toLowerCase() === severity);
    }

    if (query) {
      filtered = filtered.filter((alarm) => {
        const fields = [alarm.message, alarm.plc, alarm.register]
          .filter(Boolean)
          .map((value) => value.toLowerCase());
        return fields.some((field) => field.includes(query));
      });
    }

    if (sort === 'priority') {
      filtered.sort((a, b) => {
        const priorityA = priorityOrder[(a.priority || '').toLowerCase()] ?? 99;
        const priorityB = priorityOrder[(b.priority || '').toLowerCase()] ?? 99;
        if (priorityA !== priorityB) {
          return priorityA - priorityB;
        }
        const triggeredA = a.triggered_at ? new Date(a.triggered_at).getTime() : 0;
        const triggeredB = b.triggered_at ? new Date(b.triggered_at).getTime() : 0;
        return triggeredB - triggeredA;
      });
    } else if (sort === 'recent') {
      filtered.sort((a, b) => {
        const triggeredA = a.triggered_at ? new Date(a.triggered_at).getTime() : 0;
        const triggeredB = b.triggered_at ? new Date(b.triggered_at).getTime() : 0;
        return triggeredB - triggeredA;
      });
    } else if (sort === 'older') {
      filtered.sort((a, b) => {
        const triggeredA = a.triggered_at ? new Date(a.triggered_at).getTime() : 0;
        const triggeredB = b.triggered_at ? new Date(b.triggered_at).getTime() : 0;
        return triggeredA - triggeredB;
      });
    }

    renderTable(filtered, filtered.length);
  }

  async function loadAlarms(showLoading = true) {
    if (showLoading && refreshButton) {
      refreshButton.disabled = true;
      refreshButton.textContent = 'Actualizando…';
    }

    const headers = {
      Accept: 'application/json'
    };
    const token = getCsrfToken();
    if (token) {
      headers['X-CSRFToken'] = token;
    }

    try {
      const response = await fetch('/api/hmi/alarms', { headers });
      if (!response.ok) {
        throw new Error(`Erro ${response.status}`);
      }
      const payload = await response.json();
      allAlarms = Array.isArray(payload.alarms) ? payload.alarms : [];
      updateSummary(allAlarms);
      applyFilters();
      if (lastUpdatedEl) {
        lastUpdatedEl.textContent = `Última atualização: ${new Date().toLocaleTimeString()}`;
      }
    } catch (error) {
      allAlarms = [];
      updateSummary(allAlarms);
      renderTable([], 0);
      if (lastUpdatedEl) {
        lastUpdatedEl.textContent = `Erro ao actualizar: ${error.message}`;
      }
    } finally {
      if (refreshButton) {
        refreshButton.disabled = false;
        refreshButton.textContent = 'Atualizar lista';
      }
    }
  }

  function scheduleAutoRefresh() {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer);
    }
    autoRefreshTimer = window.setInterval(() => loadAlarms(false), 60000);
  }

  refreshButton?.addEventListener('click', () => loadAlarms());
  searchInput?.addEventListener('input', () => applyFilters());
  severitySelect?.addEventListener('change', () => applyFilters());
  sortSelect?.addEventListener('change', () => applyFilters());

  loadAlarms();
  scheduleAutoRefresh();
})();
