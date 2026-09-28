const API_BASE = "http://localhost:6001";

const form = document.getElementById("process-form");
const ownerInput = document.getElementById("owner");
const repoInput = document.getElementById("repo");
const submitBtn = document.getElementById("submit-btn");
const btnText = submitBtn.querySelector(".btn-text");
const spinner = submitBtn.querySelector(".spinner");
const resultsCard = document.getElementById("results-card");
const errorCard = document.getElementById("error-card");
const errorMessage = document.getElementById("error-message");
const remainingRequestsEl = document.getElementById("remaining-requests");
const paramsToggleBtn = document.getElementById("params-toggle-btn");
const paramsDrawer = document.getElementById("params-drawer");
const paramsOverlay = document.getElementById("params-overlay");
const minCommitsInput = document.getElementById("min-commits");
const daysInput = document.getElementById("days");
const minActiveInput = document.getElementById("min-active");
const thresholdGeodispersionInput = document.getElementById("threshold-geodispersion");
const thresholdFormalityInput = document.getElementById("threshold-formality");
const thresholdLongevityInput = document.getElementById("threshold-longevity");
const thresholdCohesionInput = document.getElementById("threshold-cohesion");
const thresholdGeodispersionValueEl = document.getElementById("threshold-geodispersion-value");
const thresholdFormalityValueEl = document.getElementById("threshold-formality-value");
const thresholdLongevityValueEl = document.getElementById("threshold-longevity-value");
const thresholdCohesionValueEl = document.getElementById("threshold-cohesion-value");
const categoryValueEl = document.getElementById("val-category");
const decisionStepsEl = document.getElementById("decision-steps");
const mapZoomTrigger = document.getElementById("map-zoom-trigger");
const mapModal = document.getElementById("map-modal");
const mapModalBackdrop = document.getElementById("map-modal-backdrop");
const mapModalClose = document.getElementById("map-modal-close");
const graphCard = document.getElementById("graph-card");
const cohesionGraphEl = document.getElementById("cohesion-graph");
const cohesionGraphInfoEl = document.getElementById("cohesion-graph-info");
let cohesionNetwork = null;
const geoGraphCard = document.getElementById("geo-graph-card");
const geoGraphEl = document.getElementById("geo-graph");
const geoGraphInfoEl = document.getElementById("geo-graph-info");
const geoGraphLegendEl = document.getElementById("geo-graph-legend");
let geoNetwork = null;
const coActivityGraphCard = document.getElementById("coactivity-graph-card");
const coActivityGraphEl = document.getElementById("coactivity-graph");
const coActivityGraphInfoEl = document.getElementById("coactivity-graph-info");
let coActivityNetwork = null;
const coActivityMinWeightInput = document.getElementById("coactivity-min-weight");
const coActivityMinWeightValueEl = document.getElementById("coactivity-min-weight-value");
let coActivityBaseNodes = [];
let coActivityBaseEdges = [];
let coActivityMaxWeight = 1;
let coActivityNodesDS = null;
let coActivityEdgesDS = null;

// La fisica serve solo per il layout iniziale: a stabilizzazione finita la
// si spegne, cosi il grafo resta fermo (niente piu "palla impazzita") ma i
// nodi restano trascinabili a mano. Vale per tutti e tre i grafi.
function freezeAfterStabilization(network) {
  if (!network || typeof network.on !== "function") {
    return;
  }
  const done = () => {
    if (typeof network.off === "function") {
      network.off("stabilizationIterationsDone", done);
    }
    network.setOptions({ physics: false });
  };
  network.on("stabilizationIterationsDone", done);
}

if (coActivityMinWeightInput) {
  coActivityMinWeightInput.addEventListener("input", applyCoActivityFilter);
}

const soundHome = document.getElementById("sound-home");
const soundEnter = document.getElementById("sound-enter");
const soundError = document.getElementById("sound-error");

const metrics = ["formality", "geodispersion", "longevity", "cohesion"];
let requestsRefreshInFlight = false;

const DEFAULT_MIN_COMMITS = "1500";
const DEFAULT_DAYS = "90";
const DEFAULT_MIN_ACTIVE = "3";

const DEFAULT_COMMUNITY_THRESHOLDS = {
  geodispersion: "0.25",
  formality: "0.50",
  longevity: "0.40",
  cohesion: "0.40",
};

const thresholdControls = [
  { slider: thresholdGeodispersionInput, valueEl: thresholdGeodispersionValueEl },
  { slider: thresholdFormalityInput, valueEl: thresholdFormalityValueEl },
  { slider: thresholdLongevityInput, valueEl: thresholdLongevityValueEl },
  { slider: thresholdCohesionInput, valueEl: thresholdCohesionValueEl },
];

