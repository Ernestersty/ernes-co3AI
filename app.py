import os
import io
from flask import Flask, render_template, redirect, url_for, session, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from supabase import create_client
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- INITIALIZATION ---
load_dotenv()
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

app = Flask(__name__)

# Essential for Render HTTPS
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-12345")

# Supabase Client
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# OAuth Configuration
SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/userinfo.email', 'openid']
CLIENT_CONFIG = {"web": {
    "client_id": os.getenv("GOOGLE_CLIENT_ID"), 
    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"), 
    "auth_uri": "https://accounts.google.com/o/oauth2/auth", 
    "token_uri": "https://oauth2.googleapis.com/token"
}}
PROD_REDIRECT = "https://ernesco.onrender.com/callback"

# Translation helper (Simplified)
@app.context_processor
def inject_translations():
    return {'t': {'dash': 'Dashboard', 'conn': 'Connect', 'pend': 'Pending', 'sett': 'Settings', 'scan': 'Scan', 'dir': 'ltr'}}

# --- ROUTES ---

@app.route('/')
def index():
    emails = []
    if session.get('logged_in'):
        try:
            # Simple fetch to verify Supabase connection
            emails = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(5).execute().data
        except:
            pass
    return render_template('index.html', logged_in=session.get('logged_in'), emails=emails)

@app.route('/pending')
def pending_actions():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    count = 0
    try:
        # STEP 2 CHECK: Does the DB return a count?
        res = supabase.table("activity_logs").select("*", count="exact").execute()
        count = res.count or 0
    except Exception as e:
        print(f"Pending Error: {e}")

    return render_template('pending_actions.html', count=count, working_on=0, percentage=0)

@app.route('/login')
def login():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, redirect_uri=PROD_REDIRECT)
    auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['state'] = state
    return redirect(auth_url)

@app.route('/callback')
def callback():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, state=session.get('state'))
    flow.redirect_uri = PROD_REDIRECT
    flow.fetch_token(authorization_response=request.url.replace('http:', 'https:'))
    
    creds = flow.credentials
    user_info = build('oauth2', 'v2', credentials=creds).userinfo().get().execute()

    supabase.table("profiles").upsert({
        "email": user_info["email"], 
        "access_token": creds.token,
        "refresh_token": creds.refresh_token
    }, on_conflict="email").execute()

    session["logged_in"] = True
    return redirect(url_for("index"))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
