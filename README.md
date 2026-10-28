# DeepGuard — Full Source Starter

A responsive DeepGuard-style media screening app based on the screenshots provided.

## Included
- Login-style demo screen (not production authentication)
- Workspace overview and model-unavailable status
- Image/video upload record flow
- SQLite screening history
- Delete record and stored upload
- Responsive mobile UI
- Upload extension allowlist and 200 MB request limit
- Honest model-unavailable behavior: **no fake deepfake scores or predictions**

## Run on Replit
1. Create a new Python Repl or import this folder as a ZIP.
2. Ensure the Repl uses Python.
3. Install dependencies:
   `pip install -r requirements.txt`
4. Run:
   `python app.py`
5. Open the web preview.

The app listens on `0.0.0.0` and uses `PORT` if provided by the environment.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```
Open http://localhost:3000.

## Important limitations before public deployment
- The login screen is a UI-only demo gate. It does not verify passwords or isolate users. Do not treat it as authentication.
- Uploads are stored in `data/uploads/` and the SQLite database in `data/deepguard.db`. Set retention, private storage, authentication, authorization, rate limits, CSRF protection, and secure production deployment before exposing this app publicly.
- File extensions are checked, but production systems should also inspect file signatures and safely decode media.
- No detection model is included. The interface explicitly reports that the model is unavailable and makes no authenticity prediction. To enable real detection, integrate a documented model with licensed weights and evaluate it on a held-out dataset without source leakage.
- Do not store secrets in the repository. Use Replit Secrets or environment variables.
