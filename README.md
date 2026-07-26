# Smear / Scope — malaria smear classifier

A small web app that uploads a blood-smear image, sends it once to your
`MalariaDetection.keras` model via a local API, and reports:

- whether parasites were detected (infected / uninfected)
- smear thickness (thin / thick)
- the model's confidence

## Project layout

```
malaria-app/
├── backend/
│   ├── app.py            # Flask API that loads the model and runs inference
│   ├── requirements.txt
│   └── model/
│       └── MalariaDetection.keras
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── README.md
```

## Class mapping

Your model outputs 4 logits. Per the training folder order you confirmed
(alphabetical, as produced by `image_dataset_from_directory`), `app.py`
maps them as:

```
0 -> Thick_Infected
1 -> Thick_Uninfected
2 -> Thin_Infected
3 -> Thin_Uninfected
```

If your actual training order was different, update the `CLASS_LABELS`
list near the top of `backend/app.py` — everything else derives from it.

## Running it locally

```bash
cd malaria-app/backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```

Then open **http://127.0.0.1:5000** — Flask serves both the API and the
frontend for local use. (For a real deployment, you'd more likely serve
`frontend/` as static files from a CDN/host and point `API_ENDPOINT` in
`app.js` at wherever the API runs — see "Deploying" below.)

## How privacy is handled

This app is built so it never has patient data to lose:

- **No disk writes.** Uploaded images are decoded straight from memory
  (`io.BytesIO`) and never saved to a file.
- **No logging of content.** Only Flask's default access log (method,
  path, status) is written — never image bytes, filenames, or results.
- **No accounts, cookies, or sessions.** Every request is stateless;
  nothing links one upload to another or to a person.
- **No analytics or third-party scripts.** The frontend loads only Google
  Fonts (typefaces, no tracking) and calls your own API.
- **Client-side preview only.** The image preview in the browser uses a
  local `blob:` URL and isn't sent anywhere until you click "analyze."

### About HIPAA specifically

This code is designed so the *application logic* doesn't collect or
retain protected health information — but HIPAA compliance is a property
of an entire system and its operator, not of a single script. If you plan
to actually use this with real patient images, you (or your organization)
are still responsible for things this code can't provide on its own:

- Encryption in transit (put this behind HTTPS/TLS — Flask's dev server
  alone does not do this)
- A Business Associate Agreement with whatever host/cloud provider you
  deploy on, if any PHI could pass through their infrastructure
- Access controls and an audit trail for *who accessed the system*
  (not image content) if required by your organization's policies
  and a formal risk assessment
- Physical/organizational safeguards required by your compliance program

In short: this app avoids collecting data it doesn't need, but "HIPAA
compliant" is a certification about your whole deployment, not a checkbox
this code can tick for you.

### Medical disclaimer

This is a research/educational classifier. It has not been reviewed or
cleared by the FDA or any other regulatory body for clinical diagnostic
use. Results should never be used to make real diagnostic or treatment
decisions without confirmation by a qualified microscopist or clinician.

## Deploying beyond localhost

- Run the Flask app behind a production WSGI server (e.g. `gunicorn`)
  and a reverse proxy (e.g. nginx) that terminates TLS.
- If you serve the frontend separately from the API's origin, update
  `API_ENDPOINT` in `frontend/app.js` to the API's full URL, and restrict
  CORS on the Flask side to that specific frontend origin.
- Keep `MAX_CONTENT_LENGTH` in `app.py` set to a sane cap to prevent
  abuse via huge uploads.
