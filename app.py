import os
import sys
import logging
from flask import Flask, render_template, redirect, url_for, session, request, send_file, flash, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
logger = logging.getLogger(__name__)

load_dotenv()
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

try:
    from supabase import create_client
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    import google.generativeai as genai
    from apscheduler.schedulers.background import BackgroundScheduler
    from gtts import gTTS
    import base64
    from email.message import EmailMessage
    import io
    logger.info("All dependencies loaded successfully")
except ImportError as e:
    logger.error(f"Import error: {e}")
    sys.exit(1)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-12345")
app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='None')

try:
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Supabase and Gemini configured")
except Exception as e:
    logger.error(f"Configuration error: {e}")
    sys.exit(1)

LANGUAGES = {
    'en': {'dash': 'Dashboard', 'conn': 'Connect', 'pend': 'Pending', 'sett': 'Settings', 'scan': 'Force Scan', 'dir': 'ltr', 'opt': 'Optimized', 'scn': 'Scanner', 'stat': 'Status', 'act': 'Active', 'app': 'App', 'lang': 'Language', 'rec': 'Recent', 'resp': 'Response', 'tone': 'Tone', 'prof': 'Professional', 'logs': 'Logs', 'fri': 'Friendly', 'no': 'No', 'save': 'Save', 'all': 'All', 'chng': 'Changes', 'acty': 'Activity', 'cust': 'Customize', 'yet': 'Yet', 'how': 'How', 'go': 'Go', 'erne': 'Ernesco', 'is': 'Is', 'int': 'Interacts', 'tot': 'Total', 'wit': 'With', 'real': 'Real', 'time': 'Time', 'email': 'Email', 'perf': 'Performance', 'proc': 'Processed', 'tdy': 'Today', 'bg': 'Background', 'sys': 'System', 'prog': 'Progress', 'ai': 'AI', 'ana': 'Analyses'},
    'sw': {'dash': 'Dashibodi', 'conn': 'Unganisha', 'pend': 'Inasubiri', 'sett': 'Mipangilio', 'scan': 'Anza Sasa', 'dir': 'ltr', 'opt': 'Imeboreswa', 'scn': 'Skana', 'stat': 'Hali', 'act': 'Amilifu', 'app': 'Programu', 'lang': 'Lugha', 'rec': 'Nyingi', 'resp': 'Jibu', 'tone': 'Sauti', 'prof': 'Kitaalamu', 'logs': 'Orodha', 'fri': 'Karibu', 'no': 'Hapana', 'save': 'Hifadhi', 'all': 'Yote', 'chng': 'Mabadiliko', 'acty': 'Shughuli', 'cust': 'Kamaata', 'yet': 'Bado', 'how': 'Jinsi', 'go': 'Jifanya', 'erne': 'Ernesco', 'is': 'Ni', 'int': 'Ushirikiano', 'tot': 'Jumla', 'wit': 'Na', 'real': 'Halisi', 'time': 'Wakati', 'email': 'Barua', 'perf': 'Utendaji', 'proc': 'Kumprocessia', 'tdy': 'Leo', 'bg': 'Msingi', 'sys': 'Mfumo', 'prog': 'Maendeleo', 'ai': 'AI', 'ana': 'Uchambuzi'},
    'fr': {'dash': 'Tableau de bord', 'conn': 'Connecter', 'pend': 'En attente', 'sett': 'Paramètres', 'scan': 'Scanner', 'dir': 'ltr', 'opt': 'Optimisé', 'scn': 'Scanneur', 'stat': 'Statut', 'act': 'Actif', 'app': 'Application', 'lang': 'Langue', 'rec': 'Récent', 'resp': 'Réponse', 'tone': 'Ton', 'prof': 'Professionnel', 'logs': 'Journaux', 'fri': 'Amical', 'no': 'Non', 'save': 'Enregistrer', 'all': 'Tous', 'chng': 'Modifications', 'acty': 'Activité', 'cust': 'Personnaliser', 'yet': 'Encore', 'how': 'Comment', 'go': 'Allez', 'erne': 'Ernesco', 'is': 'Est', 'int': 'Interagit', 'tot': 'Total', 'wit': 'Avec', 'real': 'Réel', 'time': 'Temps', 'email': 'E-mail', 'perf': 'Performance', 'proc': 'Traité', 'tdy': 'Aujourd\'hui', 'bg': 'Arrière-plan', 'sys': 'Système', 'prog': 'Progression', 'ai': 'IA', 'ana': 'Analyses'},
    'ar': {'dash': 'لوحة القيادة', 'conn': 'اتصل', 'pend': 'قيد الانتظار', 'sett': 'الإعدادات', 'scan': 'فحص الآن', 'dir': 'rtl', 'opt': 'محسّن', 'scn': 'الماسح', 'stat': 'الحالة', 'act': 'نشط', 'app': 'تطبيق', 'lang': 'اللغة', 'rec': 'الأخيرة', 'resp': 'الرد', 'tone': 'النبرة', 'prof': 'احترافي', 'logs': 'السجلات', 'fri': 'ودود', 'no': 'لا', 'save': 'حفظ', 'all': 'الكل', 'chng': 'التغييرات', 'acty': 'النشاط', 'cust': 'تخصيص', 'yet': 'بعد', 'how': 'كيف', 'go': 'اذهب', 'erne': 'Ernesco', 'is': 'هو', 'int': 'يتفاعل', 'tot': 'المجموع', 'wit': 'مع', 'real': 'حقيقي', 'time': 'الوقت', 'email': 'البريد الإلكتروني', 'perf': 'الأداء', 'proc': 'تمت معالجته', 'tdy': 'اليوم', 'bg': 'الخلفية', 'sys': 'النظام', 'prog': 'التقدم', 'ai': 'الذكاء الاصطناعي', 'ana': 'التحليلات'},
    'hi': {'dash': 'डैशबोर्ड', 'conn': 'जुड़ें', 'pend': 'अधूरी कार्यवाही', 'sett': 'सेटिंग्स', 'scan': 'स्कैन करें', 'dir': 'ltr', 'opt': 'अनुकूलित', 'scn': 'स्कैनर', 'stat': 'स्थिति', 'act': 'सक्रिय', 'app': 'ऐप', 'lang': 'भाषा', 'rec': 'हाल ही में', 'resp': 'प्रतिक्रिया', 'tone': 'टोन', 'prof': 'पेशेवर', 'logs': 'लॉग', 'fri': 'अनुकूल', 'no': 'नहीं', 'save': 'सहेजें', 'all': 'सभी', 'chng': 'परिवर्तन', 'acty': 'गतिविधि', 'cust': 'अनुकूलित करें', 'yet': 'अभी तक', 'how': 'कैसे', 'go': 'जाओ', 'erne': 'Ernesco', 'is': 'है', 'int': 'इंटरैक्ट', 'tot': 'कुल', 'wit': 'के साथ', 'real': 'वास्तविक', 'time': 'समय', 'email': 'ईमेल', 'perf': 'प्रदर्शन', 'proc': 'संसाधित', 'tdy': 'आज', 'bg': 'पृष्ठभूमि', 'sys': 'सिस्टम', 'prog': 'प्रगति', 'ai': 'कृत्रिम बुद्धिमत्ता', 'ana': 'विश्लेषण'},
    'zh': {'dash': '仪表板', 'conn': '连接', 'pend': '待处理', 'sett': '设置', 'scan': '强制扫描', 'dir': 'ltr', 'opt': '优化', 'scn': '扫描仪', 'stat': '状态', 'act': '活跃', 'app': '应用', 'lang': '语言', 'rec': '最近', 'resp': '回应', 'tone': '音调', 'prof': '专业', 'logs': '日志', 'fri': '友好', 'no': '否', 'save': '保存', 'all': '所有', 'chng': '更改', 'acty': '活动', 'cust': '定制', 'yet': '尚未', 'how': '怎样', 'go': '去', 'erne': 'Ernesco', 'is': '是', 'int': '交互', 'tot': '总计', 'wit': '与', 'real': '真实', 'time': '时间', 'email': '电子邮件', 'perf': '性能', 'proc': '已处理', 'tdy': '今天', 'bg': '背景', 'sys': '系统', 'prog': '进度', 'ai': '人工智能', 'ana': '分析'},
    'es': {'dash': 'Tablero', 'conn': 'Conectar', 'pend': 'Pendiente', 'sett': 'Configuración', 'scan': 'Escanear', 'dir': 'ltr', 'opt': 'Optimizado', 'scn': 'Escáner', 'stat': 'Estado', 'act': 'Activo', 'app': 'Aplicación', 'lang': 'Idioma', 'rec': 'Reciente', 'resp': 'Respuesta', 'tone': 'Tono', 'prof': 'Profesional', 'logs': 'Registros', 'fri': 'Amistoso', 'no': 'No', 'save': 'Guardar', 'all': 'Todos', 'chng': 'Cambios', 'acty': 'Actividad', 'cust': 'Personalizar', 'yet': 'Aún', 'how': 'Cómo', 'go': 'Ir', 'erne': 'Ernesco', 'is': 'Es', 'int': 'Interactúa', 'tot': 'Total', 'wit': 'Con', 'real': 'Real', 'time': 'Tiempo', 'email': 'Correo Electrónico', 'perf': 'Rendimiento', 'proc': 'Procesado', 'tdy': 'Hoy', 'bg': 'Fondo', 'sys': 'Sistema', 'prog': 'Progreso', 'ai': 'IA', 'ana': 'Análisis'},
    'nl': {'dash': 'Dashboard', 'conn': 'Verbinden', 'pend': 'In afwachting', 'sett': 'Instellingen', 'scan': 'Nu scannen', 'dir': 'ltr', 'opt': 'Geoptimaliseerd', 'scn': 'Scanner', 'stat': 'Status', 'act': 'Actief', 'app': 'Toepassing', 'lang': 'Taal', 'rec': 'Recent', 'resp': 'Reactie', 'tone': 'Toon', 'prof': 'Professioneel', 'logs': 'Logboeken', 'fri': 'Vriendelijk', 'no': 'Nee', 'save': 'Opslaan', 'all': 'Alle', 'chng': 'Wijzigingen', 'acty': 'Activiteit', 'cust': 'Aanpassen', 'yet': 'Nog', 'how': 'Hoe', 'go': 'Ga', 'erne': 'Ernesco', 'is': 'Is', 'int': 'Interacteert', 'tot': 'Totaal', 'wit': 'Met', 'real': 'Echt', 'time': 'Tijd', 'email': 'E-mail', 'perf': 'Prestaties', 'proc': 'Verwerkt', 'tdy': 'Vandaag', 'bg': 'Achtergrond', 'sys': 'Systeem', 'prog': 'Voortgang', 'ai': 'AI', 'ana': 'Analyses'},
    'zu': {'dash': 'Ideshibhodi', 'conn': 'Xhuma', 'pend': 'Isalindile', 'sett': 'Izilungiselelo', 'scan': 'Skena Manje', 'dir': 'ltr', 'opt': 'Kukhuseleliswe', 'scn': 'Iskenadori', 'stat': 'Isimo', 'act': 'Likhuthele', 'app': 'Uhlelo', 'lang': 'Ulimi', 'rec': 'Kamuva', 'resp': 'Impendulo', 'tone': 'Umsindo', 'prof': 'Eprofeshineli', 'logs': 'Imilaphu', 'fri': 'Ukunethezeka', 'no': 'Cha', 'save': 'Londoloza', 'all': 'Konke', 'chng': 'Izinguquko', 'acty': 'Umsebenzi', 'cust': 'Lungiselela', 'yet': 'Njengoba', 'how': 'Kanjani', 'go': 'Hamba', 'erne': 'Ernesco', 'is': 'Ngu', 'int': 'Isebenza', 'tot': 'Isamba', 'wit': 'Nge', 'real': 'Okwenele', 'time': 'Isikhathi', 'email': 'Imeyili', 'perf': 'Umsebenzi', 'proc': 'Kuprocessiwe', 'tdy': 'Namhla', 'bg': 'Isizinda', 'sys': 'Isitemu', 'prog': 'Inqobo', 'ai': 'AI', 'ana': 'Ukuhlaziya'},
    'ru': {'dash': 'Панель', 'conn': 'Подключить', 'pend': 'Ожидание', 'sett': 'Настройки', 'scan': 'Сканировать', 'dir': 'ltr', 'opt': 'Оптимизировано', 'scn': 'Сканер', 'stat': 'Статус', 'act': 'Активный', 'app': 'Приложение', 'lang': 'Язык', 'rec': 'Недавние', 'resp': 'Ответ', 'tone': 'Тон', 'prof': 'Профессиональный', 'logs': 'Журналы', 'fri': 'Дружелюбный', 'no': 'Нет', 'save': 'Сохранить', 'all': 'Все', 'chng': 'Изменения', 'acty': 'Деятельность', 'cust': 'Настроить', 'yet': 'Еще', 'how': 'Как', 'go': 'Идти', 'erne': 'Ernesco', 'is': 'Является', 'int': 'Взаимодействует', 'tot': 'Итого', 'wit': 'С', 'real': 'Реальный', 'time': 'Время', 'email': 'Электронная почта', 'perf': 'Производительность', 'proc': 'Обработано', 'tdy': 'Сегодня', 'bg': 'Фон', 'sys': 'Система', 'prog': 'Прогресс', 'ai': 'ИИ', 'ana': 'Анализы'},
    'it': {'dash': 'Dashboard', 'conn': 'Connetti', 'pend': 'In attesa', 'sett': 'Impostazioni', 'scan': 'Scansiona', 'dir': 'ltr', 'opt': 'Ottimizzato', 'scn': 'Scanner', 'stat': 'Stato', 'act': 'Attivo', 'app': 'Applicazione', 'lang': 'Lingua', 'rec': 'Recente', 'resp': 'Risposta', 'tone': 'Tono', 'prof': 'Professionale', 'logs': 'Registri', 'fri': 'Amichevole', 'no': 'No', 'save': 'Salva', 'all': 'Tutti', 'chng': 'Modifiche', 'acty': 'Attività', 'cust': 'Personalizza', 'yet': 'Ancora', 'how': 'Come', 'go': 'Vai', 'erne': 'Ernesco', 'is': 'È', 'int': 'Interagisce', 'tot': 'Totale', 'wit': 'Con', 'real': 'Reale', 'time': 'Tempo', 'email': 'Email', 'perf': 'Prestazioni', 'proc': 'Elaborato', 'tdy': 'Oggi', 'bg': 'Sfondo', 'sys': 'Sistema', 'prog': 'Progresso', 'ai': 'IA', 'ana': 'Analisi'},
    'ur': {'dash': 'ڈیش بورڈ', 'conn': 'منسلک کریں', 'pend': 'زیر التوا', 'sett': 'ترجیحات', 'scan': 'فوری اسکین', 'dir': 'rtl', 'opt': 'بہتر شدہ', 'scn': 'اسکینر', 'stat': 'حالت', 'act': 'فعال', 'app': 'ایپلیکیشن', 'lang': 'زبان', 'rec': 'حالیہ', 'resp': 'جواب', 'tone': 'لہجہ', 'prof': 'پیشہ ورانہ', 'logs': 'لاگز', 'fri': 'دوستانہ', 'no': 'نہیں', 'save': 'محفوظ کریں', 'all': 'تمام', 'chng': 'تبدیلیاں', 'acty': 'سرگرمی', 'cust': 'اپنی مرضی کے مطابق', 'yet': 'ابھی', 'how': 'کیسے', 'go': 'جاؤ', 'erne': 'Ernesco', 'is': 'ہے', 'int': 'تعامل', 'tot': 'کل', 'wit': 'ساتھ', 'real': 'حقیقی', 'time': 'وقت', 'email': 'ای میل', 'perf': 'کارکردگی', 'proc': 'کارروائی شدہ', 'tdy': 'آج', 'bg': 'پس منظر', 'sys': 'نظام', 'prog': 'پیش رفت', 'ai': 'مصنوعی ذہانت', 'ana': 'تجزیہ'},
    'ms': {'dash': 'Papan Pemuka', 'conn': 'Sambung', 'pend': 'Menunggu', 'sett': 'Tetapan', 'scan': 'Imbas Sekarang', 'dir': 'ltr', 'opt': 'Dioptimalkan', 'scn': 'Pengimbas', 'stat': 'Status', 'act': 'Aktif', 'app': 'Aplikasi', 'lang': 'Bahasa', 'rec': 'Terkini', 'resp': 'Respons', 'tone': 'Nada', 'prof': 'Profesional', 'logs': 'Rekod', 'fri': 'Ramah', 'no': 'Tidak', 'save': 'Simpan', 'all': 'Semua', 'chng': 'Perubahan', 'acty': 'Aktiviti', 'cust': 'Sesuaikan', 'yet': 'Belum', 'how': 'Bagaimana', 'go': 'Pergi', 'erne': 'Ernesco', 'is': 'Adalah', 'int': 'Berinteraksi', 'tot': 'Jumlah', 'wit': 'Dengan', 'real': 'Nyata', 'time': 'Masa', 'email': 'E-mel', 'perf': 'Prestasi', 'proc': 'Diproses', 'tdy': 'Hari Ini', 'bg': 'Latar Belakang', 'sys': 'Sistem', 'prog': 'Kemajuan', 'ai': 'AI', 'ana': 'Analisis'},
    'ko': {'dash': '대시보드', 'conn': '연결', 'pend': '대기 중', 'sett': '설정', 'scan': '지금 스캔', 'dir': 'ltr', 'opt': '최적화됨', 'scn': '스캔', 'stat': '상태', 'act': '활성', 'app': '앱', 'lang': '언어', 'rec': '최근', 'resp': '응답', 'tone': '톤', 'prof': '전문가', 'logs': '로그', 'fri': '친절함', 'no': '아니', 'save': '저장', 'all': '모두', 'chng': '변경사항', 'acty': '활동', 'cust': '사용자 정의', 'yet': '아직', 'how': '어떻게', 'go': '이동', 'erne': 'Ernesco', 'is': '입니다', 'int': '상호작용', 'tot': '총계', 'wit': '함께', 'real': '실시간', 'time': '시간', 'email': '이메일', 'perf': '성능', 'proc': '처리됨', 'tdy': '오늘', 'bg': '배경', 'sys': '시스템', 'prog': '진행률', 'ai': 'AI', 'ana': '분석'}
}

