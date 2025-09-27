import os
import subprocess
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, send_file, flash

APP_ROOT = Path(__file__).parent.resolve()
UPLOAD_DIR = APP_ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me")

# Path to the Python interpreter inside the venv we created earlier
VENV_PY = APP_ROOT / ".venv311" / "bin" / "python"


@app.route("/", methods=["GET"])
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

    # AJAX client expects JSON with the result URL
    if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {"success": True, "result_url": url_for('result')}

    return redirect(url_for('result'))


@app.route('/result')
def result():
    out = APP_ROOT / 'output.jpg'
    if not out.exists():
        flash('No output image found')
        return redirect(url_for('index'))
    return send_file(out, mimetype='image/jpeg')


if __name__ == '__main__':
    # Helpful startup checks
    if not VENV_PY.exists():
        print(f"Warning: venv python not found at {VENV_PY}. Create venv311 and install deps first.")
    print('Starting server on http://127.0.0.1:5000')
    app.run(host='127.0.0.1', port=5000, debug=True)
