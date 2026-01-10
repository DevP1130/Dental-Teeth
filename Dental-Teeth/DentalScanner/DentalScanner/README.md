# DentalScanner (Open Wide)

Small Flask app that accepts dental images, runs a local annotation script (`main.py`), optionally summarizes findings with OpenAI, and sends the original + annotated images to a provider via SMTP.

## Quick start

1. Create a Python 3.11 virtual environment and install dependencies:

    ```powershell
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    ```

2. (Optional) Create a `.env` file in the project root to store secrets (example below).

3. Run the app:

    ```powershell
    python server.py
    ```

    Open http://127.0.0.1:5000 in your browser.

## Important files and directories

- `server.py` - Flask app and route handlers.
- `main.py` - image processing / annotation script (invoked by `server.py`).
- `uploads/` - stored original uploads and sidecar `.concern.txt` / `.summary.txt` files.
- `output.jpg` - annotated image produced by `main.py` (served at `/result`).
- `outgoing_emails/` - local fallback directory where unsent emails are saved when SMTP is not configured.

## Environment variables

Recommended `.env` (do NOT commit credentials):

```
FLASK_SECRET=change-me
OPENAI_API_KEY=sk-....   # optional (for AI summaries)
OPENAI_API_MODEL=gpt-5-mini
OPENAI_TIMEOUT=30
OPENAI_RETRIES=3
OPENAI_BACKOFF_BASE=1.5

# SMTP (optional) - if not set, outgoing messages are saved to outgoing_emails/
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASSWORD=...
SMTP_FROM=you@example.com
SMTP_USE_TLS=true
SMTP_RANDOM_FROM=false
```

## Routes

- `GET /` - Terms page (must accept to continue).
- `POST /accept-terms` - Accept terms.
- `GET /welcome` - Simple profile capture.
- `POST /save-profile` - Persist landing page profile to SQLite.
- `GET /upload-page` - Upload UI.
- `POST /upload` - Upload image (multipart/form-data, field `image`). Returns JSON for XHR requests with keys: `success`, `result_url`, `original_url`, `uploaded_filename`, and optionally `ai_summary`.
- `GET /result` - Returns the annotated `output.jpg` (if present).
- `GET /uploads/<filename>` - Serves the original uploaded files.
- `POST /send-to-doctor` - Sends an email to the configured doctor email (from session or request) attaching both original and annotated images. If SMTP is not configured, the message is saved under `outgoing_emails/`.

## Troubleshooting

- If you see emails saved in `outgoing_emails/`, check that `SMTP_SERVER`, `SMTP_USER`, and `SMTP_PASSWORD` are set in the environment used to run `server.py`. The saved JSON includes an `env_snapshot` showing which SMTP envs were present.

- OpenAI timeouts: configure `OPENAI_TIMEOUT` and `OPENAI_RETRIES` in your `.env` if you experience `Read timed out` errors. The server logs attempt messages for each retry.

- If `main.py` does not produce `output.jpg`, check the script runs correctly by invoking it manually:

    ```powershell
    .\.venv\Scripts\Activate.ps1; python main.py uploads\yourfile.jpg
    ```

- To inspect outgoing fallback messages, open the generated `.json` files under `outgoing_emails/` and examine copied attachments in the corresponding `_attachments` folder.

## Development notes

- The app is intended for local development. For production use, run with a WSGI server and background long-running tasks (image processing, OpenAI calls, and email sending) to avoid blocking request handlers.

- Tests: none included. You may add unit tests for `send_email_smtp` and for the upload flow.

## Contact

If you want me to add more documentation (function docstrings across all modules, an API reference, or a CONTRIBUTING.md), tell me which parts to focus on and I will add them.
