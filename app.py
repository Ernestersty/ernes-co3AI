import os
import io
from flask import Flask, render_template, redirect, url_for, session, request, send_file
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
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Clients
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/userinfo.email', 'openid']
CLIENT_CONFIG = {"web": {"client_id": os.getenv("GOOGLE_CLIENT_ID"), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"), "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}
PROD_REDIRECT = "https://ernesco.onrender.com/callback"

def analyze_email(text):
    try:
        lang = detect(text)
        sentiment = TextBlob(text).sentiment.polarity
        mood = "Positive" if sentiment > 0.1 else "Negative" if sentiment < -0.1 else "Neutral"
        return lang, mood
    except:
        return "en", "Neutral"

def scan_inboxes_and_reply():
    print("🤖 ERNESCO AI: Scanning with Gemini...")
    try:
        users = supabase.table("profiles").select("*").execute()
        for user in users.data:
            if not user.get('access_token'): continue
            creds = Credentials(token=user['access_token'], refresh_token=user['refresh_token'], 
                                token_uri=user['token_uri'], client_id=user['client_id'], 
                                client_secret=user['client_secret'], scopes=SCOPES)
            service = build('gmail', 'v1', credentials=creds)
            results = service.users().messages().list(userId='me', q="is:unread").execute()
            
            for msg in results.get('messages', []):
                msg_detail = service.users().messages().get(userId='me', id=msg['id']).execute()
                snippet = msg_detail.get('snippet', '')
                subject = next((h['value'] for h in msg_detail['payload']['headers'] if h['name'] == 'Subject'), 'No Subject')
                
                lang, mood = analyze_email(snippet)
                prompt = f"Reply in {lang}. Mood: {mood}. Be professional. Draft a reply for: {snippet}"
                ai_response = model.generate_content(prompt)
                reply = ai_response.text

                supabase.table("activity_logs").insert({
                    "email": user['email'], "subject": subject, 
                    "ai_reply": reply, "status": f"Mood: {mood}"
                }).execute()

                service.users().messages().batchModify(userId='me', body={'ids': [msg['id']], 'removeLabelIds': ['UNREAD']}).execute()
    except Exception as e:
        print(f"Error during scan: {e}")

# Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_inboxes_and_reply, trigger="interval", seconds=90)
scheduler.start()

# --- ROUTES ---

@app.route('/')
def index():
    emails = []
    if session.get('logged_in'):
        try:
            emails = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(5).execute().data
        except: pass
    return render_template('index.html', logged_in=session.get('logged_in'), emails=emails)

@app.route('/connect')
def connect_email():
    return render_template('connect_email.html')

@app.route('/pending')
def pending_actions():
    # Fetching real count for the progress bar
    count = 0
    if session.get('logged_in'):
        try:
            logs = supabase.table("activity_logs").select("*", count="exact").execute()
            count = logs.count if logs.count else 0
        except: pass
    return render_template('pending_actions.html', count=count, working_on=0, percentage=100)

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/force-scan')
def force_scan():
    scan_inboxes_and_reply()
    return redirect(url_for('index'))

@app.route('/listen/<log_id>')
def listen(log_id):
    try:
        log = supabase.table("activity_logs").select("ai_reply").eq("id", log_id).single().execute()
        tts = gTTS(text=log.data['ai_reply'], lang='en')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return send_file(fp, mimetype='audio/mp3')
    except:
        return "Audio not available", 404

@app.route('/login')
def login():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = PROD_REDIRECT
    url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['state'] = state
    return redirect(url)

@app.route('/callback')
def callback():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, state=session.get('state'))
    flow.redirect_uri = PROD_REDIRECT
    flow.fetch_token(authorization_response=request.url.replace('http:', 'https:'))
    creds = flow.credentials
    user_info = build('oauth2', 'v2', credentials=creds).userinfo().get().execute()
    
    supabase.table("profiles").upsert({
        "email": user_info['email'], 
        "access_token": creds.token, 
        "refresh_token": creds.refresh_token, 
        "token_uri": creds.token_uri, 
        "client_id": creds.client_id, 
        "client_secret": creds.client_secret
    }, on_conflict="email").execute()
    
    session['logged_in'] = True
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
