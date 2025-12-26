import os
from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from dotenv import load_dotenv
from supabase import create_client
import google_auth_oauthlib.flow
import openai

# 1. Load Environment Variables from your .env
load_dotenv()

app = Flask(__name__)
# Flask needs this key to handle the 'Continue with Google' session
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# --- CONFIGURATION ---
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

openai.api_key = OPENAI_KEY
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Google OAuth Config
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
# This must match your Google Cloud Console exactly
REDIRECT_URI = os.getenv("REDIRECT_URI")

CLIENT_CONFIG = {
    "web": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

# The permission ERNESCO needs: Reading and Drafting emails
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# --- ROUTES ---

@app.route('/')
def index():
    """Landing Page: Now checks if user is logged in."""
    is_logged_in = 'credentials' in session
    return render_template('index.html', emails=[], logged_in=is_logged_in)

@app.route('/login')
def login():
    """Starts the Google OAuth process."""
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent' # Forces Google to provide a Refresh Token
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    """Google sends the user here after they click 'Allow'."""
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        CLIENT_CONFIG, scopes=SCOPES, state=session['state'])
    flow.redirect_uri = REDIRECT_URI

    # Exchange the code from the URL for real tokens
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    # SAVE TO SUPABASE: Store the tokens so the AI can work later
    # Note: In a real app, you'd fetch the user's email here too
    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }
    
    # Save the 'Digital Key' to your profiles table
    supabase.table("profiles").upsert(token_data).execute()

    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    """Displays the AI activity feed from Supabase."""
    try:
        response = supabase.table("activity_logs").select("*").order("created_at", desc=True).execute()
        return render_template('index.html', emails=response.data, logged_in=True)
    except Exception as e:
        print(f"Error fetching logs: {e}")
        return render_template('index.html', emails=[], logged_in=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Allow local HTTP for testing; Render handles HTTPS automatically
    if os.getenv("REDIRECT_URI") and "127.0.0.1" in os.getenv("REDIRECT_URI"):
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
        
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
