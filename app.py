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

load_dotenv()
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-12345")
app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='None')

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# FIXED: Explicit model naming to prevent the 404 error found in your logs
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# ALL LANGUAGES RESTORED (Including Spanish, Dutch, Zulu, Russian, Italian, Urdu, Bahasa, Korean)
LANGUAGES = {
    'en': {'dash': 'Dashboard', 'conn': 'Connect', 'pend': 'Pending', 'sett': 'Settings', 'scan': 'Force Scan', 'dir': 'ltr'},
    'sw': {'dash': 'Dashibodi', 'conn': 'Unganisha', 'pend': 'Inasubiri', 'sett': 'Mipangilio', 'scan': 'Anza Sasa', 'dir': 'ltr'},
    'fr': {'dash': 'Tableau de bord', 'conn': 'Connecter', 'pend': 'En attente', 'sett': 'Paramètres', 'scan': 'Scanner', 'dir': 'ltr'},
    'ar': {'dash': 'لوحة القيادة', 'conn': 'اتصل', 'pend': 'قيد الانتظار', 'sett': 'الإعدادات', 'scan': 'فحص الآن', 'dir': 'rtl'},
    'hi': {'dash': 'डैशबोर्ड', 'conn': 'जुड़ें', 'pend': 'अधूरी कार्यवाही', 'sett': 'सेटिंग्स', 'scan': 'स्कैन करें', 'dir': 'ltr'},
    'zh': {'dash': '仪表板', 'conn': '连接', 'pend': '待处理', 'sett': '设置', 'scan': '强制扫描', 'dir': 'ltr'},
    'es': {'dash': 'Tablero', 'conn': 'Conectar', 'pend': 'Pendiente', 'sett': 'Configuración', 'scan': 'Escanear', 'dir': 'ltr'},
    'nl': {'dash': 'Dashboard', 'conn': 'Verbinden', 'pend': 'In afwachting', 'sett': 'Instellingen', 'scan': 'Nu scannen', 'dir': 'ltr'},
    'zu': {'dash': 'Ideshibhodi', 'conn': 'Xhuma', 'pend': 'Isalindile', 'sett': 'Izilungiselelo', 'scan': 'Skena Manje', 'dir': 'ltr'},
    'ru': {'dash': 'Панель', 'conn': 'Подключить', 'pend': 'Ожидание', 'sett': 'Настройки', 'scan': 'Сканировать', 'dir': 'ltr'},
    'it': {'dash': 'Dashboard', 'conn': 'Connetti', 'pend': 'In attesa', 'sett': 'Impostazioni', 'scan': 'Scansiona', 'dir': 'ltr'},
    'ur': {'dash': 'ڈیش بورڈ', 'conn': 'منسلک کریں', 'pend': 'زیر التوا', 'sett': 'ترجیحات', 'scan': 'فوری اسکین', 'dir': 'rtl'},
    'ms': {'dash': 'Papan Pemuka', 'conn': 'Sambung', 'pend': 'Menunggu', 'sett': 'Tetapan', 'scan': 'Imbas Sekarang', 'dir': 'ltr'},
    'ko': {'dash': '대시보드', 'conn': '연결', 'pend': '대기 중', 'sett': '설정', 'scan': '지금 스캔', 'dir': 'ltr'}
}

@app.context_processor
def inject_translations():
    user_lang = session.get('language', 'en')
    return {'t': LANGUAGES.get(user_lang, LANGUAGES['en'])}

SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/userinfo.email', 'openid']
CLIENT_CONFIG = {"web": {"client_id": os.getenv("GOOGLE_CLIENT_ID"), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"), "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}
PROD_REDIRECT = "https://ernesco.onrender.com/callback"

def scan_inboxes_and_reply():
    try:
        users = supabase.table("profiles").select("*").execute()
        for user in users.data:
            if not user.get('access_token'): continue
            creds = Credentials(token=user['access_token'], refresh_token=user['refresh_token'], 
                                token_uri="https://oauth2.googleapis.com/token", 
                                client_id=os.getenv("GOOGLE_CLIENT_ID"), 
                                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"))
            service = build("gmail", "v1", credentials=creds)
            results = service.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=5).execute()
            for msg in results.get("messages", []):
                try:
                    m = service.users().messages().get(userId='me', id=msg['id']).execute()
                    snippet = m.get('snippet', '')
                    response = model.generate_content(f"Draft a short professional reply: {snippet}")
                    supabase.table("activity_logs").insert({"email": user['email'], "subject": "Auto-Reply", "ai_reply": response.text, "status": "Processed"}).execute()
                except Exception as e: print(f"Msg error: {e}")
    except Exception as e: print(f"Global error: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_inboxes_and_reply, trigger="interval", seconds=300)
scheduler.start()

@app.route('/')
def index():
    emails = []
    if session.get('logged_in'):
        try: emails = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(5).execute().data
        except: pass
    return render_template('index.html', logged_in=session.get('logged_in'), emails=emails)

# FIXED: Added back the connect_email route to fix the BuildError from your logs
@app.route('/connect')
def connect_email():
    if not session.get("logged_in"): return redirect(url_for("login"))
    return render_template('connect_email.html')

@app.route('/pending')
def pending_actions():
    if not session.get("logged_in"): return redirect(url_for("login"))
    count = 0
    try:
        res = supabase.table("activity_logs").select("*", count="exact").execute()
        count = res.count or 0
    except: pass
    return render_template('pending_actions.html', count=count, working_on=0, percentage=0, emails=[])

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if not session.get("logged_in"): return redirect(url_for("login"))
    if request.method == 'POST':
        session['language'] = request.form.get('language', 'en')
        return redirect(url_for('settings'))
    return render_template('settings.html')

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
        supabase.table("profiles").upsert({"email": user_info["email"], "access_token": creds.token, "refresh_token": creds.refresh_token}, on_conflict="email").execute()
        session["logged_in"] = True
        return redirect(url_for("index"))
    except Exception as e: return f"Error: {e}", 400

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/force-scan')
def force_scan():
    scan_inboxes_and_reply()
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
