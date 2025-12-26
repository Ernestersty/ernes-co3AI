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
            print(f"Error processing user {user['id']}: {e}")

# Start the background scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=scan_inboxes_and_reply, trigger="interval", minutes=10)
scheduler.start()

# --- ROUTES ---

@app.route('/')
def index():
    is_logged_in = 'credentials' in session
    return render_template('index.html', logged_in=is_logged_in)

@app.route('/login')
def login():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = os.getenv("REDIRECT_URI")
    auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['state'] = state
    return redirect(auth_url)

@app.route('/callback')
def callback():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, state=session['state'])
    flow.redirect_uri = os.getenv("REDIRECT_URI")
    flow.fetch_token(authorization_response=request.url)
    
    creds = flow.credentials
    # Save tokens to Supabase for the background worker
    supabase.table("profiles").upsert({
        "email": "fetch_from_google_api", 
        "access_token": creds.token,
        "refresh_token": creds.refresh_token
    }).execute()
    
    session['credentials'] = creds.to_json()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
        
