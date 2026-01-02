import os
import io
import base64  # Added for email encoding
from email.message import EmailMessage  # Added for email structure
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
    'ms': {'dash': 'Papan Pemuka', 'sambung': 'Sambung', 'pend': 'Menunggu', 'sett': 'Tetapan', 'scan': 'Imbas Sekarang', 'dir': 'ltr'},
    'ko': {'dash': '대시보드', 'conn': '연결', 'pend': '대기 중', 'sett': '설정', 'scan': '지금 스캔', 'dir': 'ltr'}
}

@app.context_processor
def inject_translations():
    user_lang = session.get
