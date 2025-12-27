import os
from flask import Flask, render_template, redirect, url_for, session, request
from dotenv import load_dotenv
from supabase import create_client
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from apscheduler.schedulers.background import BackgroundScheduler
import openai

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# --- CLIENTS ---
openai.api_key = os.getenv("OPENAI_API_KEY")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Google Configuration
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CLIENT_CONFIG = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

# --- BACKGROUND TASK: THE AI BRAIN ---

def scan_inboxes_and_reply():
    """Wakes up every 10 mins, finds users, and drafts AI replies."""
    print("🤖 ERNESCO AI: Scanning inboxes...")
    
    # 1. Get all users who have connected their Google Account
    users = supabase.table("profiles").select("*").execute()
    
    for user in users.data:
        try:
            # 2. Reconstruct Google Credentials from Supabase
            creds = Credentials(
                token=user.get('access_token'),
                refresh_token=user.get('refresh_token'),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
            )
            
            # 3. Connect to Gmail
            service = build('gmail', 'v1', credentials=creds)
            results = service.users().messages().list(userId='me', q="is:unread").execute()
            messages = results.get('messages', [])

            for msg in messages:
                # 4. Get Email Content
                txt = service.users().messages().get(userId='me', id=msg['id']).execute()
                snippet = txt.get('snippet')

                # 5. Ask OpenAI for a Professional Reply
                ai_response = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "You are ERNESCO, a professional executive assistant. Draft a polite reply to this email."},
                              {"role": "user", "content": snippet}]
                )
                reply_text = ai_response.choices[0].message.content

                # 6. Save Draft in Gmail
                service.users().drafts().create(userId='me', body={
                    'message': {
                        'threadId': msg['threadId'],
                        'raw': "" # You'd encode the reply_text here
                    }
                }).execute()
                
                # 7. Log Activity to Supabase
                supabase.table("activity_logs").insert({
                    "user_id": user['id'],
                    "subject": "New Email Replied",
                    "status": "drafted"
                }).execute()

        except Exception as e:
            print(f"Error processing user {user.get('id')}: {e}")

# Prepare the scheduler and job, but do NOT start it at import time.
scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_inboxes_and_reply, trigger="interval", minutes=10)


# --- Home route ---
@app.route('/')
def index():
    # Renders templates/index.html (Flask looks in the templates/ folder)
    return render_template('index.html')


# --- Privacy Route ---
@app.route('/privacy')
def privacy():
    return """
    <h1>Privacy Policy for ERNESCO</h1>
    <p>Last Updated: December 2025</p>
    <p>ERNESCO uses the <b>gmail.modify</b> scope to help you manage your inbox. 
    We only access your emails to generate AI drafts using OpenAI. 
    <b>We do not store your email content</b> on our servers, and we never sell your data.</p>
    <p>You can revoke access at any time via your Google Account settings.</p>
    <a href="/">Back to Home</a>
    """


# --- Start scheduler & run app ---
if __name__ == '__main__':
    # start the background job when running this file directly
    scheduler.start()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=os.getenv('FLASK_DEBUG', 'False') == 'True')