function applyDefaultFormValues() {
  minCommitsInput.value = DEFAULT_MIN_COMMITS;
  daysInput.value = DEFAULT_DAYS;
  minActiveInput.value = DEFAULT_MIN_ACTIVE;
  thresholdGeodispersionInput.value = DEFAULT_COMMUNITY_THRESHOLDS.geodispersion;
  thresholdFormalityInput.value = DEFAULT_COMMUNITY_THRESHOLDS.formality;
  thresholdLongevityInput.value = DEFAULT_COMMUNITY_THRESHOLDS.longevity;
  thresholdCohesionInput.value = DEFAULT_COMMUNITY_THRESHOLDS.cohesion;
}

thresholdControls.forEach((control) => {
  control.slider.addEventListener("input", () => {
    syncThresholdSlider(control);
  });
});

applyDefaultFormValues();
syncThresholdSliders();

function playSound(audio) {
  audio.currentTime = 0;
  audio.play().catch(() => {});
}

// Home button: prevent navigation, play sound, then reset the page
document.getElementById("home-btn").addEventListener("click", (e) => {
  e.preventDefault();
  playSound(soundHome);
  ownerInput.value = "";
  repoInput.value = "";
  applyDefaultFormValues();
  syncThresholdSliders();
  hideResults();
  hideError();
  hideCohesionGraph();
  hideGeoGraph();
  hideCoActivityGraph();
});

