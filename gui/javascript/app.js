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

const soundHome = document.getElementById("sound-home");
const soundEnter = document.getElementById("sound-enter");
const soundError = document.getElementById("sound-error");

const metrics = ["formality", "geodispersion", "longevity", "cohesion"];
let requestsRefreshInFlight = false;

const DEFAULT_MIN_COMMITS = "100";
const DEFAULT_DAYS = "90";
const DEFAULT_MIN_ACTIVE = "3";

const DEFAULT_COMMUNITY_THRESHOLDS = {
  geodispersion: "0.50",
  formality: "0.50",
  longevity: "0.50",
  cohesion: "0.50",
};

const thresholdControls = [
  { slider: thresholdGeodispersionInput, valueEl: thresholdGeodispersionValueEl },
  { slider: thresholdFormalityInput, valueEl: thresholdFormalityValueEl },
  { slider: thresholdLongevityInput, valueEl: thresholdLongevityValueEl },
  { slider: thresholdCohesionInput, valueEl: thresholdCohesionValueEl },
];

thresholdControls.forEach((control) => {
  control.slider.addEventListener("input", () => {
    syncThresholdSlider(control);
  });
});

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
  minCommitsInput.value = DEFAULT_MIN_COMMITS;
  daysInput.value = DEFAULT_DAYS;
  minActiveInput.value = DEFAULT_MIN_ACTIVE;
  thresholdGeodispersionInput.value = DEFAULT_COMMUNITY_THRESHOLDS.geodispersion;
  thresholdFormalityInput.value = DEFAULT_COMMUNITY_THRESHOLDS.formality;
  thresholdLongevityInput.value = DEFAULT_COMMUNITY_THRESHOLDS.longevity;
  thresholdCohesionInput.value = DEFAULT_COMMUNITY_THRESHOLDS.cohesion;
  syncThresholdSliders();
  hideResults();
  hideError();
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
  }
});

setInterval(() => {
  updateRemainingRequests();
}, 1000);

updateRemainingRequests();

function setLoading(loading) {
  submitBtn.disabled = loading;
  btnText.textContent = loading ? "Processing\u2026" : "Process";
  spinner.classList.toggle("hidden", !loading);
}

function showResults(data) {
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

  resultsCard.classList.remove("hidden");
}

function hideResults() {
  resultsCard.classList.add("hidden");
}

function showError(msg) {
  errorMessage.textContent = msg;
  errorCard.classList.remove("hidden");
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
    const res = await fetch(`${API_BASE}/remaining`);
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
