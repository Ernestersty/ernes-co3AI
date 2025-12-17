import os
from flask import Flask, send_from_directory, render_template, request, jsonify
from dotenv import load_dotenv
from supabase import create_client
import openai

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')

# Configuration
openai.api_key = os.getenv("OPENAI_API_KEY")
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

# --- DATABASE & AI LOGIC ---

def save_email(sender, subject, body, user_id):
    # We set status to 'processing' initially to show the spinner in UI
    return supabase.table("activity_logs").insert({
        "user_owner": user_id,
        "sender_name": sender,
        "original_email": body,
        "status": "processing"
    }).execute()

def generate_reply(email_text, tone="Professional", language="English"):
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
    # Fetch data for the main dashboard
    data = supabase.table("activity_logs").select("*").order("created_at", desc=True).execute()
    return render_template('index.html', emails=data.data)

@app.route('/pending-actions')
def pending_actions():
    # 1. Fetch all activity for the user
    # In a real app, replace 'user@example.com' with the logged-in user's email
    response = supabase.table("activity_logs").select("*").execute()
    all_logs = response.data
    
    total_count = len(all_logs)
    working_on_list = [log for log in all_logs if log.get('status') == 'processing']
    completed_count = len([log for log in all_logs if log.get('status') == 'replied'])
    
    # 2. Calculate Percentage
    percentage = 0
    if total_count > 0:
        percentage = int((completed_count / total_count) * 100)

    return render_template('pending_actions.html', 
                           emails=working_on_list, 
                           count=total_count, 
                           working_on=len(working_on_list), 
                           percentage=percentage)

# Serve other static/html files (Settings, etc.)
@app.route('/<path:filename>')
def static_files(filename):
    if os.path.exists(filename) and not filename.startswith('.'):
        # If it's an HTML file, we use render_template so Jinja2 works
        if filename.endswith('.html'):
            return render_template(filename)
        return send_from_directory('.', filename)
    return 'Not Found', 404

# --- START SERVER ---

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # debug=True is great for development, turn off for production
    app.run(host='0.0.0.0', port=port, debug=True)
