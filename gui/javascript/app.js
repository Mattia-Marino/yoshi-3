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

const soundHome = document.getElementById("sound-home");
const soundEnter = document.getElementById("sound-enter");
const soundError = document.getElementById("sound-error");

const metrics = ["formality", "geodispersion", "longevity"];

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
  hideResults();
  hideError();
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
    try {
      res = await fetch(`${API_BASE}/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner, repo }),
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
