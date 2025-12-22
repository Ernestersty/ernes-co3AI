import os
import imaplib
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from supabase import create_client
import openai

load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION ---
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

openai.api_key = OPENAI_KEY
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ROUTES ---

@app.route('/')
def index():
    """Landing Page: Registration/Connect form."""
    return render_template('index.html', emails=[])

@app.route('/verify-connection', methods=['POST'])
def verify_connection():
    """Gatekeeper: Checks if the IMAP credentials actually work."""
    data = request.json
    email_user = data.get('email')
    # This is the 16-character App Password generated in Google/Yahoo settings
    app_pass = data.get('app_password') 

    try:
        # Attempt to connect to Gmail's IMAP server
        # For Yahoo, use "imap.mail.yahoo.com"
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, app_pass)
        mail.logout()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 401

@app.route('/dashboard')
def dashboard():
    """Home Page: Displays the email feed."""
    try:
        response = supabase.table("activity_logs").select("*").order("created_at", desc=True).execute()
        return render_template('index.html', emails=response.data)
    except Exception as e:
        return render_template('index.html', emails=[])

@app.route('/pending-actions')
def pending_actions():
    """Activity/Status Page."""
    try:
        response = supabase.table("activity_logs").select("*").execute()
        all_logs = response.data
        total = len(all_logs)
        completed = len([log for log in all_logs if log.get('status') == 'replied'])
        percentage = int((completed / total) * 100) if total > 0 else 0
        return render_template('pending_actions.html', emails=all_logs, percentage=percentage)
    except:
        return "Database Error."

@app.route('/settings')
def settings():
    return "<h1>Settings</h1><p>Configurations coming soon.</p><a href='/dashboard'>Back</a>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
