import os
import base64
from dotenv import load_dotenv
import subprocess
import json
import requests
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, send_file, flash, jsonify
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import smtplib

APP_ROOT = Path(__file__).parent.resolve()
UPLOAD_DIR = APP_ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me")

# Load environment variables from .env if present (local dev convenience).
# Explicitly load from APP_ROOT to ensure we find .env in the project root
env_path = APP_ROOT / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()  # Fallback: try to find .env automatically

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
    # Ensure API key is in the environment (reload .env if needed)
    api_key = env.get('ROBOFLOW_API_KEY')
    if not api_key and env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        env = os.environ.copy()
        api_key = env.get('ROBOFLOW_API_KEY')
    if api_key:
        print(f"API key found: {api_key[:10]}... (length: {len(api_key)})")
    else:
        print("WARNING: ROBOFLOW_API_KEY not found in environment!")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
        # Log output for debugging
        if proc.stdout:
            print(f"main.py stdout: {proc.stdout[:1000]}")
        if proc.stderr:
            print(f"main.py stderr: {proc.stderr[:1000]}")
    except subprocess.TimeoutExpired:
        if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": "Processing timed out"}, 504
        flash('Processing timed out')
        return redirect(url_for('index'))

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "Unknown error")[:500]
        if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": f"Processing failed: {err}"}, 500
        flash('Processing failed: ' + err)
        return redirect(url_for('index'))

    # If main.py saved output.jpg in repo root, serve it
    output_path = APP_ROOT / "output.jpg"
    if not output_path.exists():
        # Include subprocess output in error message for debugging
        debug_info = ""
        if proc.stdout:
            debug_info = f"\n\nmain.py output: {proc.stdout[-500:]}"
        if proc.stderr:
            debug_info += f"\n\nmain.py errors: {proc.stderr[-500:]}"
        error_msg = f"No output image produced. The workflow may not have returned an annotated image.{debug_info}"
        if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {"success": False, "error": error_msg}, 500
        flash(error_msg)
        return redirect(url_for('index'))

    # AJAX client expects JSON with the result URL; include uploaded filename so client can attach concerns
    if request.headers.get('Accept') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Attempt to summarize findings using OpenAI if an API key is available.
        ai_summary = None
        ai_error = None
        
        try:
            OPENAI_KEY = os.environ.get('OPENAI_API_KEY')
            if OPENAI_KEY and output_path.exists():
                # Use vision-capable model to analyze the annotated image
                model = os.environ.get('OPENAI_API_MODEL', 'gpt-4o-mini')
                
                # Read and encode the annotated image as base64
                with open(output_path, 'rb') as img_file:
                    img_data = base64.b64encode(img_file.read()).decode('utf-8')
                
                # Determine image format
                img_format = 'jpeg' if output_path.suffix.lower() in ['.jpg', '.jpeg'] else 'png'
                
                system_msg = (
                    "You are a helpful dental assistant. Analyze the annotated dental image provided by the user. "
                    "The image shows dental X-rays or photos with annotations/detections highlighted. "
                    "Provide a concise analysis of the detected issues, a risk assessment (low/medium/high) with reasons, "
                    "and recommended next actions. Reply in plain text, organized into sections: Summary:, Risk:, Actions:."
                )
                
                # Build user message with image and patient concerns
                user_content = []
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{img_format};base64,{img_data}",
                        "detail": "high"
                    }
                })
                
                text_parts = [f"Please analyze this annotated dental image"]
                if concern_text:
                    text_parts.append(f"\n\nPatient's additional concerns: {concern_text}")
                else:
                    text_parts.append(f"\n\nNo additional concerns provided by the patient.")
                
                user_content.append({
                    "type": "text",
                    "text": "".join(text_parts)
                })

                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_content}
                    ],
                    "max_tokens": 800,
                    "temperature": 0.15,
                }

                headers = {
                    "Authorization": f"Bearer {OPENAI_KEY}",
                    "Content-Type": "application/json"
                }

                resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
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


