"""
Malaria Blood Smear Classifier — backend API.

PRIVACY / DATA-HANDLING DESIGN
------------------------------
This service is intentionally built to avoid collecting any personal or
patient data:

  - Uploaded images are read into memory (io.BytesIO), preprocessed, and
    passed straight to the model. They are never written to disk and never
    persist past the single request.
  - No filenames, image bytes, or prediction results are logged. The only
    thing written to server logs is Flask/Werkzeug's default access line
    (method, path, status code) — no request body.
  - No cookies, sessions, accounts, or client identifiers are used or
    stored. Each request is stateless.
  - No third-party analytics, trackers, or telemetry are included.
  - CORS is restricted to same-origin by default; adjust ALLOWED_ORIGIN
    below only if you deploy the frontend on a different host.

IMPORTANT: this code makes it easy to run the service without retaining
data, but it is not itself a HIPAA "compliance certificate." If you deploy
this where real patient images will be uploaded, you (the operator) are
still responsible for the surrounding requirements HIPAA imposes on a
covered entity/business associate — e.g. TLS in transit, a signed Business
Associate Agreement with your hosting provider, access controls, audit
logging of *access* (not image content), and a risk assessment. This app
only handles the "don't collect/retain the data in the first place" part.

MEDICAL DISCLAIMER: this is a research/educational classifier, not a
diagnostic device. It has not been reviewed or cleared by any regulatory
body (e.g. FDA) for clinical use. Do not use it to make real diagnostic or
treatment decisions — a qualified microscopist/clinician must confirm any
result.
"""

import io
import os
import urllib.request

import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from PIL import Image

# Keras 3 standalone package (works whether it pulled in tensorflow or
# another backend under the hood).
import keras

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "MalariaDetection.keras")
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")

# If the model file isn't already sitting on disk (e.g. it was kept out of
# git via .gitignore), download it once from this URL on startup instead.
# Set MODEL_URL as an environment variable on your host (e.g. Render's
# dashboard -> your service -> Environment) rather than hardcoding it here.
MODEL_URL = os.environ.get("MODEL_URL")

IMG_SIZE = (180, 180)  # matches the model's InputLayer batch_shape
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB safety cap
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}

# Class order the model was trained on (confirmed by the model owner).
# Index -> label, as produced by Keras' image_dataset_from_directory, which
# sorts subfolder names alphabetically.
CLASS_LABELS = [
    "Thick_Infected",
    "Thick_Uninfected",
    "Thin_Infected",
    "Thin_Uninfected",
]

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def ensure_model_present():
    """Download the model file if it isn't already on disk."""
    if os.path.exists(MODEL_PATH):
        return

    if not MODEL_URL:
        raise RuntimeError(
            f"Model file not found at {MODEL_PATH}, and no MODEL_URL "
            "environment variable is set to download it from. Either "
            "place the .keras file there directly, or set MODEL_URL."
        )

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    print(f"Model not found locally — downloading from {MODEL_URL} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Download complete.")


# Load the model once at startup and keep it in memory for the process
# lifetime — this is the only thing "persisted"; it never changes per
# request and contains no user data.
ensure_model_present()
print(f"Loading model from {MODEL_PATH} ...")
model = keras.saving.load_model(MODEL_PATH)
print("Model loaded.")


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)
    exp = np.exp(shifted)
    return exp / np.sum(exp)


def preprocess_image(file_bytes: bytes) -> np.ndarray:
    """Decode -> RGB -> resize -> float32 array shaped (1, H, W, 3).

    Values are left in the 0-255 range on purpose: the model has its own
    Rescaling(1/255) layer built in, matching how it was trained.
    """
    with Image.open(io.BytesIO(file_bytes)) as img:
        img = img.convert("RGB")
        img = img.resize(IMG_SIZE, resample=Image.BILINEAR)
        arr = np.asarray(img, dtype=np.float32)
    return np.expand_dims(arr, axis=0)


def interpret(label: str, confidence: float):
    infected = "Infected" in label and "Uninfected" not in label
    thickness = "thick" if label.startswith("Thick") else "thin"
    return infected, thickness


@app.after_request
def add_privacy_headers(response):
    # Discourage any intermediate caching of request/response content and
    # signal there's nothing to track here.
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/predict", methods=["POST"])
def predict():
    if "image" not in request.files:
        return jsonify({"error": "No file uploaded under field name 'image'."}), 400

    file = request.files["image"]

    if file.filename == "":
        return jsonify({"error": "Empty filename."}), 400

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        return jsonify({
            "error": f"Unsupported content type '{file.content_type}'. "
                     f"Allowed: {sorted(ALLOWED_CONTENT_TYPES)}"
        }), 400

    file_bytes = file.read()  # kept only in local variables, in memory

    try:
        batch = preprocess_image(file_bytes)
    except Exception:
        return jsonify({"error": "Could not read the uploaded file as an image."}), 400
    finally:
        # Drop the reference to raw bytes as soon as we're done with them.
        del file_bytes

    logits = model.predict(batch, verbose=0)[0]
    probs = softmax(logits)

    top_idx = int(np.argmax(probs))
    label = CLASS_LABELS[top_idx]
    confidence = float(probs[top_idx])
    infected, thickness = interpret(label, confidence)

    result = {
        "infected": infected,
        "thickness": thickness,
        "confidence": round(confidence, 4),
        "probabilities": {
            CLASS_LABELS[i]: round(float(probs[i]), 4) for i in range(len(CLASS_LABELS))
        },
        "disclaimer": (
            "Research/educational tool only. Not a medical device and not "
            "reviewed or cleared for clinical diagnosis. A qualified "
            "professional must confirm any result."
        ),
    }

    # Nothing about this request (image, filename, or result) is logged or
    # stored anywhere beyond this point — `batch`, `logits`, etc. go out of
    # scope and are garbage collected once the response is returned.
    return jsonify(result)


# ---------------------------------------------------------------------------
# Serve the static frontend (optional convenience for local/dev use).
# In production you'd typically serve the frontend separately, e.g. via a
# static host or CDN, and point it at this API's origin.
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    # Debug is off on purpose: Flask's debugger can expose request data and
    # allows remote code execution if ever exposed to the internet.
    app.run(host="127.0.0.1", port=5000, debug=False)
