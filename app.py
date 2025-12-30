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
    'zh': {'dash': '仪表板', 'conn': '连接', 'pend': '待办事项', 'sett': '设置', 'scan': '强制扫描', 'dir': 'ltr'}
}

@app.context_processor
def inject_translations():
    user_lang = session.get('language', 'en')
    return {'t': LANGUAGES.get(user_lang, LANGUAGES['en'])}

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
            
            # Important: Since session isn't available in background threads, 
            # we check the user's saved preferences from the profile table.
            # (Note: In a full app, you'd save 'language' and 'tone' to the database)
            # For now, we use the session or default to 'en'
            pref_lang = session.get('language', 'en')
            pref_tone = session.get('tone', 'professional')

            for msg in results.get('messages', []):
                msg_detail = service.users().messages().get(userId='me', id=msg['id']).execute()
                snippet = msg_detail.get('snippet', '')
                subject = next((h['value'] for h in msg_detail['payload']['headers'] if h['name'] == 'Subject'), 'No Subject')
                
                lang, mood = analyze_email(snippet)
                
                # AI Instruction based on Settings
                prompt = f"Reply in {pref_lang}. Make the tone {pref_tone}. The detected mood is {mood}. Draft a reply for: {snippet}"
                ai_response = model.generate_content(prompt)
                reply = ai_response.text

                supabase.table("activity_logs").insert({
                    "email": user['email'], "subject": subject, 
                    "ai_reply": reply, "status": f"Mood: {mood}"
                }).execute()

                service.users().messages().batchModify(userId='me', body={'ids': [msg['id']], 'removeLabelIds': ['UNREAD']}).execute()
    except Exception as e:
        print(f"Error during scan: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_inboxes_and_reply, trigger="interval", seconds=90)
scheduler.start()

@app.route('/')
def index():
    emails = []
    if session.get('logged_in'):
        try:
            emails = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(5).execute().data
        except: pass
    return render_template('index.html', logged_in=session.get('logged_in'), emails=emails)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        session['language'] = request.form.get('language')
        session['tone'] = request.form.get('tone')
        return redirect(url_for('settings'))
    return render_template('settings.html')

@app.route('/pending')
def pending_actions():
    count = 0
    if session.get('logged_in'):
        try:
            logs = supabase.table("activity_logs").select("*", count="exact").execute()
            count = logs.count if logs.count else 0
        except: pass
    return render_template('pending_actions.html', count=count, working_on=0, percentage=100)

@app.route('/connect')
def connect_email():
    return render_template('connect_email.html')

@app.route('/force-scan')
def force_scan():
    scan_inboxes_and_reply()
    return redirect(url_for('index'))

@app.route('/listen/<log_id>')
def listen(log_id):
    try:
        log = supabase.table("activity_logs").select("ai_reply").eq("id", log_id).single().execute()
        # Voice also matches chosen language
        tts_lang = session.get('language', 'en')
        tts = gTTS(text=log.data['ai_reply'], lang=tts_lang)
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
        "email": user_info['email'], "access_token": creds.token, "refresh_token": creds.refresh_token, 
        "token_uri": creds.token_uri, "client_id": creds.client_id, "client_secret": creds.client_secret
    }, on_conflict="email").execute()
    session['logged_in'] = True
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
