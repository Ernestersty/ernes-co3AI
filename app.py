import os
import io
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

# Load Environment Variables
load_dotenv()
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

app = Flask(__name__)

# 1. Enable HTTPS support for Render
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# 2. Secure Secret Key handling
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-12345")

# 3. Session Security for Production
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='None'
)

# Clients Initialization
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Configure Gemini AI
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# Translation Dictionary
LANGUAGES = {
    'en': {'dash': 'Dashboard', 'conn': 'Connect', 'pend': 'Pending', 'sett': 'Settings', 'scan': 'Force Scan', 'dir': 'ltr'},
    'sw': {'dash': 'Dashibodi', 'conn': 'Unganisha', 'pend': 'Inasubiri', 'sett': 'Mipangilio', 'scan': 'Anza Sasa', 'dir': 'ltr'},
    'fr': {'dash': 'Tableau de bord', 'conn': 'Connecter', 'pend': 'En attente', 'sett': 'Paramètres', 'scan': 'Scanner', 'dir': 'ltr'},
    'es': {'dash': 'Tablero', 'conn': 'Conectar', 'pend': 'Pendiente', 'sett': 'Ajustes', 'scan': 'Escanear', 'dir': 'ltr'},
    'de': {'dash': 'Dashboard', 'conn': 'Verbinden', 'pend': 'Ausstehend', 'sett': 'Einstellungen', 'scan': 'Escanear', 'dir': 'ltr'},
    'zu': {'dash': 'Ideshibhodi', 'conn': 'Xhuma', 'pend': 'Kulindile', 'sett': 'Izilungiselelo', 'scan': 'Skena', 'dir': 'ltr'},
    'ru': {'dash': 'Панель', 'conn': 'Связь', 'pend': 'Ожидание', 'sett': 'Настройки', 'scan': 'Сканировать', 'dir': 'ltr'},
    'it': {'dash': 'Dashboard', 'conn': 'Connetti', 'pend': 'In sospeso', 'sett': 'Impostazioni', 'scan': 'Scansione', 'dir': 'ltr'},
    'ur': {'dash': 'ڈیش بورڈ', 'conn': 'رابطہ کریں', 'pend': 'باقی عمل', 'sett': 'ترجیحات', 'scan': 'اسکین کریں', 'dir': 'rtl'},
    'ar': {'dash': 'لوحة القيادة', 'conn': 'اتصل', 'pend': 'قيد الانتظار', 'sett': 'الإعدادات', 'scan': 'فحص الآن', 'dir': 'rtl'},
    'ms': {'dash': 'Papan Pemuka', 'conn': 'Sambung', 'pend': 'Menunggu', 'sett': 'Tetapan', 'scan': 'Imbas', 'dir': 'ltr'},
    'hi': {'dash': 'डैशबोर्ड', 'conn': 'कनेक्ट करें', 'pend': 'लंबित', 'sett': 'सेटिंग्स', 'scan': 'स्कैन करें', 'dir': 'ltr'},
    'ko': {'dash': '대시보드', 'conn': '연결', 'pend': '대기 중', 'sett': '설정', 'scan': '스캔', 'dir': 'ltr'},
    'zh': {'dash': '仪表板', 'conn': '连接', '待办事项': 'Pending', 'sett': '设置', 'scan': '强制扫描', 'dir': 'ltr'}
}

# OAuth Configuration
SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/userinfo.email', 'openid']
CLIENT_CONFIG = {"web": {"client_id": os.getenv("GOOGLE_CLIENT_ID"), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"), "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}
PROD_REDIRECT = "https://ernesco.onrender.com/callback"

@app.context_processor
def inject_translations():
    user_lang = session.get('language', 'en')
    return {'t': LANGUAGES.get(user_lang, LANGUAGES['en'])}

def analyze_email(text):
    try:
        lang = detect(text)
        sentiment = TextBlob(text).sentiment.polarity
        mood = "Positive" if sentiment > 0.1 else "Negative" if sentiment < -0.1 else "Neutral"
        return lang, mood
    except:
        return "en", "Neutral"

# Background Worker
def scan_inboxes_and_reply():
    print("🤖 ERNESCO AI: Scanning with Gemini...")
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
            
            # Fetch last 10 Inbox messages
            results = service.users().messages().list(
                userId="me",
                labelIds=["INBOX"],
                maxResults=10
            ).execute()

            messages = results.get("messages", [])
            
            # Use background defaults
            pref_lang = 'en'
            pref_tone = 'professional'

            for msg in messages:
                msg_detail = service.users().messages().get(userId='me', id=msg['id']).execute()
                snippet = msg_detail.get('snippet', '')
                subject = next((h['value'] for h in msg_detail['payload']['headers'] if h['name'] == 'Subject'), 'No Subject')
                
                lang, mood = analyze_email(snippet)
                
                prompt = f"Reply in {pref_lang}. Make the tone {pref_tone}. The detected mood is {mood}. Draft a reply for: {snippet}"
                ai_response = model.generate_content(prompt)
                reply = ai_response.text

                # Log to Supabase
                supabase.table("activity_logs").insert({
                    "email": user['email'], "subject": subject, 
                    "ai_reply": reply, "status": f"Mood: {mood}"
                }).execute()

                # Mark as Read
                service.users().messages().batchModify(userId='me', body={'ids': [msg['id']], 'removeLabelIds': ['UNREAD']}).execute()
    except Exception as e:
        print(f"Error during scan: {e}")

# Scheduler Setup
scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_inboxes_and_reply, trigger="interval", seconds=90)
scheduler.start()

# --- ROUTES ---

@app.route('/')
def index():
    emails = []
    if session.get('logged_in'):
        try:
            emails = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(10).execute().data
        except: pass
    return render_template('index.html', logged_in=session.get('logged_in'), emails=emails)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
        
    if request.method == 'POST':
        session['language'] = request.form.get('language')
        session['tone'] = request.form.get('tone')
        return redirect(url_for('settings'))
    return render_template('settings.html')

@app.route('/pending')
def pending_actions():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    count = 0
    working_on = 0
    try:
        logs = supabase.table("activity_logs").select("*", count="exact").execute()
        count = logs.count or 0
    except Exception as e:
        print("Pending error:", e)

    percentage = int((working_on / count) * 100) if count > 0 else 0
    return render_template('pending_actions.html', count=count, working_on=working_on, percentage=percentage)

@app.route('/connect')
def connect_email():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template('connect_email.html')

@app.route('/force-scan')
def force_scan():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    scan_inboxes_and_reply()
    return redirect(url_for('index'))

@app.route('/listen/<log_id>')
def listen(log_id):
    if not session.get("logged_in"):
        return "Unauthorized", 401
    try:
        log = supabase.table("activity_logs").select("ai_reply").eq("id", log_id).single().execute()
        tts_lang = session.get('language', 'en')
        tts = gTTS(text=log.data['ai_reply'], lang=tts_lang)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return send_file(fp, mimetype='audio/mp3')
    except:
        return "Audio not available", 404

# --- AUTH ROUTES ---

@app.route('/login')
def login():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, redirect_uri=PROD_REDIRECT)
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
    session['state'] = state
    return redirect(authorization_url)

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
        "refresh_token": creds.refresh_token,
        "token_expiry": creds.expiry.isoformat() if creds.expiry else None
    }, on_conflict="email").execute()

    session["logged_in"] = True
    return redirect(url_for("index"))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
            
            
