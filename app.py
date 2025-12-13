from flask import Flask, send_from_directory
import os

# Expose 'app' for gunicorn: `gunicorn app:app`
app = Flask(__name__, static_folder='.', static_url_path='')

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# Serve other static/html files in repo root (e.g., connect_email.html, receive_emails.html)
@app.route('/<path:filename>')
def static_files(filename):
    # don't serve hidden files
    if os.path.exists(filename) and not filename.startswith('.'):
        return send_from_directory('.', filename)
    return 'Not Found', 404

if __name__ == '__main__':
    # Use PORT env var provided by Render; fallback to 5000 locally
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