@app.route('/send-report', methods=['POST'])
def send_report():
    """Send email report with annotated image and AI summary to patient and doctor"""
    try:
        data = request.get_json()
        patient_email = data.get('patient_email')
        doctor_email = data.get('doctor_email')
        ai_summary = data.get('ai_summary', '')
        
        if not patient_email or not doctor_email:
            return jsonify({"success": False, "error": "Patient and doctor emails are required"}), 400
        
        # Get the annotated image
        output_path = APP_ROOT / "output.jpg"
        if not output_path.exists():
            return jsonify({"success": False, "error": "Annotated image not found"}), 404
        
        # Email configuration from environment variables
        smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        email_from = os.environ.get('EMAIL_FROM', '').strip().strip('"').strip("'")
        email_password = os.environ.get('EMAIL_PASSWORD', '').strip().strip('"').strip("'")
        
        if not email_from or not email_password:
            return jsonify({
                "success": False, 
                "error": "Email configuration not found. Please set EMAIL_FROM and EMAIL_PASSWORD in .env file"
            }), 500
        
        # Create email message
        msg = MIMEMultipart('related')
        msg['From'] = email_from
        msg['To'] = f"{patient_email}, {doctor_email}"
        msg['Subject'] = 'Dental Scan Report - Annotated Image & AI Analysis'
        
        # Escape HTML in AI summary to prevent injection
        from html import escape
        ai_summary_escaped = escape(ai_summary) if ai_summary else 'No AI analysis available.'
        ai_summary_html = ai_summary_escaped.replace('\n', '<br>')
        
        # Create email body with AI summary
        body_html = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #020617;">Dental Scan Report</h2>
            <p>Please find your dental scan analysis report below.</p>
            
            <h3 style="color: #020617; margin-top: 24px;">AI Analysis</h3>
            <div style="background-color: #f8f9fa; padding: 16px; border-radius: 8px; margin: 12px 0; white-space: pre-wrap;">{ai_summary_html}</div>
            
            <h3 style="color: #020617; margin-top: 24px;">Annotated Image</h3>
            <p>The annotated dental scan image is attached to this email.</p>
            
            <hr style="margin: 24px 0; border: none; border-top: 1px solid #ddd;">
            <p style="color: #666; font-size: 12px;">This is an automated report from Dental Scanner.</p>
          </body>
        </html>
        """
        
        body_text = f"""
Dental Scan Report

Please find your dental scan analysis report below.

AI Analysis:
{ai_summary if ai_summary else 'No AI analysis available.'}

Annotated Image:
The annotated dental scan image is attached to this email.

---
This is an automated report from Dental Scanner.
        """
        
        # Add text and HTML versions
        msg_alternative = MIMEMultipart('alternative')
        msg_alternative.attach(MIMEText(body_text, 'plain'))
        msg_alternative.attach(MIMEText(body_html, 'html'))
        msg.attach(msg_alternative)
        
        # Attach the annotated image
        with open(output_path, 'rb') as img_file:
            img_data = img_file.read()
            img = MIMEImage(img_data)
            img.add_header('Content-Disposition', 'attachment', filename='annotated_dental_scan.jpg')
            msg.attach(img)
        
        # Send email
        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_from, email_password)
            server.send_message(msg)
            server.quit()
            
            return jsonify({
                "success": True,
                "message": f"Report sent successfully to {patient_email} and {doctor_email}"
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to send email: {str(e)}"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Error sending report: {str(e)}"
        }), 500


# (Concerns are saved as part of the upload form under uploads/<filename>.concern.txt)


if __name__ == '__main__':
    # Helpful startup checks
    if not VENV_PY.exists():
        print(f"Warning: venv python not found at {VENV_PY}. Create venv311 and install deps first.")
    print('Starting server on http://127.0.0.1:5000')
    app.run(host='127.0.0.1', port=5000, debug=True)