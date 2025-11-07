(function () {
  const SUMMARY_ENDPOINT = "/api/dashboard/summary";
  const LAYOUT_ENDPOINT = "/api/dashboard/layout";
  const PLC_COLLECTION_ENDPOINT = "/api/dashboard/plcs";
  const PLC_DETAILS_ENDPOINT = (plcId) => `/api/dashboard/clps/${plcId}`;

  const context = window.DASHBOARD_CONTEXT || { isAdmin: false, csrfToken: "" };

  const summaryCards = document.querySelectorAll(".summary-card");
  const incidentList = document.getElementById("incident-list");
  const layoutCanvas = document.getElementById("factory-layout");
  const layoutViewport = document.getElementById("layout-viewport");
  const layoutSection = document.getElementById("factory-layout-section");
  const layoutStatus = document.getElementById("layout-status");
  const toggleEditBtn = document.getElementById("toggle-edit");
  const saveLayoutBtn = document.getElementById("save-layout");
  const fullscreenToggleBtn = document.getElementById("fullscreen-toggle");
  const resetViewBtn = document.getElementById("reset-layout-view");
  const inspector = document.getElementById("plc-inspector");
  const closeInspectorBtn = document.getElementById("close-inspector");
  const inspectorTitle = document.getElementById("inspector-title");
  const inspectorDetails = document.getElementById("inspector-details");
  const inspectorRegisters = document.getElementById("inspector-registers");
  const plcCardList = document.getElementById("plc-card-list");
  const exportAllBtn = document.getElementById("dashboard-export-all");
  const exportFormatSelect = document.getElementById("dashboard-export-format");
  const exportFeedback = document.getElementById("dashboard-export-feedback");

  let isEditMode = false;
  const editable = layoutCanvas?.dataset?.editable === "true";
  let layoutData = { nodes: [], connections: [] };
  let logChart;
  let alarmChart;
  const panState = { x: 0, y: 0 };
  const zoomState = { level: 1, min: 0.5, max: 2.5, step: 0.1 };
  let isPanning = false;
  let panPointerId = null;
  let panStart = { x: 0, y: 0 };
  let pointerStart = { x: 0, y: 0 };
  let selectedNodeId = null;
  const plcCardState = new Map();

  function showStatusMessage(message, variant = "info") {
    if (!layoutStatus) return;
    layoutStatus.textContent = message;
    layoutStatus.className = `layout-status-message ${variant}`;
  }

  function showExportFeedback(message, variant = "info") {
    if (!exportFeedback) return;
    exportFeedback.textContent = message || "";
    exportFeedback.classList.remove("success", "error", "loading");
    if (variant && variant !== "info") {
      exportFeedback.classList.add(variant);
    }
  }

  async function exportAllRegisters() {
    if (!exportAllBtn) return;
    const format = exportFormatSelect?.value || "xlsx";
    const url = `/api/registers/export/all?format=${encodeURIComponent(format)}`;
    try {
      showExportFeedback("Preparando exportação…", "loading");
      const response = await fetch(url, { credentials: "same-origin" });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.message || "Não foi possível exportar os registradores.");
      }

      const blob = await response.blob();
      let filename = `clps.${format}`;
      const disposition = response.headers.get("Content-Disposition");
      if (disposition) {
        const match = disposition.match(/filename="?([^";]+)"?/i);
        if (match && match[1]) {
          filename = match[1];
        }
      }

      const link = document.createElement("a");
      const href = URL.createObjectURL(blob);
      link.href = href;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(href);
      showExportFeedback("Exportação preparada com sucesso.", "success");
    } catch (error) {
      console.error(error);
      showExportFeedback(error.message || "Falha ao exportar os registradores.", "error");
    }
  }

  function safeFetch(url, options = {}) {
    const headers = Object.assign({}, options.headers);
    if (context.csrfToken) {
      headers["X-CSRFToken"] = context.csrfToken;
    }
    return fetch(url, Object.assign({}, options, { headers, credentials: "same-origin" }))
      .then((response) => {
        if (!response.ok) {
          return response.json().catch(() => ({})).then((payload) => {
            const error = new Error(payload.message || response.statusText);
            error.payload = payload;
            error.status = response.status;
            throw error;
          });
        }
        return response.json();
      });
  }

  function formatMetric(value) {
    if (value === null || value === undefined) {
      return "--";
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return value.toLocaleString("pt-BR");
    }
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }
    return String(value);
  }

  function updateSummaryCards(summary) {
    summaryCards.forEach((card) => {
      const key = card.dataset.summary;
      if (!key) return;
      const metric = card.querySelector(".metric");
      if (metric) {
        const value = summary[key.replace(/-/g, "_")] ?? "--";
        metric.textContent = formatMetric(value);
      }
    });
  }

  function buildLogChart(data) {
    const ctx = document.getElementById("logVolumeChart");
    if (!ctx) return;
    const labels = data.map((item) => item.date);
    const values = data.map((item) => item.count);

    if (logChart) {
      logChart.data.labels = labels;
      logChart.data.datasets[0].data = values;
      logChart.update();
      return;
    }

    logChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Leituras registradas",
            data: values,
            borderColor: "#22d3ee",
            backgroundColor: "rgba(34, 211, 238, 0.25)",
            tension: 0.35,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              color: "#cbd5f5",
            },
          },
          x: {
            ticks: {
              color: "#94a3b8",
            },
          },
        },
        plugins: {
          legend: {
            labels: { color: "#e2e8f0" },
          },
        },
      },
    });
  }

  function buildAlarmChart(alarms) {
    const ctx = document.getElementById("alarmDistributionChart");
    if (!ctx) return;

    const labels = Object.keys(alarms);
    const values = labels.map((key) => alarms[key]);

    if (alarmChart) {
      alarmChart.data.labels = labels;
      alarmChart.data.datasets[0].data = values;
      alarmChart.update();
      return;
    }

    alarmChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels,
        datasets: [
          {
            label: "Alarmes",
            data: values,
            backgroundColor: ["#22c55e", "#facc15", "#f97316", "#ef4444"],
            borderColor: "transparent",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: "#e2e8f0" },
          },
        },
      },
    });
  }

  function renderIncidents(incidents) {
    if (!incidentList) return;
    incidentList.innerHTML = "";
    if (!incidents.length) {
      const li = document.createElement("li");
      li.textContent = "Nenhum incidente crítico no momento.";
      li.className = "incident-item";
      incidentList.appendChild(li);
      return;
    }

    incidents.forEach((incident) => {
      const li = document.createElement("li");
      li.className = "incident-item";
      const locationLabel = incident.location ? ` · ${incident.location}` : "";
      const ipLabel = incident.ip ? ` · ${incident.ip}` : "";
      li.innerHTML = `<span>${incident.name}${ipLabel}${locationLabel}</span><span>${incident.reason}</span>`;
      incidentList.appendChild(li);
    });
  }

  function formatTimestamp(timestamp) {
    if (!timestamp) return "--";
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
      return timestamp;
    }
    return date.toLocaleString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  }

  function formatTimeLabel(timestamp) {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
      return timestamp;
    }
    return date.toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function renderPlcCards(plcs) {
    if (!plcCardList) return;
    plcCardList.innerHTML = "";
    plcCardState.clear();

    if (!plcs.length) {
      const emptyMessage = document.createElement("p");
      emptyMessage.className = "plc-card-empty";
      emptyMessage.textContent =
        plcCardList.dataset.emptyText || "Nenhum CLP cadastrado.";
      plcCardList.appendChild(emptyMessage);
      return;
    }

    plcs.forEach((plc) => {
      const wrapper = document.createElement("details");
      wrapper.className = `plc-card status-${plc.status}`;
      wrapper.dataset.plcId = plc.id;
      if (plc.alarm_count) {
        wrapper.classList.add("has-alarm");
      }

      const summary = document.createElement("summary");
      summary.className = "plc-card-summary";
      summary.innerHTML = `
        <span class="plc-card-heading">
          <span class="plc-card-name">${plc.name}</span>
          <span class="plc-card-ip">${plc.ip || "-"}</span>
        </span>
        <span class="plc-card-flags">
          <span class="plc-status-pill status-${plc.status}">${plc.status_label}</span>
          <span class="plc-alarm-pill ${plc.alarm_count ? "is-active" : ""}">
            ${plc.alarm_count ? `⚠️ ${plc.alarm_count}` : "🟢 OK"}
          </span>
          <span class="plc-last-read" title="Última leitura">${formatTimestamp(
            plc.last_read
          )}</span>
        </span>
      `;
      wrapper.appendChild(summary);

      const body = document.createElement("div");
      body.className = "plc-card-content";
      body.innerHTML = `<p class="plc-card-hint">Expanda para carregar métricas e logs.</p>`;
      wrapper.appendChild(body);

      wrapper.addEventListener("toggle", () => {
        if (!wrapper.open) {
          return;
        }
        const state = plcCardState.get(plc.id);
        if (!state || !state.loaded) {
          loadPlcCardContent(plc, body, wrapper);
        }
      });

      plcCardList.appendChild(wrapper);
    });
  }

  function loadPlcCardContent(plcMeta, container, wrapper) {
    container.innerHTML = `<p class="plc-card-loading">Carregando dados do CLP...</p>`;

    safeFetch(PLC_DETAILS_ENDPOINT(plcMeta.id))
      .then((details) => {
        plcCardState.set(plcMeta.id, { loaded: true });
        wrapper.dataset.loaded = "true";
        wrapper.classList.toggle("has-alarm", details.status === "alarm");

        const registerMap = new Map(
          (details.registers || []).map((register) => [String(register.id), register])
        );

        const header = document.createElement("div");
        header.className = "plc-card-info";
        header.innerHTML = `
          <div><span>Protocolo:</span><strong>${details.protocol}</strong></div>
          <div><span>Alarmes activos:</span><strong>${details.active_alarm_count}</strong></div>
          <div><span>Registradores:</span><strong>${details.register_count}</strong></div>
          <div><span>Última leitura:</span><strong>${formatTimestamp(
            details.last_log || plcMeta.last_read
          )}</strong></div>
        `;

        const chartContainer = document.createElement("div");
        chartContainer.className = "plc-card-chart";
        const chartCanvas = document.createElement("canvas");
        chartCanvas.width = 600;
        chartCanvas.height = 260;
        chartContainer.appendChild(chartCanvas);

        const telemetryEntries = Object.entries(details.telemetry || {});
        const trendSource = telemetryEntries.find(([, samples]) => samples.length > 1);
        if (trendSource) {
          const [registerId, samples] = trendSource;
          const register = registerMap.get(registerId);
          const heading = document.createElement("h4");
          heading.className = "plc-chart-title";
          heading.textContent = register ? register.name : `Registrador ${registerId}`;
          chartContainer.insertBefore(heading, chartCanvas);
          buildPlcCardChart(chartCanvas, samples, register);
        } else {
          chartContainer.innerHTML = `<p class="plc-card-hint">Sem histórico suficiente para montar gráfico.</p>`;
        }

        const registerList = document.createElement("ul");
        registerList.className = "plc-register-list";
        (details.registers || []).slice(0, 6).forEach((register) => {
          const item = document.createElement("li");
          item.innerHTML = `
            <span class="register-name">${register.name}</span>
            <span class="register-status status-${register.status}">${register.status_label}</span>
            <span class="register-value">${
              register.last_value != null ? register.last_value : "--"
            } ${register.unit || ""}</span>
          `;
          registerList.appendChild(item);
        });

        const logList = document.createElement("ul");
        logList.className = "plc-log-list";
        (details.logs || []).slice(0, 12).forEach((log) => {
          const register = registerMap.get(String(log.register_id));
          const label = register ? register.name : `Reg ${log.register_id || "-"}`;
          const value =
            log.value != null && Number.isFinite(log.value)
              ? Number(log.value).toLocaleString("pt-BR")
              : log.value ?? "--";
          const li = document.createElement("li");
          li.innerHTML = `
            <span class="log-title">${label}</span>
            <span class="log-time">${formatTimeLabel(log.timestamp)}</span>
            <span class="log-value">${value}</span>
          `;
          logList.appendChild(li);
        });

        container.innerHTML = "";
        container.appendChild(header);
        container.appendChild(chartContainer);
        container.appendChild(registerList);
        container.appendChild(logList);
      })
      .catch((error) => {
        container.innerHTML = `<p class="plc-card-error">Erro ao carregar: ${error.message}</p>`;
      });
  }

  function buildPlcCardChart(canvas, samples, register) {
    if (!canvas || !samples || !samples.length || !window.Chart) {
      return null;
    }

    const context = canvas.getContext("2d");
    const labels = samples.map((sample) => formatTimeLabel(sample.timestamp));
    const values = samples.map((sample) => sample.value ?? null);

    return new Chart(context, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: register ? register.name : "Tendência",
            data: values,
            borderColor: "#38bdf8",
            backgroundColor: "rgba(56, 189, 248, 0.2)",
            fill: true,
            tension: 0.35,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            ticks: { color: "#94a3b8" },
          },
          y: {
            ticks: { color: "#e2e8f0" },
          },
        },
        plugins: {
          legend: {
            display: false,
          },
        },
      },
    });
  }

  function formatStatusClass(status) {
    switch (status) {
      case "alarm":
        return "status-alarm";
      case "offline":
        return "status-offline";
      case "inactive":
        return "status-inactive";
      case "online":
      default:
        return "status-online";
    }
  }

  function createNodeElement(node) {
    const element = document.createElement("div");
    element.className = `layout-node ${formatStatusClass(node.status || "online")}`;
    element.style.left = `${node.position?.x || 0}px`;
    element.style.top = `${node.position?.y || 0}px`;
    element.dataset.nodeId = node.id;
    element.dataset.type = node.type;
    element.tabIndex = 0;

    if (editable) {
      element.classList.add("editable");
    }

    const title = document.createElement("p");
    title.className = "node-title";
    title.textContent = node.label || node.name || node.id;
    element.appendChild(title);

    if (node.meta_line) {
      const meta = document.createElement("p");
      meta.className = "node-meta";
      meta.textContent = node.meta_line;
      element.appendChild(meta);
    }

    const locationLabel =
      node.location_label || node.metadata?.location_label || node.metadata?.location;
    if (locationLabel) {
      const location = document.createElement("p");
      location.className = "node-location";
      location.textContent = locationLabel;
      element.appendChild(location);
    }

    element.addEventListener("click", () => handleNodeSelection(node));
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        handleNodeSelection(node);
      }
    });

    if (editable && !window.interact) {
      enableDrag(element);
    }

    return element;
  }

  function clearLayout() {
    if (!layoutCanvas) return;
    layoutCanvas.innerHTML = "";
  }

  function updateCanvasTransform() {
    if (!layoutCanvas) return;
    layoutCanvas.style.transform = `translate(${panState.x}px, ${panState.y}px) scale(${zoomState.level})`;
  }

  function persistNodePosition(element) {
    if (!element || !layoutData?.nodes) return;
    const nodeId = element.dataset.nodeId;
    if (!nodeId) return;
    const x = parseFloat(element.dataset.x ?? element.style.left) || 0;
    const y = parseFloat(element.dataset.y ?? element.style.top) || 0;
    const target = (layoutData.nodes || []).find((node) => node.id === nodeId);
    if (target) {
      target.position = { x, y };
    }
  }

  function initializeInteractForNodes() {
    if (!editable || !window.interact || !layoutCanvas) return;

    if (window.interact.isSet?.(".layout-node.editable")) {
      window.interact(".layout-node.editable").unset();
    }

    window.interact(".layout-node.editable").draggable({
      listeners: {
        start(event) {
          const target = event.target;
          target.dataset.dragging = "true";
          target.dataset.x = parseFloat(target.style.left) || 0;
          target.dataset.y = parseFloat(target.style.top) || 0;
        },
        move(event) {
          const target = event.target;
          const currentX = parseFloat(target.dataset.x) || 0;
          const currentY = parseFloat(target.dataset.y) || 0;
          const deltaX = event.dx / zoomState.level;
          const deltaY = event.dy / zoomState.level;
          const nextX = Math.max(0, currentX + deltaX);
          const nextY = Math.max(0, currentY + deltaY);
          target.dataset.x = nextX;
          target.dataset.y = nextY;
          target.style.left = `${nextX}px`;
          target.style.top = `${nextY}px`;
          updateConnectionOverlay();
        },
        end(event) {
          const target = event.target;
          target.dataset.dragging = "false";
          persistNodePosition(target);
        },
      },
    });
  }

  function getCanvasCoordinates(event) {
    if (!layoutCanvas) {
      return { x: 0, y: 0 };
    }

    const rect = layoutCanvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) / zoomState.level;
    const y = (event.clientY - rect.top) / zoomState.level;

    return { x, y };
  }

  function renderLayout(layout) {
    if (!layoutCanvas) return;

    layoutData = layout;
    clearLayout();

    const fragment = document.createDocumentFragment();
    layout.nodes.forEach((node) => {
      const element = createNodeElement(node);
      fragment.appendChild(element);
    });

    layoutCanvas.appendChild(fragment);
    drawConnections(layout.connections);
    updateCanvasTransform();
    initializeInteractForNodes();

    if (selectedNodeId) {
      updateSelectedNode(selectedNodeId);
    }
  }

  function drawConnections(connections) {
    if (!layoutCanvas) return;
    const nodes = new Map();
    layoutCanvas.querySelectorAll(".layout-node").forEach((node) => {
      nodes.set(node.dataset.nodeId, node);
    });

    connections.forEach((connection) => {
      const source = nodes.get(connection.source);
      const target = nodes.get(connection.target);
      if (!source || !target) return;

      const line = document.createElement("div");
      line.className = "layout-connection";

      const sourceRect = source.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const canvasRect = layoutCanvas.getBoundingClientRect();

      const x1 = sourceRect.left + sourceRect.width / 2 - canvasRect.left;
      const y1 = sourceRect.top + sourceRect.height / 2 - canvasRect.top;
      const x2 = targetRect.left + targetRect.width / 2 - canvasRect.left;
      const y2 = targetRect.top + targetRect.height / 2 - canvasRect.top;

      const length = Math.hypot(x2 - x1, y2 - y1);
      const angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;

      line.style.width = `${length}px`;
      line.style.left = `${x1}px`;
      line.style.top = `${y1}px`;
      line.style.transform = `rotate(${angle}deg)`;

      layoutCanvas.appendChild(line);
    });
  }

  function enableDrag(element) {
    let pointerActive = false;
    let offsetX = 0;
    let offsetY = 0;

    element.addEventListener("pointerdown", (event) => {
      if (!isEditMode || (event.button !== undefined && event.button !== 0)) return;

      pointerActive = true;
      element.setPointerCapture?.(event.pointerId);

      const pointer = getCanvasCoordinates(event);
      const currentLeft = parseFloat(element.style.left);
      const currentTop = parseFloat(element.style.top);

      offsetX = pointer.x - (Number.isFinite(currentLeft) ? currentLeft : 0);
      offsetY = pointer.y - (Number.isFinite(currentTop) ? currentTop : 0);

      element.dataset.dragging = "true";
      event.preventDefault();
      event.stopPropagation();
    });

    element.addEventListener("pointermove", (event) => {
      if (!pointerActive || !isEditMode) return;
      const pointer = getCanvasCoordinates(event);
      const x = pointer.x - offsetX;
      const y = pointer.y - offsetY;
      element.style.left = `${Math.max(0, x)}px`;
      element.style.top = `${Math.max(0, y)}px`;
      updateConnectionOverlay();
      event.preventDefault();
    });

    element.addEventListener("pointerup", (event) => {
      if (!pointerActive) return;
      pointerActive = false;
      element.releasePointerCapture?.(event.pointerId);
      element.dataset.dragging = "false";
      persistNodePosition(element);
      updateConnectionOverlay();
      event.preventDefault();
    });

    element.addEventListener("pointercancel", () => {
      pointerActive = false;
      element.dataset.dragging = "false";
      updateConnectionOverlay();
    });
  }

  function updateConnectionOverlay() {
    layoutCanvas.querySelectorAll(".layout-connection").forEach((line) => line.remove());
    drawConnections(layoutData.connections || []);
    updateCanvasTransform();
  }

  function resetLayoutView({ silent = false } = {}) {
    panState.x = 0;
    panState.y = 0;
    zoomState.level = 1;
    updateCanvasTransform();
    if (!silent) {
      showStatusMessage("Visão recentralizada e zoom redefinido");
    }
  }

  function isFullscreenActive() {
    return Boolean(layoutSection) && document.fullscreenElement === layoutSection;
  }

  function updateFullscreenButton() {
    if (!fullscreenToggleBtn) return;
    fullscreenToggleBtn.textContent = isFullscreenActive()
      ? "Sair da tela cheia"
      : "Tela cheia";
  }

  function toggleFullscreen() {
    if (!layoutSection) return;
    if (isFullscreenActive()) {
      if (document.exitFullscreen) {
        try {
          const result = document.exitFullscreen();
          if (result && typeof result.catch === "function") {
            result.catch(() => {
              /* ignore */
            });
          }
        } catch (error) {
          /* ignore */
        }
      }
      return;
    }
    if (layoutSection.requestFullscreen) {
      try {
        const result = layoutSection.requestFullscreen();
        if (result && typeof result.catch === "function") {
          result.catch(() => {
            showStatusMessage("Não foi possível entrar em tela cheia", "warning");
          });
        }
      } catch (error) {
        showStatusMessage("Não foi possível entrar em tela cheia", "warning");
      }
    } else {
      showStatusMessage("Tela cheia não suportada neste navegador", "warning");
    }
  }

  function handleFullscreenChange() {
    if (!layoutSection) return;
    layoutSection.classList.toggle("is-fullscreen", isFullscreenActive());
    updateFullscreenButton();
  }

  function initializePanning() {
    if (!layoutViewport || !layoutCanvas) return;

    const startPan = (event) => {
      if (event.button !== 0) return;
      if (event.target.closest(".layout-node")) {
        return;
      }
      isPanning = true;
      panPointerId = event.pointerId;
      panStart = { x: panState.x, y: panState.y };
      pointerStart = { x: event.clientX, y: event.clientY };
      layoutViewport.setPointerCapture?.(event.pointerId);
      layoutViewport.classList.add("is-panning");
      event.preventDefault();
    };

    const movePan = (event) => {
      if (!isPanning || event.pointerId !== panPointerId) return;
      panState.x = panStart.x + (event.clientX - pointerStart.x);
      panState.y = panStart.y + (event.clientY - pointerStart.y);
      updateCanvasTransform();
    };

    const endPan = (event) => {
      if (!isPanning || (event && event.pointerId !== panPointerId)) return;
      isPanning = false;
      panPointerId = null;
      layoutViewport.classList.remove("is-panning");
      if (event && layoutViewport.releasePointerCapture) {
        try {
          layoutViewport.releasePointerCapture(event.pointerId);
        } catch (error) {
          /* ignore */
        }
      }
    };

    layoutViewport.addEventListener("pointerdown", startPan);
    layoutViewport.addEventListener("pointermove", movePan);
    layoutViewport.addEventListener("pointerup", endPan);
    layoutViewport.addEventListener("pointercancel", endPan);
    layoutViewport.addEventListener("pointerleave", (event) => {
      if (!isPanning) return;
      endPan(event);
    });
  }

  function updateSelectedNode(nodeId) {
    if (!layoutCanvas) return;

    layoutCanvas
      .querySelectorAll(".layout-node.is-selected")
      .forEach((element) => element.classList.remove("is-selected"));

    if (!nodeId) {
      selectedNodeId = null;
      return;
    }

    const selector = `.layout-node[data-node-id="${CSS.escape(nodeId)}"]`;
    const element = layoutCanvas.querySelector(selector);
    if (element) {
      element.classList.add("is-selected");
      selectedNodeId = nodeId;
    } else {
      selectedNodeId = null;
    }
  }

  function handleNodeSelection(node) {
    if (!node) return;
    updateSelectedNode(node.id);

    const registerId =
      node.metadata?.register_id !== undefined && node.metadata?.register_id !== null
        ? Number(node.metadata.register_id)
        : null;
    if (node.type === "plc" || node.metadata?.plc_id) {
      openInspector(node, { focusRegisterId: registerId });
    }
  }

  function initializeZoom() {
    if (!layoutViewport || !layoutCanvas) return;

    const handleWheel = (event) => {
      if (!event.ctrlKey) {
        return;
      }

      event.preventDefault();
      const direction = event.deltaY > 0 ? -1 : 1;
      const nextLevel = Math.min(
        zoomState.max,
        Math.max(zoomState.min, zoomState.level + direction * zoomState.step)
      );

      if (nextLevel === zoomState.level) {
        return;
      }

      const viewportRect = layoutViewport.getBoundingClientRect();
      const offsetX = event.clientX - viewportRect.left;
      const offsetY = event.clientY - viewportRect.top;

      const canvasX = (offsetX - panState.x) / zoomState.level;
      const canvasY = (offsetY - panState.y) / zoomState.level;

      zoomState.level = nextLevel;
      panState.x = offsetX - canvasX * zoomState.level;
      panState.y = offsetY - canvasY * zoomState.level;

      updateCanvasTransform();
      showStatusMessage(`Zoom ${Math.round(zoomState.level * 100)}%`);
    };

    layoutViewport.addEventListener("wheel", handleWheel, { passive: false });
  }

  function collectLayoutState() {
    const nodes = Array.from(layoutCanvas.querySelectorAll(".layout-node")).map((node) => {
      return {
        id: node.dataset.nodeId,
        type: node.dataset.type,
        position: {
          x: parseFloat(node.style.left) || 0,
          y: parseFloat(node.style.top) || 0,
        },
      };
    });

    return { nodes, connections: layoutData.connections || [] };
  }

  function toggleEditMode() {
    isEditMode = !isEditMode;
    if (toggleEditBtn) {
      toggleEditBtn.textContent = isEditMode ? "Modo visualização" : "Alternar modo de edição";
    }
    showStatusMessage(
      isEditMode
        ? "Modo edição ativado. Arraste os CLPs para reposicionar."
        : "Modo edição desativado"
    );
  }

  function saveLayout() {
    if (!isEditMode) {
      showStatusMessage("Ative o modo de edição para salvar alterações", "warning");
      return;
    }
    const payload = collectLayoutState();
    safeFetch(LAYOUT_ENDPOINT, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((data) => {
        hydrateLayoutMetadata(data.layout);
        layoutData = data.layout;
        renderLayout(layoutData);
        showStatusMessage("Layout atualizado com sucesso", "success");
      })
      .catch((error) => {
        console.error(error);
        showStatusMessage(`Erro ao salvar layout: ${error.message}`, "error");
      });
  }

  function openInspector(node, { focusRegisterId } = {}) {
    inspector?.classList.remove("hidden");
    inspector?.focus?.();
    inspectorTitle.textContent = "Carregando...";
    inspectorDetails.innerHTML = "";
    inspectorRegisters.innerHTML = "";

    const plcIdentifier =
      node.plc_id || node.metadata?.plc_id || node.id.replace("plc-", "");

    if (!plcIdentifier) {
      inspectorTitle.textContent = "CLP não identificado";
      inspectorDetails.innerHTML = "";
      inspectorRegisters.innerHTML = "";
      return;
    }

    safeFetch(PLC_DETAILS_ENDPOINT(plcIdentifier))
      .then((details) => {
        inspectorTitle.textContent = details.name;
        const entries = [
          ["IP", details.ip_address],
          ["VLAN", details.vlan_id ?? "-"],
          ["Localização", details.location_label || details.location || "Não informada"],
          ["Status", details.status_label],
          ["Última comunicação", details.last_seen || "n/d"],
          ["Protocolo", details.protocol],
        ];
        inspectorDetails.innerHTML = "";
        entries.forEach(([label, value]) => {
          const dt = document.createElement("dt");
          dt.textContent = label;
          const dd = document.createElement("dd");
          dd.textContent = value ?? "-";
          inspectorDetails.appendChild(dt);
          inspectorDetails.appendChild(dd);
        });

        inspectorRegisters.innerHTML = "";
        details.registers.forEach((register) => {
          const li = document.createElement("li");
          const info = document.createElement("span");
          info.textContent = register.name;

          const badge = document.createElement("span");
          badge.className = `status-pill ${register.status}`;
          badge.textContent = register.status_label;

          const registerIdentifier = Number(register.id);
          if (focusRegisterId !== null && registerIdentifier === focusRegisterId) {
            li.classList.add("is-selected");
            li.setAttribute("aria-current", "true");
          }

          li.appendChild(info);
          li.appendChild(badge);
          inspectorRegisters.appendChild(li);
        });
      })
      .catch((error) => {
        inspectorTitle.textContent = "Erro ao carregar";
        inspectorDetails.innerHTML = `<dt>Erro</dt><dd>${error.message}</dd>`;
      });
  }

  function closeInspector() {
    inspector?.classList.add("hidden");
  }

  function hydrateLayoutMetadata(layout) {
    const nodesById = new Map();
    layout.nodes.forEach((node) => nodesById.set(node.id, node));
    layout.nodes.forEach((node) => {
      if (node.metadata?.plc_id) {
        node.plc_id = node.metadata.plc_id;
        if (node.metadata.location_label || node.metadata.location) {
          node.location_label = node.metadata.location_label || node.metadata.location;
        }
      }
    });
  }

  function loadDashboard() {
    Promise.all([
      safeFetch(SUMMARY_ENDPOINT),
      safeFetch(LAYOUT_ENDPOINT),
      safeFetch(PLC_COLLECTION_ENDPOINT),
    ])
      .then(([summary, layout, plcCollection]) => {
        updateSummaryCards(summary.totals || {});
        buildLogChart(summary.log_volume || []);
        buildAlarmChart(summary.alarms_by_priority || {});
        renderIncidents(summary.offline_clps || []);
        hydrateLayoutMetadata(layout.layout);
        renderLayout(layout.layout);
        renderPlcCards(plcCollection.plcs || []);
        if (layout.vlan_summary) {
          showStatusMessage(`Última atualização ${layout.generated_at}`);
        }
      })
      .catch((error) => {
        console.error(error);
        showStatusMessage(`Erro ao carregar dashboard: ${error.message}`, "error");
      });
  }

  if (toggleEditBtn) {
    toggleEditBtn.addEventListener("click", toggleEditMode);
  }

  if (saveLayoutBtn) {
    saveLayoutBtn.addEventListener("click", saveLayout);
  }

  if (closeInspectorBtn) {
    closeInspectorBtn.addEventListener("click", closeInspector);
  }

  if (fullscreenToggleBtn) {
    fullscreenToggleBtn.addEventListener("click", toggleFullscreen);
  }

  if (resetViewBtn) {
    resetViewBtn.addEventListener("click", () => resetLayoutView());
  }

  if (layoutSection) {
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    updateFullscreenButton();
  }

  if (layoutCanvas && !editable) {
    layoutCanvas.classList.remove("editable");
  }

  if (exportAllBtn) {
    exportAllBtn.addEventListener("click", (event) => {
      event.preventDefault();
      exportAllRegisters();
    });
  }

  initializeZoom();
  initializePanning();
  resetLayoutView({ silent: true });
  loadDashboard();
})();
