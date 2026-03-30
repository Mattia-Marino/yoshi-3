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

const soundHome = document.getElementById("sound-home");
const soundEnter = document.getElementById("sound-enter");
const soundError = document.getElementById("sound-error");

const metrics = ["formality", "geodispersion", "longevity", "cohesion"];
let requestsRefreshInFlight = false;

const DEFAULT_MIN_COMMITS = "100";
const DEFAULT_DAYS = "90";
const DEFAULT_MIN_ACTIVE = "3";

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
  hideResults();
  hideError();
});

paramsToggleBtn.addEventListener("click", toggleParamsDrawer);
paramsOverlay.addEventListener("click", closeParamsDrawer);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeParamsDrawer();
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
