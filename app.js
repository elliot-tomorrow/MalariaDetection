/**
 * All state here lives only in page memory for the duration of this tab.
 * - The preview image uses a blob: URL generated client-side (never
 *   uploaded until the user clicks "analyze specimen").
 * - No localStorage / sessionStorage / cookies are used.
 * - The only network call this page makes is the single POST below.
 */

const viewport = document.getElementById("viewport");
const viewportEmpty = document.getElementById("viewportEmpty");
const fileInput = document.getElementById("fileInput");
const preview = document.getElementById("preview");
const scanLine = document.getElementById("scanLine");
const analyzeBtn = document.getElementById("analyzeBtn");
const clearBtn = document.getElementById("clearBtn");
const statusLine = document.getElementById("statusLine");
const readout = document.getElementById("readout");
const errorBanner = document.getElementById("errorBanner");

const resultInfected = document.getElementById("resultInfected");
const resultThickness = document.getElementById("resultThickness");
const resultConfidence = document.getElementById("resultConfidence");
const probBars = document.getElementById("probBars");

let currentFile = null;
let previewUrl = null;

const API_ENDPOINT = "/api/predict";

function resetError() {
  errorBanner.hidden = true;
  errorBanner.textContent = "";
}

function showError(message) {
  errorBanner.hidden = false;
  errorBanner.textContent = message;
}

function setFile(file) {
  resetError();
  readout.hidden = true;

  if (!file || !file.type.startsWith("image/")) {
    showError("Please choose an image file (PNG, JPG, WEBP, or BMP).");
    return;
  }

  currentFile = file;

  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  preview.src = previewUrl;

  viewport.classList.add("has-image");
  analyzeBtn.disabled = false;
  clearBtn.disabled = false;
  statusLine.textContent = "specimen loaded — ready to analyze";
}

function clearAll() {
  currentFile = null;
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }
  preview.src = "";
  viewport.classList.remove("has-image");
  fileInput.value = "";
  analyzeBtn.disabled = true;
  clearBtn.disabled = true;
  readout.hidden = true;
  resetError();
  statusLine.textContent = "awaiting specimen";
}

viewport.addEventListener("click", () => fileInput.click());
viewport.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
});

fileInput.addEventListener("change", (e) => {
  const file = e.target.files && e.target.files[0];
  if (file) setFile(file);
});

["dragenter", "dragover"].forEach((evt) =>
  viewport.addEventListener(evt, (e) => {
    e.preventDefault();
    viewport.classList.add("dragging");
  })
);

["dragleave", "drop"].forEach((evt) =>
  viewport.addEventListener(evt, (e) => {
    e.preventDefault();
    viewport.classList.remove("dragging");
  })
);

viewport.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (file) setFile(file);
});

clearBtn.addEventListener("click", clearAll);

analyzeBtn.addEventListener("click", async () => {
  if (!currentFile) return;

  resetError();
  readout.hidden = true;
  analyzeBtn.disabled = true;
  clearBtn.disabled = true;
  scanLine.classList.add("active");
  statusLine.textContent = "reading specimen…";

  const formData = new FormData();
  formData.append("image", currentFile);

  try {
    const response = await fetch(API_ENDPOINT, {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "The classifier could not process this image.");
    }

    renderResult(data);
    statusLine.textContent = "analysis complete";
  } catch (err) {
    showError(err.message || "Something went wrong reaching the classifier.");
    statusLine.textContent = "analysis failed";
  } finally {
    scanLine.classList.remove("active");
    analyzeBtn.disabled = false;
    clearBtn.disabled = false;
  }
});

function renderResult(data) {
  resultInfected.textContent = data.infected ? "infected" : "no parasites detected";
  resultInfected.className = "readout-value " + (data.infected ? "flag-infected" : "flag-clear");

  resultThickness.textContent = data.thickness;
  resultConfidence.textContent = (data.confidence * 100).toFixed(1) + "%";

  probBars.innerHTML = "";
  const entries = Object.entries(data.probabilities).sort((a, b) => b[1] - a[1]);

  for (const [label, value] of entries) {
    const row = document.createElement("div");
    row.className = "prob-bar-row";

    const name = document.createElement("span");
    name.textContent = label.toLowerCase().replace("_", " · ");

    const track = document.createElement("div");
    track.className = "prob-bar-track";
    const fill = document.createElement("div");
    fill.className = "prob-bar-fill";
    fill.style.width = (value * 100).toFixed(1) + "%";
    track.appendChild(fill);

    const pct = document.createElement("span");
    pct.textContent = (value * 100).toFixed(1) + "%";
    pct.style.textAlign = "right";

    row.appendChild(name);
    row.appendChild(track);
    row.appendChild(pct);
    probBars.appendChild(row);
  }

  readout.hidden = false;
}
