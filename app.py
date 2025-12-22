import os
from flask import Flask, render_template, request, jsonify, send_from_directory
from dotenv import load_dotenv
from supabase import create_client
import openai

load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION ---
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("CRITICAL: Supabase credentials missing!")

openai.api_key = OPENAI_KEY
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ROUTES ---

@app.route('/')
def index():
    """Landing Page: The registration/connect form."""
    # We show index.html but with no emails yet because they haven't "entered" the app
    return render_template('index.html', emails=[])

@app.route('/dashboard')
def dashboard():
    """Home Page: This is where users land after connecting."""
    try:
        # Fetching all logs from the 'activity_logs' table to show the feed
        response = supabase.table("activity_logs").select("*").order("created_at", desc=True).execute()
        return render_template('index.html', emails=response.data)
    except Exception as e:
        print(f"Dashboard Error: {e}")
        return render_template('index.html', emails=[])

@app.route('/pending-actions')
def pending_actions():
    """Activity Page: Shows the progress of AI processing."""
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
        return "Database Connection Error. Check Render Logs."

@app.route('/settings')
def settings():
    """Settings Page: Placeholder for user preferences."""
    # You can create a settings.html later. For now, we'll use a simple message.
    return "<h1>Settings Page</h1><p>User preferences and API configurations coming soon.</p><a href='/dashboard'>Back to Dashboard</a>"

# Serve other static files
@app.route('/<path:filename>')
def other_pages(filename):
    if filename.endswith('.html'):
        return render_template(filename)
    return 'Not Found', 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
