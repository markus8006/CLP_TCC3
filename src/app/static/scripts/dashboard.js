(function () {
  const SUMMARY_ENDPOINT = "/api/dashboard/summary";
  const LAYOUT_ENDPOINT = "/api/dashboard/layout";
  const PLC_DETAILS_ENDPOINT = (plcId) => `/api/dashboard/clps/${plcId}`;

  const context = window.DASHBOARD_CONTEXT || { isAdmin: false, csrfToken: "" };

  const summaryCards = document.querySelectorAll(".summary-card");
  const incidentList = document.getElementById("incident-list");
  const layoutCanvas = document.getElementById("factory-layout");
  const layoutStatus = document.getElementById("layout-status");
  const toggleEditBtn = document.getElementById("toggle-edit");
  const saveLayoutBtn = document.getElementById("save-layout");
  const inspector = document.getElementById("plc-inspector");
  const closeInspectorBtn = document.getElementById("close-inspector");
  const inspectorTitle = document.getElementById("inspector-title");
  const inspectorDetails = document.getElementById("inspector-details");
  const inspectorRegisters = document.getElementById("inspector-registers");

  let isEditMode = false;
  const editable = layoutCanvas?.dataset?.editable === "true";
  let layoutData = { nodes: [], connections: [] };
  let logChart;
  let alarmChart;

  function showStatusMessage(message, variant = "info") {
    if (!layoutStatus) return;
    layoutStatus.textContent = message;
    layoutStatus.className = `layout-status-message ${variant}`;
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

  function updateSummaryCards(summary) {
    summaryCards.forEach((card) => {
      const key = card.dataset.summary;
      if (!key) return;
      const metric = card.querySelector(".metric");
      if (metric) {
        const value = summary[key.replace(/-/g, "_")] ?? "--";
        metric.textContent = value;
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
      li.innerHTML = `<span>${incident.name} · ${incident.ip || ""}</span><span>${incident.reason}</span>`;
      incidentList.appendChild(li);
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

    element.addEventListener("click", () => {
      if (node.type === "plc") {
        openInspector(node);
      }
    });

    if (editable) {
      enableDrag(element);
    }

    return element;
  }

  function clearLayout() {
    if (!layoutCanvas) return;
    layoutCanvas.innerHTML = "";
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
      if (!isEditMode) return;
      pointerActive = true;
      element.setPointerCapture(event.pointerId);
      const rect = element.getBoundingClientRect();
      const canvasRect = layoutCanvas.getBoundingClientRect();
      offsetX = event.clientX - rect.left;
      offsetY = event.clientY - rect.top;
      element.dataset.dragging = "true";
      event.preventDefault();
    });

    element.addEventListener("pointermove", (event) => {
      if (!pointerActive || !isEditMode) return;
      const canvasRect = layoutCanvas.getBoundingClientRect();
      const x = event.clientX - canvasRect.left - offsetX;
      const y = event.clientY - canvasRect.top - offsetY;
      element.style.left = `${Math.max(0, x)}px`;
      element.style.top = `${Math.max(0, y)}px`;
    });

    element.addEventListener("pointerup", (event) => {
      if (!pointerActive) return;
      pointerActive = false;
      element.releasePointerCapture(event.pointerId);
      element.dataset.dragging = "false";
      updateConnectionOverlay();
    });

    element.addEventListener("pointercancel", () => {
      pointerActive = false;
      updateConnectionOverlay();
    });
  }

  function updateConnectionOverlay() {
    layoutCanvas.querySelectorAll(".layout-connection").forEach((line) => line.remove());
    drawConnections(layoutData.connections || []);
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
    showStatusMessage(isEditMode ? "Modo edição ativado" : "Modo edição desativado");
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

  function openInspector(node) {
    inspector?.classList.remove("hidden");
    inspector?.focus?.();
    inspectorTitle.textContent = "Carregando...";
    inspectorDetails.innerHTML = "";
    inspectorRegisters.innerHTML = "";

    safeFetch(PLC_DETAILS_ENDPOINT(node.plc_id || node.metadata?.plc_id || node.id.replace("plc-", "")))
      .then((details) => {
        inspectorTitle.textContent = details.name;
        const entries = [
          ["IP", details.ip_address],
          ["VLAN", details.vlan_id ?? "-"],
          ["Status", details.status_label],
          ["Última comunicação", details.last_seen || "n/d"],
          ["Protocol", details.protocol],
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
      }
    });
  }

  function loadDashboard() {
    Promise.all([safeFetch(SUMMARY_ENDPOINT), safeFetch(LAYOUT_ENDPOINT)])
      .then(([summary, layout]) => {
        updateSummaryCards(summary.totals || {});
        buildLogChart(summary.log_volume || []);
        buildAlarmChart(summary.alarms_by_priority || {});
        renderIncidents(summary.offline_clps || []);
        hydrateLayoutMetadata(layout.layout);
        renderLayout(layout.layout);
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

  if (layoutCanvas && !editable) {
    layoutCanvas.classList.remove("editable");
  }

  loadDashboard();
})();
