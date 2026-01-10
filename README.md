# Dental Scanner - Web UI

This repository contains a simple Flask frontend that uploads an image, runs `main.py` on it, and serves the generated `output.jpg`.

Quick start (macOS, zsh):

1. Make sure you have Homebrew Python 3.11 installed (we used `/opt/homebrew/bin/python3.11`).
2. Create and activate the venv:
```
/opt/homebrew/bin/python3.11 -m venv .venv311
source .venv311/bin/activate
```
3. Install dependencies:
```
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```
4. Set your `ROBOFLOW_API_KEY`:
   - Create a `.env` file in the project root directory
   - Add this line: `ROBOFLOW_API_KEY=your_actual_api_key_here`
   - Replace `your_actual_api_key_here` with your actual Roboflow API key
   - Get your API key from: https://app.roboflow.com/
   - The `.env` file is automatically loaded by `server.py` using `python-dotenv`
5. Run the server:
```
python server.py
```
6. Open http://127.0.0.1:5000 in a browser, upload an image, and view the resulting `output.jpg`.
