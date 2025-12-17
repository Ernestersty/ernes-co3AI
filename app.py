import os
from flask import Flask, send_from_directory, render_template, request, jsonify
from dotenv import load_dotenv
from supabase import create_client
import openai

# Load environment variables (from .env file locally, or Render settings in production)
load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION & SAFETY CHECKS ---
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

# This prevents the "Exception on / [GET]" if keys are missing
if not SUPABASE_URL or not SUPABASE_KEY:
    print("CRITICAL: Supabase credentials missing! Check Render Environment Variables.")

openai.api_key = OPENAI_KEY
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- DATABASE & AI LOGIC ---

def save_email(sender, subject, body, user_id):
    """Saves a new email to Supabase and marks it as processing."""
    return supabase.table("activity_logs").insert({
        "user_owner": user_id,
        "sender_name": sender,
        "original_email": body,
        "status": "processing"
    }).execute()

def generate_reply(email_text, tone="Professional", language="English"):
    """Uses OpenAI to generate a draft response."""
    if not openai.api_key:
        return "AI Error: OpenAI Key not configured."
        
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"You are a professional email assistant. Reply in a {tone} tone and use {language}."},
            {"role": "user", "content": email_text}
        ]
    )
    return response.choices[0].message.content

# --- ROUTES ---

@app.route('/')
def index():
    """Main Dashboard: Fetches all emails from Supabase and shows them on index.html"""
    try:
        # Fetch data for the main dashboard
        data = supabase.table("activity_logs").select("*").order("created_at", desc=True).execute()
        return render_template('index.html', emails=data.data)
    except Exception as e:
        print(f"Dashboard Error: {e}")
        # Return empty list if database fails so the page doesn't crash
        return render_template('index.html', emails=[])

@app.route('/pending-actions')
def pending_actions():
    """Status Page: Shows progress bar and emails still being processed."""
    try:
        response = supabase.table("activity_logs").select("*").execute()
        all_logs = response.data
        
        total_count = len(all_logs)
        working_on_list = [log for log in all_logs if log.get('status') == 'processing']
        completed_count = len([log for log in all_logs if log.get('status') == 'replied'])
        
        percentage = 0
        if total_count > 0:
            percentage = int((completed_count / total_count) * 100)

        return render_template('pending_actions.html', 
                               emails=working_on_list, 
                               count=total_count, 
                               working_on=len(working_on_list), 
                               percentage=percentage)
    except Exception as e:
        print(f"Pending Actions Error: {e}")
        return "Database Connection Error. Check logs."

# Serve other static files (Settings, etc.)
@app.route('/<path:filename>')
def static_files(filename):
    if os.path.exists(filename) and not filename.startswith('.'):
        if filename.endswith('.html'):
            return render_template(filename)
        return send_from_directory('.', filename)
    return 'Not Found', 404

# --- START SERVER ---

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # debug=False for production/Render
    app.run(host='0.0.0.0', port=port, debug=True)

