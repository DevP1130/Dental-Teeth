import os
from dotenv import load_dotenv
import subprocess
import json
import requests
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, send_file, flash

APP_ROOT = Path(__file__).parent.resolve()
UPLOAD_DIR = APP_ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me")

# Load environment variables from .env if present (local dev convenience).
load_dotenv()

# Path to the Python interpreter inside a venv. Try several common locations so
# the app works on Windows and Unix without forcing a specific venv name.
cand_paths = [
    APP_ROOT / ".venv" / "Scripts" / "python.exe",      # Windows (typical)
    APP_ROOT / ".venv311" / "Scripts" / "python.exe",  # Windows alt
    APP_ROOT / ".venv311" / "bin" / "python",         # Unix-style venv311
    APP_ROOT / ".venv" / "bin" / "python",            # Unix-style .venv
]

VENV_PY = None
for p in cand_paths:
    if p.exists():
        VENV_PY = p
        break

# If none of the expected venv python paths exist, default to the first
# candidate (keeps behavior similar to before; startup will print a helpful
# warning which prompts the user to create/point to the correct venv).
if VENV_PY is None:
    VENV_PY = cand_paths[0]


@app.route("/", methods=["GET"])
def welcome():
    # show a welcome form that collects basic user info before proceeding
    return render_template("welcome.html")


@app.route('/upload-page', methods=['GET'])
def index():
    # show upload form and recent output if present
    output_path = APP_ROOT / "output.jpg"
    output_exists = output_path.exists()
    return render_template("index.html", output_exists=output_exists)


@app.route("/upload", methods=["POST"])
def upload():
    if 'image' not in request.files:
        if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "No file part"}, 400
        flash('No file part')
        return redirect(url_for('index'))

    file = request.files['image']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('index'))

    # Save uploaded file
    save_path = UPLOAD_DIR / file.filename
    file.save(save_path)

    # If a concern string was sent in the form, save it next to the uploaded file
    concern_text = request.form.get('concern', '').strip()
    if concern_text:
        safe_name = os.path.basename(file.filename)
        concern_path = UPLOAD_DIR / (safe_name + '.concern.txt')
        try:
            with open(concern_path, 'w', encoding='utf-8') as fh:
                fh.write(concern_text)
        except Exception:
            # non-fatal: continue processing the main image
            pass

    # Ensure the venv python exists
    if not VENV_PY.exists():
        flash(f'Venv python not found at {VENV_PY}. Activate the correct venv or create .venv311')
        return redirect(url_for('index'))

    # Run main.py with the uploaded image path
    main_py = APP_ROOT / "main.py"
    cmd = [str(VENV_PY), str(main_py), str(save_path)]

    # Keep environment so main.py can read ROBOFLOW_API_KEY from env
    env = os.environ.copy()

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    except subprocess.TimeoutExpired:
        if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "Processing timed out"}, 504
        flash('Processing timed out')
        return redirect(url_for('index'))

    if proc.returncode != 0:
        err = proc.stderr[:500]
        if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": err}, 500
        flash('Processing failed: ' + err)
        return redirect(url_for('index'))

    # If main.py saved output.jpg in repo root, serve it
    output_path = APP_ROOT / "output.jpg"
    if not output_path.exists():
        if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "No output image produced"}, 500
        flash('No output image produced')
        return redirect(url_for('index'))

    # AJAX client expects JSON with the result URL; include uploaded filename so client can attach concerns
    if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Attempt to summarize findings using OpenAI if an API key is available.
        ai_summary = None
        ai_error = None
        
        try:
            OPENAI_KEY = os.environ.get('OPENAI_API_KEY')
            if OPENAI_KEY:
                # Compose a short prompt that asks for a concise summary, risk assessment, and recommended actions.
                model = os.environ.get('OPENAI_API_MODEL', 'gpt-4o-mini')
                system_msg = (
                    "You are a helpful dental assistant. Given a patient's short concern text and that an image of their teeth was uploaded, "
                    "provide a concise (3-6 line) summary of possible issues, a brief risk assessment (low/medium/high) with reasons, "
                    "and suggested next actions. Reply in plain text, organized into sections: Summary:, Risk:, Actions:."
                )
                user_msg = f"Uploaded filename: {file.filename}\nPatient concerns: {concern_text}" if concern_text else f"Uploaded filename: {file.filename}\nPatient provided no additional concerns."

                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.15,
                }

                headers = {
                    "Authorization": f"Bearer {OPENAI_KEY}",
                    "Content-Type": "application/json"
                }

                resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=15)
                if resp.status_code == 200:
                    j = resp.json()
                    # Safely extract assistant text
                    ai_text = None
                    try:
                        ai_text = j['choices'][0]['message']['content']
                    except Exception:
                        ai_text = None
                    if ai_text:
                        ai_summary = ai_text.strip()
                        # Save summary next to the uploaded file for records
                        try:
                            safe_name = os.path.basename(file.filename)
                            summary_path = UPLOAD_DIR / (safe_name + '.summary.txt')
                            with open(summary_path, 'w', encoding='utf-8') as sf:
                                sf.write(ai_summary)
                        except Exception:
                            # non-fatal: ignore file write issues
                            pass
                    else:
                        ai_error = 'No assistant content returned'
                else:
                    ai_error = f'OpenAI API error {resp.status_code}: {resp.text[:400]}'
            else:
                ai_error = 'OPENAI_API_KEY not set; skipping AI summary'
        except Exception as e:
            ai_error = f'AI summarization failed: {str(e)[:300]}'

        out = {"success": True, "result_url": url_for('result'), "uploaded_filename": file.filename}
        if ai_summary:
            out['ai_summary'] = ai_summary
        else:
            out['ai_summary_error'] = ai_error
        return out

    return redirect(url_for('result'))


@app.route('/result')
def result():
    out = APP_ROOT / 'output.jpg'
    if not out.exists():
        flash('No output image found')
        return redirect(url_for('index'))
    return send_file(out, mimetype='image/jpeg')


# (Concerns are saved as part of the upload form under uploads/<filename>.concern.txt)


if __name__ == '__main__':
    # Helpful startup checks
    if not VENV_PY.exists():
        print(f"Warning: venv python not found at {VENV_PY}. Create venv311 and install deps first.")
    print('Starting server on http://127.0.0.1:5000')
    app.run(host='127.0.0.1', port=5000, debug=True)
