import os
from dotenv import load_dotenv
import subprocess
import json
import requests
import sqlite3
import smtplib
import shutil
import mimetypes
from email.message import EmailMessage
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, send_file, flash, session, jsonify
from datetime import datetime

APP_ROOT = Path(__file__).parent.resolve()
UPLOAD_DIR = APP_ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me")

# Load environment variables from .env if present (local dev convenience).
load_dotenv()

# Default OpenAI model used for AI summarization. Can be overridden by setting
# OPENAI_API_MODEL in the environment or .env (example: OPENAI_API_MODEL=gpt-5-mini)
DEFAULT_OPENAI_MODEL = os.environ.get('OPENAI_API_MODEL', 'gpt-5-mini')

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

# --- Simple SQLite database for storing landing-page profiles ---
DB_PATH = APP_ROOT / "data.db"

def init_db():
    """Create the profiles table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                provider TEXT NOT NULL,
                dob TEXT NOT NULL,
                patient_email TEXT NOT NULL,
                doctor_email TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

# Initialize DB on import/startup
init_db()


# --- Email helper --------------------------------------------------------
def send_email_smtp(to_email: str, subject: str, body: str, attachments: list[str], use_random_from: bool = False, reply_to: str | None = None) -> tuple[bool, str]:
    """Send an email using SMTP settings from environment.

    Returns (success, message).
    Expects attachments as list of absolute path strings.
    """
    smtp_server = os.environ.get('SMTP_SERVER')
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    smtp_user = os.environ.get('SMTP_USER')
    smtp_pass = os.environ.get('SMTP_PASSWORD')
    use_tls = os.environ.get('SMTP_USE_TLS', 'true').lower() not in ('0','false','no')

    # Debug: print masked SMTP env info so we can diagnose missing-config vs runtime send errors
    try:
        print(f"send_email_smtp: smtp_server={smtp_server!r}, smtp_port={smtp_port!r}, smtp_user_set={bool(smtp_user)}, smtp_pass_set={bool(smtp_pass)}, use_tls={use_tls}")
    except Exception:
        pass

    if not smtp_server or not smtp_user or not smtp_pass:
        # Fallback for local testing: save the composed message and attachments to disk
        try:
            out_dir = APP_ROOT / 'outgoing_emails'
            out_dir.mkdir(exist_ok=True)
            stamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
            import uuid as _uuid
            fname = f'email_{stamp}_{_uuid.uuid4().hex[:8]}.json'
            target = out_dir / fname
            # Copy attachments into a subfolder for this message
            attach_dir = out_dir / (fname + '_attachments')
            attach_dir.mkdir(exist_ok=True)
            copied = []
            for p in attachments:
                try:
                    src = Path(p)
                    if src.exists():
                        dest = attach_dir / src.name
                        shutil.copy(src, dest)
                        copied.append(str(dest.name))
                except Exception:
                    pass

            # Include a brief snapshot of the env so we can diagnose why fallback was used
            env_snapshot = {
                'SMTP_SERVER': bool(os.environ.get('SMTP_SERVER')),
                'SMTP_USER': bool(os.environ.get('SMTP_USER')),
                'SMTP_PASSWORD': bool(os.environ.get('SMTP_PASSWORD')),
                'SMTP_FROM': bool(os.environ.get('SMTP_FROM')),
                'SMTP_PORT': os.environ.get('SMTP_PORT')
            }

            payload = {
                'from': os.environ.get('SMTP_FROM', smtp_user),
                'to': to_email,
                'subject': subject,
                'body': body,
                'attachments': copied,
                'note': 'Saved locally because SMTP_SERVER/SMTP_USER/SMTP_PASSWORD not configured.',
                'env_snapshot': env_snapshot
            }
            import json as _json
            with open(target, 'w', encoding='utf-8') as fh:
                _json.dump(payload, fh, ensure_ascii=False, indent=2)
            return True, f"Saved email to {str(target)}"
        except Exception as e:
            return False, f"SMTP not configured and fallback save failed: {str(e)}"

    msg = EmailMessage()
    # Determine From address. Optionally generate a random local-part if requested.
    configured_from = os.environ.get('SMTP_FROM', smtp_user)
    from_addr = configured_from

    if use_random_from:
        # Derive domain from configured_from or smtp_user or fall back to example.com
        domain = None
        for src in (configured_from, smtp_user):
            if src and '@' in src:
                domain = src.split('@',1)[1]
                break
        if not domain:
            domain = os.environ.get('SMTP_FROM_DOMAIN', 'example.com')
        import uuid
        local = uuid.uuid4().hex[:12]
        from_addr = f"{local}@{domain}"

    msg['From'] = from_addr
    # If a reply-to address is provided (e.g., patient), ensure replies go there
    if reply_to:
        msg['Reply-To'] = reply_to
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.set_content(body)

    # Attach files
    for p in attachments:
        try:
            path = Path(p)
            if not path.exists():
                continue
            ctype, encoding = mimetypes.guess_type(str(path))
            if ctype is None:
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)
            with open(path, 'rb') as fh:
                data = fh.read()
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)
        except Exception as e:
            # continue attaching other files
            print('Attachment failed', p, str(e))

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as s:
            if use_tls:
                s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        print('send_email_smtp: Email sent successfully')
        return True, 'Email sent'
    except Exception as e:
        # Log exception to help debugging; return the error message upstream
        print('send_email_smtp: Exception during SMTP send:', str(e))
        return False, str(e)



@app.route("/", methods=["GET"])
def terms():
    # Show terms and services page first
    return render_template("terms.html")


@app.route("/accept-terms", methods=["POST"])
def accept_terms():
    print("Accept terms route called")
    print("Form data:", request.form)
    print("Headers:", dict(request.headers))
    print("User Agent:", request.headers.get('User-Agent', 'Unknown'))
    
    # Check if both checkboxes were checked
    if request.form.get('acceptTerms') and request.form.get('medicalDisclaimer'):
        # Handle terms acceptance
        session['terms_accepted'] = True
        print("Terms accepted, session updated")
        
        # For mobile preview compatibility, also use URL parameter as backup
        # Check if this is a JSON request (AJAX) or form submission
        if request.is_json or request.headers.get('Content-Type') == 'application/json':
            return jsonify({"success": True})
        else:
            # Form submission - redirect with URL parameter for mobile compatibility
            print("Redirecting to welcome page with URL parameter")
            return redirect(url_for('welcome', terms_accepted='true'))
    else:
        print("Terms not properly accepted")
        flash('You must accept both terms to continue.')
        return redirect(url_for('terms'))


@app.route("/debug-session", methods=["GET"])
def debug_session():
    return jsonify({
        "session": dict(session),
        "terms_accepted": session.get('terms_accepted', False)
    })

@app.route("/welcome", methods=["GET"])
def welcome():
    print("Welcome route called")
    print("Session:", dict(session))
    print("URL args:", request.args)
    print("Terms accepted in session:", session.get('terms_accepted'))
    
    # Check if terms have been accepted (session OR URL parameter for mobile compatibility)
    terms_accepted_session = session.get('terms_accepted', False)
    terms_accepted_url = request.args.get('terms_accepted') == 'true'
    
    print("Terms accepted via session:", terms_accepted_session)
    print("Terms accepted via URL:", terms_accepted_url)
    
    if not (terms_accepted_session or terms_accepted_url):
        print("Terms not accepted, redirecting to terms page")
        return redirect(url_for('terms'))
    
    # If terms accepted via URL but not in session, update session
    if terms_accepted_url and not terms_accepted_session:
        session['terms_accepted'] = True
        print("Updated session from URL parameter")
    
    print("Terms accepted, showing welcome page")
    # show a welcome form that collects basic user info before proceeding
    return render_template("welcome.html")


@app.route('/upload-page', methods=['GET'])
def index():
    # Check if terms have been accepted (session OR URL parameter for mobile compatibility)
    terms_accepted_session = session.get('terms_accepted', False)
    terms_accepted_url = request.args.get('terms_accepted') == 'true'
    
    if not (terms_accepted_session or terms_accepted_url):
        return redirect(url_for('terms'))
    
    # If terms accepted via URL but not in session, update session
    if terms_accepted_url and not terms_accepted_session:
        session['terms_accepted'] = True
    
    # show upload form and recent output if present
    output_path = APP_ROOT / "output.jpg"
    output_exists = output_path.exists()
    return render_template("index.html", output_exists=output_exists)


@app.route('/save-profile', methods=['POST'])
def save_profile():
    """Persist landing-page profile into SQLite and set session values.

    Expected form fields: firstName, lastName, provider, dob, patientEmail, doctorEmail, terms_accepted
    """
    data = {}
    for f in ('firstName', 'lastName', 'provider', 'dob', 'patientEmail', 'doctorEmail'):
        val = request.form.get(f)
        if not val:
            flash('Please fill out all required fields')
            return redirect(url_for('welcome'))
        data[f] = val.strip()

    terms_accepted = request.form.get('terms_accepted') == 'true'

    # Save to DB
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO profiles (first_name, last_name, provider, dob, patient_email, doctor_email, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                data['firstName'],
                data['lastName'],
                data['provider'],
                data['dob'],
                data['patientEmail'],
                data['doctorEmail'],
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    except Exception as e:
        print('DB insert failed:', str(e))
        flash('Could not save profile (internal error)')
        return redirect(url_for('welcome'))
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # Store basic info in session so other pages can use it locally
    session['first_name'] = data['firstName']
    session['last_name'] = data['lastName']
    session['provider'] = data['provider']
    session['dob'] = data['dob']
    session['patient_email'] = data['patientEmail']
    session['doctor_email'] = data['doctorEmail']
    session['terms_accepted'] = terms_accepted

    # Redirect to upload page; for mobile compatibility, append URL param if terms accepted via URL
    if terms_accepted:
        return redirect(url_for('index', terms_accepted='true'))
    return redirect(url_for('index'))


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
                # Prefer explicit env override but fall back to the module-level default
                model = os.environ.get('OPENAI_API_MODEL', DEFAULT_OPENAI_MODEL)
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
                    # Use max_tokens for OpenAI Chat Completions API
                    "max_completion_tokens": 5000,
                    "temperature": 1,
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
@app.route('/send-to-doctor', methods=['POST'])
def send_to_doctor():
    """Send an email to the stored doctor_email with concerns and both original and annotated images.

    Expects JSON body or form with optional 'uploaded_filename' and optional 'concern' override.
    """
    # Debug: log incoming request data and session for diagnosis
    try:
        print('send_to_doctor called; headers=', dict(request.headers))
        print('send_to_doctor called; form=', dict(request.form))
        print('send_to_doctor called; json=', request.get_json(silent=True))
        print('send_to_doctor session keys=', {k: bool(session.get(k)) for k in ('patient_email','doctor_email')})
    except Exception:
        pass

    # Determine uploaded filename: priority JSON/form uploaded_filename, then session stored value on result div is client-side
    uploaded_filename = request.form.get('uploaded_filename') or (request.json or {}).get('uploaded_filename') if request.is_json else None
    concern = request.form.get('concern') or (request.json or {}).get('concern') if request.is_json else None

    # Best-effort: use session values if present
    doctor_email = session.get('doctor_email') or request.form.get('doctor_email') or (request.json or {}).get('doctor_email')
    patient_email = session.get('patient_email')

    if not doctor_email:
        return jsonify({'success': False, 'error': 'No doctor email available'}), 400

    # Build attachments: uploaded original in uploads/<filename> and annotated output.jpg in repo root
    attachments = []
    if uploaded_filename:
        upath = UPLOAD_DIR / uploaded_filename
        if upath.exists():
            attachments.append(str(upath))
    # annotated output
    annotated = APP_ROOT / 'output.jpg'
    if annotated.exists():
        attachments.append(str(annotated))

    if not attachments:
        return jsonify({'success': False, 'error': 'No files available to attach'}), 400

    # Compose email body
    body_lines = []
    body_lines.append('Dear Provider,')
    body_lines.append('')
    body_lines.append('A patient has submitted dental images via the Open Wide app. See attachments for the original and annotated images.')
    body_lines.append('')
    if patient_email:
        body_lines.append(f'Patient contact email: {patient_email}')
    if concern:
        body_lines.append('Patient concerns:')
        body_lines.append(concern)
    else:
        # try to read concern file saved next to uploaded file
        if uploaded_filename:
            cfile = UPLOAD_DIR / (uploaded_filename + '.concern.txt')
            if cfile.exists():
                try:
                    body_lines.append('Patient concerns:')
                    body_lines.append(open(cfile, encoding='utf-8').read())
                except Exception:
                    pass

    body_lines.append('')
    body_lines.append('This message was sent from the Open Wide app.')

    subject = 'Dental images from Open Wide'

    # Check if caller requested a random from-address
    random_from_flag = False
    try:
        if request.is_json:
            random_from_flag = bool((request.json or {}).get('random_from'))
        else:
            random_from_flag = bool(request.form.get('random_from'))
    except Exception:
        random_from_flag = False

    # Environment can also force random-from behavior
    if os.environ.get('SMTP_RANDOM_FROM', '').lower() in ('1','true','yes'):
        random_from_flag = True

    success, msg = send_email_smtp(doctor_email, subject, '\n'.join(body_lines), attachments, use_random_from=random_from_flag, reply_to=patient_email)
    if not success:
        return jsonify({'success': False, 'error': msg}), 500
    return jsonify({'success': True, 'message': msg})


if __name__ == '__main__':
    # Helpful startup checks
    if not VENV_PY.exists():
        print(f"Warning: venv python not found at {VENV_PY}. Create venv311 and install deps first.")
    print('Starting server on http://127.0.0.1:5000')
    app.run(host='127.0.0.1', port=5000, debug=True)