@app.context_processor
def inject_translations():
    user_lang = session.get('language', 'en')
    return {'t': LANGUAGES.get(user_lang, LANGUAGES['en'])}

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
        logger.error(f"Send Error: {e}")
        return False

def scan_inboxes_and_reply():
    try:
        users = supabase.table("profiles").select("*").execute()
        for user in users.data:
            if not user.get('access_token'): continue
            lang = user.get('language', 'en')
            tone = user.get('tone', 'professional')
            creds = Credentials(token=user['access_token'], refresh_token=user['refresh_token'], token_uri="https://oauth2.googleapis.com/token", client_id=os.getenv("GOOGLE_CLIENT_ID"), client_secret=os.getenv("GOOGLE_CLIENT_SECRET"))
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
                    supabase.table("activity_logs").insert({"email": user['email'], "subject": subject, "ai_reply": response.text, "status": status_text}).execute()
                    service.users().messages().batchModify(userId='me', body={'ids': [msg['id']], 'removeLabelIds': ['UNREAD']}).execute()
                except Exception as e:
                    logger.error(f"Msg error: {e}")
    except Exception as e:
        logger.error(f"Global error: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_inboxes_and_reply, trigger="interval", seconds=300)
scheduler.start()

@app.route('/')
def index():
    emails = []
    if session.get('logged_in'):
        try:
            emails = supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(10).execute().data
        except:
            pass
    return render_template('index.html', logged_in=session.get('logged_in'), emails=emails)

@app.route('/connect')
def connect_email():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template('connect_email.html')

@app.route('/pending')
def pending_actions():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    count, sent_count, emails = 0, 0, []
    try:
        res = supabase.table("activity_logs").select("*", count="exact").execute()
        count = res.count or 0
        sent_res = supabase.table("activity_logs").select("*", count="exact").eq("status", "SENT").execute()
        sent_count = sent_res.count or 0
        emails = res.data[:5]
    except:
        pass
    return render_template('pending_actions.html', count=count, sent_count=sent_count, working_on=len(emails), percentage=75, emails=emails)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    if request.method == 'POST':
        lang = request.form.get('language', 'en')
        tone = request.form.get('tone', 'professional')
        session['language'] = lang
        session['tone'] = tone
        try:
            supabase.table("profiles").update({"language": lang, "tone": tone}).eq("email", session.get("user_email")).execute()
            flash("Preferences Saved!", "success")
        except:
            pass
        return redirect(url_for('settings'))
    return render_template('settings.html')

@app.route('/listen/<int:log_id>')
def listen(log_id):
    if not session.get("logged_in"):
        return "Unauthorized", 401
    try:
        res = supabase.table("activity_logs").select("ai_reply").eq("id", log_id).execute()
        if not res.data:
            return "Log not found", 404
        tts = gTTS(text=res.data[0]['ai_reply'], lang=session.get('language', 'en'))
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return send_file(fp, mimetype='audio/mpeg')
    except Exception as e:
        logger.error(f"Listen error: {e}")
        return f"Error: {e}", 500

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
        supabase.table("profiles").upsert({"email": user_info["email"], "access_token": creds.token, "refresh_token": creds.refresh_token}, on_conflict="email").execute()
        session["logged_in"] = True
        return redirect(url_for("index"))
    except Exception as e:
        logger.error(f"Callback error: {e}")
        return f"Error: {e}", 400

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/force-scan')
def force_scan():
    scan_inboxes_and_reply()
    flash("Manual Scan Complete", "success")
    return redirect(url_for('index'))

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'app': 'Ernesco AI Assistant'})

if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 5000))
        logger.info(f"Starting Flask app on port {port}...")
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        logger.error(f"Failed to start Flask app: {e}")
        sys.exit(1)
