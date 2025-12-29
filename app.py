import os
from flask import Flask, render_template, redirect, url_for, session, request
from dotenv import load_dotenv
from supabase import create_client
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from apscheduler.schedulers.background import BackgroundScheduler
import openai

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# --- CLIENTS ---
openai.api_key = os.getenv("OPENAI_API_KEY")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CLIENT_CONFIG = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

# --- BACKGROUND TASK ---
def scan_inboxes_and_reply():
    print("🤖 ERNESCO AI: Scanning inboxes...")
    try:
        users = supabase.table("profiles").select("*").execute()
        for user in users.data:
            # Logic for Gmail/OpenAI goes here (same as your previous version)
            pass
    except Exception as e:
        print(f"Error in background task: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_inboxes_and_reply, trigger="interval", minutes=10)
scheduler.start()

# --- ROUTES ---

@app.route('/')
def index():
    # If the user just logged in, 'logged_in' will be True
    logged_in = session.get('logged_in', False)
    return render_template('index.html', logged_in=logged_in)

@app.route('/login')
def login():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    # Use the REDIRECT_URI from your .env
    flow.redirect_uri = os.getenv("REDIRECT_URI")
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, state=session.get('state'))
    flow.redirect_uri = os.getenv("REDIRECT_URI")
    
    # Fix: Render uses HTTPS, but Flask might see HTTP. This forces it to match.
    authorization_response = request.url.replace('http:', 'https:') if 'render.com' in request.url else request.url
    
    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials

    # Save to Supabase
    try:
        supabase.table("profiles").upsert({
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "email": "user@example.com" # Ideally fetch from google service.users().getProfile()
        }).execute()
    except Exception as e:
        print(f"Supabase Error: {e}")

    session['logged_in'] = True
    # REDIRECT BACK TO HOME instead of a separate dashboard to avoid 404
    return redirect(url_for('index'))

@app.route('/privacy')
def privacy():
    return render_template('index.html', show_privacy=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
                





