import os
import io
import traceback
from flask import Flask, render_template, redirect, url_for, session, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from supabase import create_client
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import google.generativeai as genai
from apscheduler.schedulers.background import BackgroundScheduler
from textblob import TextBlob
from langdetect import detect
from gtts import gTTS

load_dotenv()
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-12345")
app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='None')

# Clients
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# --- SAFELY INITIALIZE GEMINI ---
def get_ai_model():
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
        genai.configure(api_key=api_key)
        return genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        print(f"AI Init Error: {e}")
        return None

# Translation Dictionary
LANGUAGES = {
    'en': {'dash': 'Dashboard', 'conn': 'Connect', 'pend': 'Pending', 'sett': 'Settings', 'scan': 'Force Scan', 'dir': 'ltr'},
    # ... (other languages kept as per your original list)
}

@app.context_processor
def inject_translations():
    user_lang = session.get('language', 'en')
    return {'t': LANGUAGES.get(user_lang, LANGUAGES['en'])}

SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/userinfo.email', 'openid']
CLIENT_CONFIG = {"web": {"client_id": os.getenv("GOOGLE_CLIENT_ID"), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"), "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}
PROD_REDIRECT = "https://ernesco.onrender.com/callback"

def scan_inboxes_and_reply():
    model = get_ai_model()
    if not model:
        print("Scan aborted: Gemini Model not configured.")
        return

    try:
        users = supabase.table("profiles").select("*").execute()
        for user in users.data:
            if not user.get('access_token'): continue
            
            creds = Credentials(
                token=user['access_token'],
                refresh_token=user['refresh_token'],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
            )
            
            service = build("gmail", "v1", credentials=creds)
            results = service.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=5).execute()
            messages = results.get("messages", [])
            
            for msg in messages:
                try:
                    msg_detail = service.users().messages().get(userId='me', id=msg['id']).execute()
                    snippet = msg_detail.get('snippet', '')
                    subject = next((h['value'] for h in msg_detail['payload']['headers'] if h['name'] == 'Subject'), 'No Subject')
                    
                    # Sentiment logic
                    lang = detect(snippet) if snippet else "en"
                    sentiment = TextBlob(snippet).sentiment.polarity
                    mood = "Positive" if sentiment > 0.1 else "Negative" if sentiment < -0.1 else "Neutral"
                    
                    # Gemini Draft
                    ai_response = model.generate_content(f"Reply in {lang}. Tone: Professional. Content: {snippet}")
                    reply = ai_response.text

                    supabase.table("activity_logs").insert({
                        "email": user['email'], "subject": subject, 
                        "ai_reply": reply, "status": f"Mood: {mood}"
                    }).execute()

                    # Mark as read
                    service.users().messages().batchModify(userId='me', body={'ids': [msg['id']], 'removeLabelIds': ['UNREAD']}).execute()
                except Exception as inner_e:
                    print(f"Message skip: {inner_e}")
    except Exception as e:
        print(f"Global Scan Error: {e}")

# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_inboxes_and_reply, trigger="interval", seconds=300) # Increased to 5 mins for safety
scheduler.start()

@app.route('/pending')
def pending_actions():
    if not session.get("logged_in"): 
        return redirect(url_for("login"))
    
    # Force defaults to prevent Jinja2 Undefined errors
    count = 0
    working_on = 0
    percentage = 0
    emails = []

    try:
        res = supabase.table("activity_logs").select("*", count="exact").execute()
        count = res.count or 0
        # Optional: fetch some logs to show in the list
        log_data = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(5).execute()
        emails = log_data.data if log_data.data else []
    except Exception as e:
        print(f"DB Fetch Error: {e}")

    if count > 0:
        percentage = int((working_on / count) * 100)

    return render_template('pending_actions.html', 
                           count=count, 
                           working_on=working_on, 
                           percentage=percentage, 
                           emails=emails)

@app.route('/login')
def login():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, redirect_uri=PROD_REDIRECT)
    auth_url, state = flow.authorization_url(access_type='offline', prompt='consent', include_granted_scopes='true')
    session['state'] = state
    return redirect(auth_url)

@app.route('/callback')
def callback():
    try:
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
    except Exception as e:
        return f"Auth Error: {e}", 400

# Include other routes (index, logout, force_scan, etc.) similarly wrapped in try/except

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