paramsToggleBtn.addEventListener("click", toggleParamsDrawer);
paramsOverlay.addEventListener("click", closeParamsDrawer);
mapZoomTrigger.addEventListener("click", openMapModal);
mapModalBackdrop.addEventListener("click", closeMapModal);
mapModalClose.addEventListener("click", closeMapModal);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeParamsDrawer();
    closeMapModal();
  }
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const owner = ownerInput.value.trim();
  const repo = repoInput.value.trim();
  if (!owner || !repo) return;

  playSound(soundEnter);
  setLoading(true);
  hideResults();
  hideError();
  hideCohesionGraph();
  hideGeoGraph();
  hideCoActivityGraph();

  try {
    let res;
    const minCommits = parseNullableInt(minCommitsInput.value);
    const days = parseNullableInt(daysInput.value);
    const minActive = parseNullableInt(minActiveInput.value);

    try {
      res = await fetch(`${API_BASE}/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          owner,
          repo,
          min_commits: minCommits,
          days,
          min_active: minActive,
        }),
      });
    } catch (_) {
      throw new Error("Unable to reach the server. Is the backend running?");
    }

    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || `Request failed (${res.status})`);
    }

    playSound(soundHome);
    showResults(data);
  } catch (err) {
    playSound(soundError);
    showError(err.message);
  } finally {
    setLoading(false);
    updateRemainingRequests();
  }
});

setInterval(() => {
  updateRemainingRequests();
}, 15000);

updateRemainingRequests();

function setLoading(loading) {
  submitBtn.disabled = loading;
  btnText.textContent = loading ? "Processing\u2026" : "Process";
  spinner.classList.toggle("hidden", !loading);
}

function showResults(data) {
  if (data.simple_project && data.inactive) {
    showInactiveSPResults(data);
    return;
  }

  if (data.simple_project) {
    showSimpleProjectResults(data);
    return;
  }

  if (data.inactive) {
    showInactiveResults(data);
    return;
  }

  metrics.forEach((key) => {
    const value = data[key] ?? 0;
    const pct = Math.min(Math.max(value * 100, 0), 100);

    document.getElementById(`val-${key}`).textContent = value.toFixed(4);
    const bar = document.getElementById(`bar-${key}`);
    bar.style.width = "0";
    // trigger reflow so the transition animates from 0
    void bar.offsetWidth;
    bar.style.width = `${pct}%`;
  });

  const decisionResult = classifyCommunity(data);
  categoryValueEl.textContent = decisionResult.category;
  renderDecisionSteps(decisionResult.steps, decisionResult.category);
  const spDetailsEl = document.getElementById("sp-details");
  if (spDetailsEl) {
    spDetailsEl.textContent = formatSimpleProjectDetails(data);
  }

  resultsCard.classList.remove("hidden");
  renderCohesionGraph(data.cohesion_graph);
  renderGeoGraph(data.geo_graph);
  renderCoActivityGraph(data.coactivity_graph);
}

function showSimpleProjectResults(data) {
  metrics.forEach((key) => {
    document.getElementById(`val-${key}`).textContent = "N/A";
    const bar = document.getElementById(`bar-${key}`);
    bar.style.width = "0";
  });

  const category = data.category || "Simple Project (SP)";
  categoryValueEl.textContent = category;
  const spDetailsEl = document.getElementById("sp-details");
  if (spDetailsEl) {
    spDetailsEl.textContent = formatSimpleProjectDetails(data);
  }
  renderStructureLowDecisionPath(category);
  resultsCard.classList.remove("hidden");
  hideCohesionGraph();
  hideGeoGraph();
  hideCoActivityGraph();
}

function showInactiveResults(data) {
  metrics.forEach((key) => {
    document.getElementById(`val-${key}`).textContent = "N/A";
    const bar = document.getElementById(`bar-${key}`);
    bar.style.width = "0";
  });

  const category = data.category || "Inactive";
  categoryValueEl.textContent = category;
  const spDetailsEl = document.getElementById("sp-details");
  if (spDetailsEl) {
    const reason = data.reason ? capitalizeFirst(data.reason) : "";
    const counts = formatSimpleProjectDetails(data);
    spDetailsEl.textContent = reason && counts && counts !== reason ? `${reason}. ${counts}` : reason || counts;
  }
  renderInactiveDecisionPath(data.reason, category);
  resultsCard.classList.remove("hidden");
  hideCohesionGraph();
  hideGeoGraph();
  hideCoActivityGraph();
}

function showInactiveSPResults(data) {
  metrics.forEach((key) => {
    document.getElementById(`val-${key}`).textContent = "N/A";
    const bar = document.getElementById(`bar-${key}`);
    bar.style.width = "0";
  });

  const category = data.category || "Inactive Simple Project (ISP)";
  categoryValueEl.textContent = category;
  const spDetailsEl = document.getElementById("sp-details");
  if (spDetailsEl) {
    const reason = data.reason ? capitalizeFirst(data.reason) : "";
    const counts = formatSimpleProjectDetails(data);
    spDetailsEl.textContent = reason && counts && counts !== reason ? `${reason}. ${counts}` : reason || counts;
  }
  renderInactiveSPDecisionPath(data, category);
  resultsCard.classList.remove("hidden");
  hideCohesionGraph();
  hideGeoGraph();
  hideCoActivityGraph();
}

function capitalizeFirst(text) {
  if (!text) {
    return "";
  }
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatSimpleProjectDetails(data) {
  const commitsFound = Number(data.commits_found);
  const commitsRequired = Number(data.commits_required);
  const activeFound = Number(data.active_found);
  const activeRequired = Number(data.active_required);
  const days = Number(data.days);

  const hasCounts =
    Number.isFinite(commitsFound) &&
    Number.isFinite(commitsRequired) &&
    Number.isFinite(activeFound) &&
    Number.isFinite(activeRequired) &&
    Number.isFinite(days);

  if (hasCounts) {
    return `The repo has ${commitsFound}/${commitsRequired} total commits and ${activeFound}/${activeRequired} active members in last ${days} days.`;
  }

  return data.reason || "";
}

function hideResults() {
  resultsCard.classList.add("hidden");
}

function hideCohesionGraph() {
  if (cohesionNetwork) {
    cohesionNetwork.destroy();
    cohesionNetwork = null;
  }
  if (cohesionGraphEl) {
    cohesionGraphEl.innerHTML = "";
  }
  if (cohesionGraphInfoEl) {
    cohesionGraphInfoEl.textContent = "";
  }
  if (graphCard) {
    graphCard.classList.add("hidden");
  }
}

function renderCohesionGraph(graph) {
  if (!graphCard || !cohesionGraphEl || !cohesionGraphInfoEl) {
    return;
  }
  // NB: pulisce solo il proprio grafo; gli altri li gestiscono
  // hideResults/home/SP e il proprio render. Non cancellare gli altri qui.
  hideCohesionGraph();

  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph?.edges) ? graph.edges : [];

  if (typeof vis === "undefined" || !vis.Network) {
    cohesionGraphInfoEl.textContent = "Graph library unavailable (offline CDN). Metrics above are unaffected.";
    cohesionGraphEl.innerHTML = '<div class="graph-empty">vis-network failed to load.</div>';
    graphCard.classList.remove("hidden");
    return;
  }

  if (nodes.length === 0) {
    cohesionGraphInfoEl.textContent = "No contributor nodes available for this repository.";
    cohesionGraphEl.innerHTML = '<div class="graph-empty">No graph data.</div>';
    graphCard.classList.remove("hidden");
    return;
  }

  const visNodes = nodes.map((n) => ({
    id: n.id,
    label: n.label || n.id,
    value: 4 + Math.min(n.followers || 0, 20),
    title: `${n.id}<br>followers: ${n.followers ?? 0} · following: ${n.following ?? 0}`,
  }));
  const visEdges = edges
    .filter((e) => e && e.from && e.to)
    .map((e) => ({ from: e.from, to: e.to, arrows: "to" }));

  cohesionGraphInfoEl.textContent = `${nodes.length} contributors · ${visEdges.length} follows edges (same nodes used for cohesion).`;

  const data = {
    nodes: new vis.DataSet(visNodes),
    edges: new vis.DataSet(visEdges),
  };
  const options = {
    nodes: { shape: "dot", scaling: { min: 8, max: 30 }, font: { size: 12 } },
    edges: { arrows: { to: { enabled: true, scaleFactor: 0.8 } }, smooth: { type: "continuous" } },
    physics: { solver: "barnesHut", stabilization: { iterations: 200 } },
    interaction: { hover: true, tooltipDelay: 100, navigationButtons: true },
  };
  cohesionNetwork = new vis.Network(cohesionGraphEl, data, options);
  freezeAfterStabilization(cohesionNetwork);
  graphCard.classList.remove("hidden");
}

const GEO_COUNTRY_PALETTE = [
  "#43a047", "#1e88e5", "#ef6c00", "#8e24aa", "#d81b60",
  "#00897b", "#fdd835", "#5c6bc0", "#fb8c00", "#26a69a",
];

function geoCountryColor(country, indexByCountry) {
  const idx = indexByCountry.get(country) % GEO_COUNTRY_PALETTE.length;
  return GEO_COUNTRY_PALETTE[idx];
}

function hideGeoGraph() {
  if (geoNetwork) {
    geoNetwork.destroy();
    geoNetwork = null;
  }
  if (geoGraphEl) {
    geoGraphEl.innerHTML = "";
  }
  if (geoGraphInfoEl) {
    geoGraphInfoEl.textContent = "";
  }
  if (geoGraphLegendEl) {
    geoGraphLegendEl.innerHTML = "";
  }
  if (geoGraphCard) {
    geoGraphCard.classList.add("hidden");
  }
}

function renderGeoGraph(graph) {
  if (!geoGraphCard || !geoGraphEl || !geoGraphInfoEl) {
    return;
  }
  hideGeoGraph();

  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph?.edges) ? graph.edges : [];

  if (typeof vis === "undefined" || !vis.Network) {
    geoGraphInfoEl.textContent = "Graph library unavailable (offline CDN). Metrics above are unaffected.";
    geoGraphEl.innerHTML = '<div class="graph-empty">vis-network failed to load.</div>';
    geoGraphCard.classList.remove("hidden");
    return;
  }

  if (nodes.length === 0) {
    geoGraphInfoEl.textContent = "No matched locations for this repository.";
    geoGraphEl.innerHTML = '<div class="graph-empty">No geographic graph data.</div>';
    geoGraphCard.classList.remove("hidden");
    return;
  }

  const indexByCountry = new Map();
  nodes.forEach((n) => {
    const country = (n.country || "unknown").toLowerCase();
    if (!indexByCountry.has(country)) {
      indexByCountry.set(country, indexByCountry.size);
    }
  });

  const visNodes = nodes.map((n) => {
    const country = (n.country || "unknown").toLowerCase();
    // "unknown" = senza location o non matchabile: grigio e isolato, ma
    // visibile cosi il grafo non si svuota e si vede chi resta fuori.
    const isUnknown = country === "unknown";
    return {
      id: n.login,
      label: n.login,
      color: isUnknown ? "#b0bec5" : geoCountryColor(country, indexByCountry),
      title: isUnknown
        ? `${n.login}<br>location unknown`
        : `${n.login}<br>${country}<br>lat: ${Number(n.latitude).toFixed(2)}, lon: ${Number(n.longitude).toFixed(2)}`,
    };
  });
  const visEdges = edges
    .filter((e) => e && e.from && e.to)
    .map((e) => {
      const nearby = e.type === "nearby";
      return {
        from: e.from,
        to: e.to,
        color: nearby ? "#ef6c00" : "#43a047",
        dashes: nearby,
        title: `${e.type} · ${Number(e.distance_km).toFixed(0)} km`,
      };
    });

  const sameCount = edges.filter((e) => e.type === "same_country").length;
  const nearbyCount = edges.filter((e) => e.type === "nearby").length;
  const unknownCount = nodes.filter((n) => (n.country || "unknown").toLowerCase() === "unknown").length;
  geoGraphInfoEl.textContent = `${nodes.length} contributors · ${indexByCountry.size} countries · ${sameCount} same-country + ${nearbyCount} nearby edges · ${unknownCount} without location (grey).`;

  geoGraphLegendEl.innerHTML = "";
  indexByCountry.forEach((idx, country) => {
    const item = document.createElement("span");
    item.className = "graph-legend-item";
    const dot = document.createElement("span");
    dot.className = "graph-legend-dot";
    dot.style.background = country === "unknown" ? "#b0bec5" : GEO_COUNTRY_PALETTE[idx % GEO_COUNTRY_PALETTE.length];
    const label = document.createElement("span");
    label.textContent = country;
    item.append(dot, label);
    geoGraphLegendEl.appendChild(item);
  });
  const edgeLegend = document.createElement("span");
  edgeLegend.className = "graph-legend-item";
  edgeLegend.innerHTML = '<span class="graph-legend-line"></span><span>same country</span>';
  const nearbyLegend = document.createElement("span");
  nearbyLegend.className = "graph-legend-item";
  nearbyLegend.innerHTML = '<span class="graph-legend-line nearby"></span><span>nearby &lt;500 km</span>';
  geoGraphLegendEl.append(edgeLegend, nearbyLegend);

  const data = {
    nodes: new vis.DataSet(visNodes),
    edges: new vis.DataSet(visEdges),
  };
  const options = {
    nodes: { shape: "dot", size: 14, font: { size: 12 } },
    edges: { smooth: { type: "continuous" } },
    physics: { solver: "barnesHut", stabilization: { iterations: 200 } },
    interaction: { hover: true, tooltipDelay: 100, navigationButtons: true },
  };
  geoNetwork = new vis.Network(geoGraphEl, data, options);
  freezeAfterStabilization(geoNetwork);
  geoGraphCard.classList.remove("hidden");
}

// Teoria (promemoria): questo grafo mostra la collaborazione PRATICATA nel
// tempo, non relazioni dichiarate. Arco A-B = A e B attivi nelle stesse
// settimane (peso = quante). Nucleo denso = team reale; nodi isolati =
// comparse one-shot (problema di retention); coesione alta + co-attivita
// frammentata = folla di solisti, non un team.
function hideCoActivityGraph() {
  if (coActivityNetwork) {
    coActivityNetwork.destroy();
    coActivityNetwork = null;
  }
  coActivityBaseNodes = [];
  coActivityBaseEdges = [];
  coActivityMaxWeight = 1;
  coActivityNodesDS = null;
  coActivityEdgesDS = null;
  if (coActivityMinWeightInput) {
    coActivityMinWeightInput.value = "0";
  }
  if (coActivityMinWeightValueEl) {
    coActivityMinWeightValueEl.textContent = "1";
  }
  if (coActivityGraphEl) {
    coActivityGraphEl.innerHTML = "";
  }
  if (coActivityGraphInfoEl) {
    coActivityGraphInfoEl.textContent = "";
  }
  if (coActivityGraphCard) {
    coActivityGraphCard.classList.add("hidden");
  }
}

// Slider "min shared weeks": scala LOGARITMICA 0..100 -> 1..maxWeight.
// I pesi vanno da 1 a centinaia di settimane: con scala lineare i primi
// millimetri di slider brucerebbero decine di valori (troppo sensibile),
// mentre in logaritmica meta corsa ~ radice del max. Nasconde gli archi
// deboli senza rifare richieste: alzalo se il grafo e troppo denso.
function coActivitySliderToWeight() {
  const pos = Math.min(100, Math.max(0, Number(coActivityMinWeightInput.value) || 0));
  if (pos <= 0) {
    return 1;
  }
  const w = Math.exp((Math.log(coActivityMaxWeight) * pos) / 100);
  return Math.min(coActivityMaxWeight, Math.max(1, Math.round(w)));
}

function applyCoActivityFilter() {
  if (!coActivityNodesDS || !coActivityEdgesDS || !coActivityMinWeightInput) {
    return;
  }
  const minW = coActivitySliderToWeight();
  coActivityMinWeightValueEl.textContent = String(minW);

  const visible = coActivityBaseEdges.filter((e) => e.weight >= minW);
  const linked = new Set();
  visible.forEach((e) => {
    linked.add(e.from);
    linked.add(e.to);
  });

  coActivityNodesDS.clear();
  coActivityNodesDS.add(
    coActivityBaseNodes.map((n) => ({
      id: n.id,
      label: n.label,
      // Dimensione nodo = settimane attive (presenza nel tempo, non volume).
      value: 4 + Math.min(n.activeWeeks || 0, 30),
      color: linked.has(n.id) ? "#43a047" : "#b0bec5",
      title: `${n.id}<br>active weeks: ${n.activeWeeks ?? 0} · commits: ${n.totalCommits ?? 0}`,
    }))
  );
  coActivityEdgesDS.clear();
  coActivityEdgesDS.add(
    visible.map((e) => ({
      from: e.from,
      to: e.to,
      // Spessore arco = settimane in comune (collaborazione praticata).
      width: 1 + Math.min(e.weight || 1, 12) / 2,
      title: `${e.from} ↔ ${e.to}<br>${e.weight} shared weeks (${e.type})`,
    }))
  );

  coActivityGraphInfoEl.textContent =
    `${coActivityBaseNodes.length} contributors (top by commits) · ` +
    `${visible.length}/${coActivityBaseEdges.length} edges ≥ ${minW} shared weeks · ` +
    `${coActivityBaseNodes.length - linked.size} isolated (grey).`;
}

function renderCoActivityGraph(graph) {
  if (!coActivityGraphCard || !coActivityGraphEl || !coActivityGraphInfoEl) {
    return;
  }
  // NB: pulisce solo il proprio grafo (vedi nota in renderCohesionGraph).
  hideCoActivityGraph();

  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph?.edges) ? graph.edges : [];

  if (typeof vis === "undefined" || !vis.Network) {
    coActivityGraphInfoEl.textContent = "Graph library unavailable (offline CDN). Metrics above are unaffected.";
    coActivityGraphEl.innerHTML = '<div class="graph-empty">vis-network failed to load.</div>';
    coActivityGraphCard.classList.remove("hidden");
    return;
  }

  if (nodes.length === 0) {
    coActivityGraphInfoEl.textContent = "No activity data (GitHub may still be computing contributor stats).";
    coActivityGraphEl.innerHTML = '<div class="graph-empty">No co-activity data.</div>';
    coActivityGraphCard.classList.remove("hidden");
    return;
  }

  coActivityBaseNodes = nodes.map((n) => ({
    id: n.id,
    label: n.label || n.id,
    activeWeeks: n.active_weeks || 0,
    totalCommits: n.total_commits || 0,
  }));
  coActivityBaseEdges = edges
    .filter((e) => e && e.from && e.to)
    .map((e) => ({ from: e.from, to: e.to, type: e.type || "co_active", weight: e.weight || 1 }));

  coActivityMaxWeight = Math.max(1, ...coActivityBaseEdges.map((e) => e.weight));
  coActivityMinWeightInput.value = "0";

  coActivityNodesDS = new vis.DataSet([]);
  coActivityEdgesDS = new vis.DataSet([]);
  const data = { nodes: coActivityNodesDS, edges: coActivityEdgesDS };
  const options = {
    nodes: { shape: "dot", scaling: { min: 8, max: 30 }, font: { size: 12 } },
    edges: { color: "#43a047", smooth: { type: "continuous" } },
    physics: {
      solver: "barnesHut",
      barnesHut: { springLength: 160, damping: 0.15 },
      stabilization: { iterations: 500 },
    },
    interaction: { hover: true, tooltipDelay: 100, navigationButtons: true },
  };
  coActivityNetwork = new vis.Network(coActivityGraphEl, data, options);
  freezeAfterStabilization(coActivityNetwork);
  applyCoActivityFilter();
  coActivityGraphCard.classList.remove("hidden");
}

function showError(msg) {
  errorMessage.textContent = msg;
  errorCard.classList.remove("hidden");
}

function renderStructureLowDecisionPath(category) {
  decisionStepsEl.innerHTML = "";

  const startItem = document.createElement("li");
  startItem.className = "decision-step";
  startItem.textContent = "Start node from map: Structure";
  decisionStepsEl.appendChild(startItem);

  const structureItem = document.createElement("li");
  structureItem.className = "decision-step";
  structureItem.textContent = "Structure node: LOW -> Simple Project (SP)";
  decisionStepsEl.appendChild(structureItem);

  const stopItem = document.createElement("li");
  stopItem.className = "decision-step decision-final";
  stopItem.textContent = `Final category from map path: ${category}`;
  decisionStepsEl.appendChild(stopItem);
}

function renderInactiveDecisionPath(reason, category) {
  decisionStepsEl.innerHTML = "";

  const startItem = document.createElement("li");
  startItem.className = "decision-step";
  startItem.textContent = "Eligibility check: commit threshold passed";
  decisionStepsEl.appendChild(startItem);

  const activityItem = document.createElement("li");
  activityItem.className = "decision-step";
  activityItem.textContent = `Activity check: ${reason || "not active"} -> Inactive`;
  decisionStepsEl.appendChild(activityItem);

  const stopItem = document.createElement("li");
  stopItem.className = "decision-step decision-final";
  stopItem.textContent = `Final category from map path: ${category}`;
  decisionStepsEl.appendChild(stopItem);
}

function renderInactiveSPDecisionPath(data, category) {
  decisionStepsEl.innerHTML = "";

  const startItem = document.createElement("li");
  startItem.className = "decision-step";
  startItem.textContent = "Eligibility check: commit threshold not passed";
  decisionStepsEl.appendChild(startItem);

  const structureItem = document.createElement("li");
  structureItem.className = "decision-step";
  structureItem.textContent = "Structure node: LOW -> Simple Project (SP)";
  decisionStepsEl.appendChild(structureItem);

  const activityItem = document.createElement("li");
  activityItem.className = "decision-step";
  const activeFound = Number(data.active_found);
  const activeRequired = Number(data.active_required);
  const days = Number(data.days);
  const activityText =
    Number.isFinite(activeFound) && Number.isFinite(activeRequired) && Number.isFinite(days)
      ? `${activeFound}/${activeRequired} active members in last ${days} days`
      : data.reason || "not active";
  activityItem.textContent = `Activity check: ${activityText} -> Inactive`;
  decisionStepsEl.appendChild(activityItem);

  const stopItem = document.createElement("li");
  stopItem.className = "decision-step decision-final";
  stopItem.textContent = `Final category from map path: ${category}`;
  decisionStepsEl.appendChild(stopItem);
}

function hideError() {
  errorCard.classList.add("hidden");
}

function toggleParamsDrawer() {
  if (paramsDrawer.classList.contains("open")) {
    closeParamsDrawer();
  } else {
    openParamsDrawer();
  }
}

function openParamsDrawer() {
  paramsDrawer.classList.add("open");
  paramsOverlay.classList.remove("hidden");
  paramsToggleBtn.setAttribute("aria-expanded", "true");
  paramsDrawer.setAttribute("aria-hidden", "false");
}

function closeParamsDrawer() {
  paramsDrawer.classList.remove("open");
  paramsOverlay.classList.add("hidden");
  paramsToggleBtn.setAttribute("aria-expanded", "false");
  paramsDrawer.setAttribute("aria-hidden", "true");
}

function openMapModal() {
  mapModal.classList.remove("hidden");
  mapModal.setAttribute("aria-hidden", "false");
}

function closeMapModal() {
  mapModal.classList.add("hidden");
  mapModal.setAttribute("aria-hidden", "true");
}

function parseNullableInt(rawValue) {
  const value = rawValue.trim();
  if (value === "") {
    return null;
  }

  const num = Number.parseInt(value, 10);
  if (!Number.isFinite(num)) {
    return null;
  }

  return num;
}

function classifyCommunity(data) {
  const geodispersion = Number(data.geodispersion ?? 0);
  const formality = Number(data.formality ?? 0);
  const longevity = Number(data.longevity ?? 0);
  const cohesion = Number(data.cohesion ?? 0);
  const thresholds = getCommunityThresholds();
  const steps = [];

  const geodispersionLow = geodispersion < thresholds.geodispersion;
  steps.push(createDecisionStep("Geodispersion", geodispersion, thresholds.geodispersion, geodispersionLow, "Community of Practice (CoP)", "Network of Practice (NoP)"));

  if (geodispersionLow) {
    const formalityLow = formality < thresholds.formality;
    steps.push(createDecisionStep("Formality", formality, thresholds.formality, formalityLow, "Informal Community (IC)", "Formal Community (FC)"));

    if (formalityLow) {
      return {
        category: "Informal Community (IC)",
        steps,
      };
    }

    const longevityLow = longevity < thresholds.longevity;
    steps.push(createDecisionStep("Longevity", longevity, thresholds.longevity, longevityLow, "Project Team (PT)", "Go to Cohesion node"));

    if (longevityLow) {
      return {
        category: "Project Team (PT)",
        steps,
      };
    }

    const cohesionLow = cohesion < thresholds.cohesion;
    steps.push(createDecisionStep("Cohesion", cohesion, thresholds.cohesion, cohesionLow, "Strategic Community (SC)", "Workgroup (WG)"));

    if (cohesionLow) {
      return {
        category: "Strategic Community (SC)",
        steps,
      };
    }

    return {
      category: "Workgroup (WG)",
      steps,
    };
  }

  const formalityLow = formality < thresholds.formality;
  steps.push(createDecisionStep("Formality", formality, thresholds.formality, formalityLow, "Informal Network (IN)", "Formal Network (FN)"));

  if (formalityLow) {
    return {
      category: "Informal Network (IN)",
      steps,
    };
  }

  return {
    category: "Formal Network (FN)",
    steps,
  };
}

function getCommunityThresholds() {
  return {
    geodispersion: parseThresholdValue(thresholdGeodispersionInput.value, DEFAULT_COMMUNITY_THRESHOLDS.geodispersion),
    formality: parseThresholdValue(thresholdFormalityInput.value, DEFAULT_COMMUNITY_THRESHOLDS.formality),
    longevity: parseThresholdValue(thresholdLongevityInput.value, DEFAULT_COMMUNITY_THRESHOLDS.longevity),
    cohesion: parseThresholdValue(thresholdCohesionInput.value, DEFAULT_COMMUNITY_THRESHOLDS.cohesion),
  };
}

function parseThresholdValue(rawValue, fallbackValue) {
  return normalizeThreshold(rawValue, fallbackValue);
}

function syncThresholdSliders() {
  thresholdControls.forEach((control) => {
    syncThresholdSlider(control);
  });
}

function syncThresholdSlider(control) {
  const normalized = normalizeThreshold(control.slider.value, "0.50");
  const formatted = normalized.toFixed(2);
  control.slider.value = formatted;
  control.valueEl.textContent = formatted;
}

function normalizeThreshold(rawValue, fallbackValue) {
  const normalizedRawValue = String(rawValue).trim().replace(",", ".");
  const num = Number.parseFloat(normalizedRawValue);
  if (!Number.isFinite(num)) {
    return Number.parseFloat(fallbackValue);
  }

  if (num < 0) {
    return 0;
  }

  if (num > 1) {
    return 1;
  }

  return num;
}

function createDecisionStep(metricLabel, metricValue, threshold, conditionResult, lowBranch, highBranch) {
  return {
    metricLabel,
    metricValue,
    threshold,
    conditionResult,
    branch: conditionResult ? lowBranch : highBranch,
    levelLabel: conditionResult ? "LOW" : "HIGH",
    levelClass: conditionResult ? "low" : "high",
  };
}

function renderDecisionSteps(steps, category) {
  decisionStepsEl.innerHTML = "";

  const startItem = document.createElement("li");
  startItem.className = "decision-step";
  startItem.textContent = "Start node from map: Geodispersion";
  decisionStepsEl.appendChild(startItem);

  steps.forEach((step) => {
    const listItem = document.createElement("li");
    listItem.className = "decision-step";

    const mainText = document.createElement("span");
    mainText.textContent = `${step.metricLabel} node: ${step.metricValue.toFixed(4)} < ${step.threshold.toFixed(4)} => `;

    const badge = document.createElement("span");
    badge.className = `decision-badge ${step.levelClass}`;
    badge.textContent = step.levelLabel;

    const branchText = document.createElement("span");
    branchText.className = "decision-branch";
    branchText.textContent = ` -> ${step.branch}`;

    listItem.append(mainText, badge, branchText);
    decisionStepsEl.appendChild(listItem);
  });

  const finalItem = document.createElement("li");
  finalItem.className = "decision-step decision-final";
  finalItem.textContent = `Final category from map path: ${category}`;
  decisionStepsEl.appendChild(finalItem);
}

async function updateRemainingRequests() {
  if (requestsRefreshInFlight) {
    return;
  }

  requestsRefreshInFlight = true;

  try {
    const res = await fetch(`${API_BASE}/remaining`, { cache: "no-store" });
    if (!res.ok) {
      throw new Error(`Request failed (${res.status})`);
    }

    const data = await res.json();
    const remaining = Number(data.remaining);

    if (!Number.isFinite(remaining)) {
      throw new Error("Invalid remaining requests value");
    }

    remainingRequestsEl.textContent = Math.max(0, Math.floor(remaining)).toString();
  } catch (_) {
    // Keep the widget non-intrusive: show placeholder on errors.
    remainingRequestsEl.textContent = "--";
  } finally {
    requestsRefreshInFlight = false;
  }
}
