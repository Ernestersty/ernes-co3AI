import os
import io
import base64
from email.message import EmailMessage
from flask import Flask, render_template, redirect, url_for, session, request, send_file, flash
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from supabase import create_client
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import google.generativeai as genai
from apscheduler.schedulers.background import BackgroundScheduler
from gtts import gTTS

load_dotenv()
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-12345")
app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='None')

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Gemini Configuration
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# Multilingual UI Dictionary (Kept exactly as provided)
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

# OAuth Setup - Fixed Variable Name
SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/userinfo.email', 'openid']
CLIENT_CONFIG = {"web": {"client_id": os.getenv("GOOGLE_CLIENT_ID"), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"), "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}
REDIRECT_URI = "https://ernesco.onrender.com/callback"

def send_gmail_reply(service, thread_id, msg_id, to_email, subject, body):
    try:
        message = EmailMessage()
        message.set_content(body)
        message['To'] = to_email
        message['Subject'] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        message['In-Reply-To'] = msg_id
        message['References'] = msg_id
        raw_msg = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId="me", body={'raw': raw_msg, 'threadId': thread_id}).execute()
        return True
    except Exception as e:
        print(f"Send Error: {e}")
        return False

def scan_inboxes_and_reply():
    try:
        users = supabase.table("profiles").select("*").execute()
        for user in users.data:
            if not user.get('access_token'): continue
            lang = user.get('language', 'en')
            tone = user.get('tone', 'professional')
            creds = Credentials(token=user['access_token'], refresh_token=user['refresh_token'], 
                                token_uri="https://oauth2.googleapis.com/token", 
                                client_id=os.getenv("GOOGLE_CLIENT_ID"), 
                                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"))
            service = build("gmail", "v1", credentials=creds)
            results = service.users().messages().list(userId="me", q="is:unread", maxResults=5).execute()
            
            for msg in results.get("messages", []):
                try:
                    m = service.users().messages().get(userId='me', id=msg['id']).execute()
                    headers = m.get('payload', {}).get('headers', [])
                    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
                    sender = next((h['value'] for h in headers if h['name'] == 'From'), "")
                    msg_id = next((h['value'] for h in headers if h['name'] == 'Message-ID'), "")
                    
                    prompt = f"Draft a short {tone} email reply. Write the response entirely in {lang}. Email snippet: {m.get('snippet', '')}"
                    response = model.generate_content(prompt)
                    
                    success = send_gmail_reply(service, m['threadId'], msg_id, sender, subject, response.text)
                    status_text = "SENT" if success else "FAILED"
                    
                    supabase.table("activity_logs").insert({
                        "email": user['email'], "subject": subject, "ai_reply": response.text, "status": status_text
                    }).execute()

                    service.users().messages().batchModify(userId='me', body={'ids': [msg['id']], 'removeLabelIds': ['UNREAD']}).execute()
                except Exception as e: print(f"Msg error: {e}")
    except Exception as e: print(f"Global error: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_inboxes_and_reply, trigger="interval", seconds=300)
scheduler.start()

@app.route('/')
def index():
    emails = []
    if session.get('logged_in'):
        try:
            emails = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(10).execute().data
        except: pass
    return render_template('index.html', logged_in=session.get('logged_in'), emails=emails)

@app.route('/connect')
def connect_email():
    if not session.get("logged_in"): return redirect(url_for("login"))
    return render_template('connect_email.html')

@app.route('/pending')
def pending_actions():
    if not session.get("logged_in"): return redirect(url_for("login"))
    count, sent_count, emails = 0, 0, []
    try:
        res = supabase.table("activity_logs").select("*", count="exact").execute()
        count = res.count or 0
        sent_res = supabase.table("activity_logs").select("*", count="exact").eq("status", "SENT").execute()
        sent_count = sent_res.count or 0
        emails = res.data[:5]
    except: pass
    return render_template('pending_actions.html', count=count, sent_count=sent_count, working_on=len(emails), percentage=75, emails=emails)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if not session.get("logged_in"): return redirect(url_for("login"))
    if request.method == 'POST':
        lang = request.form.get('language', 'en')
        tone = request.form.get('tone', 'professional')
        session['language'] = lang
        session['tone'] = tone
        try:
            supabase.table("profiles").update({"language": lang, "tone": tone}).eq("email", session.get("user_email")).execute()
            flash("Preferences Saved!", "success")
        except: pass
        return redirect(url_for('settings'))
    return render_template('settings.html')

@app.route('/listen/<int:log_id>')
def listen(log_id):
    if not session.get("logged_in"): return "Unauthorized", 401
    try:
        res = supabase.table("activity_logs").select("ai_reply").eq("id", log_id).execute()
        if not res.data: return "Log not found", 404
        tts = gTTS(text=res.data[0]['ai_reply'], lang=session.get('language', 'en'))
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return send_file(fp, mimetype='audio/mpeg')
    except Exception as e: return f"Error: {e}", 500

@app.route('/login')
def login():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, state = flow.authorization_url(access_type='offline', prompt='consent', include_granted_scopes='true')
    session['state'] = state
    return redirect(auth_url)

@app.route('/callback')
def callback():
    try:
        flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, state=session.get('state'))
        flow.redirect_uri = REDIRECT_URI
        flow.fetch_token(authorization_response=request.url.replace('http:', 'https:'))
        creds = flow.credentials
        user_info = build('oauth2', 'v2', credentials=creds).userinfo().get().execute()
        
        session["user_name"] = user_info.get("given_name", "User").upper()
        session["user_email"] = user_info["email"]
        
        supabase.table("profiles").upsert({
            "email": user_info["email"], "access_token": creds.token, "refresh_token": creds.refresh_token
        }, on_conflict="email").execute()
        
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
    flash("Manual Scan Complete", "success")
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
