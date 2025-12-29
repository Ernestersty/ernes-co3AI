import os
from flask import Flask, render_template, redirect, url_for, session, request
from dotenv import load_dotenv
from supabase import create_client
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build # Added for email fetching

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Clients
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Add 'userinfo.email' to scopes so we know who is logging in
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]

CLIENT_CONFIG = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

# HARD-CODED REDIRECT to stop the 127.0.0.1 error
PROD_REDIRECT = "https://ernesco.onrender.com/callback"

@app.route('/')
def index():
    emails = []
    logged_in = session.get('logged_in', False)
    
    if logged_in:
        try:
            # Shows recent AI activity from Supabase
            response = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(5).execute()
            emails = response.data
        except Exception as e:
            print(f"Supabase error: {e}")

    return render_template('index.html', logged_in=logged_in, emails=emails)

@app.route('/login')
def login():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = PROD_REDIRECT
    # 'offline' access_type ensures we get a Refresh Token
    authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, state=session.get('state'))
    flow.redirect_uri = PROD_REDIRECT
    
    # Fix Render's HTTP proxy issue
    auth_url = request.url.replace('http:', 'https:')
    flow.fetch_token(authorization_response=auth_url)
    
    creds = flow.credentials
    
    # 1. Fetch user email using Google API
    try:
        service = build('oauth2', 'v2', credentials=creds)
        user_info = service.userinfo().get().execute()
        user_email = user_info.get('email')
        
        # 2. Save tokens to Supabase 'profiles' table
        supabase.table("profiles").upsert({
            "email": user_email,
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret
        }, on_conflict="email").execute()
        
        print(f"✅ Saved tokens for {user_email}")
        session['user_email'] = user_email
        
    except Exception as e:
        print(f"❌ Error during callback storage: {e}")

    session['logged_in'] = True
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
