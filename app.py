import os
from flask import Flask, render_template, redirect, url_for, session, request
from dotenv import load_dotenv
from supabase import create_client
from google_auth_oauthlib.flow import Flow

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Clients
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

@app.route('/')
def index():
    # Fetch logs from Supabase to show on the dashboard if logged in
    emails = []
    logged_in = session.get('logged_in', False)
    
    if logged_in:
        try:
            response = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(5).execute()
            emails = response.data
        except Exception as e:
            print(f"Supabase error: {e}")

    return render_template('index.html', logged_in=logged_in, emails=emails)

@app.route('/login')
def login():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = os.getenv("REDIRECT_URI")
    authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, state=session.get('state'))
    flow.redirect_uri = os.getenv("REDIRECT_URI")
    
    # FIX: Ensure the callback URL uses HTTPS (Render requirement)
    auth_url = request.url.replace('http:', 'https:') if 'render.com' in request.url else request.url
    flow.fetch_token(authorization_response=auth_url)
    
    creds = flow.credentials
    session['logged_in'] = True
    
    # Save tokens to Supabase here
    # supabase.table("profiles").upsert({...}).execute()

    return redirect(url_for('index')) # Redirecting back to home avoids the 404

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))


