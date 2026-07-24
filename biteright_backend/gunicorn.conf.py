import os

# Automatically bind Gunicorn to Render's dynamic PORT on 0.0.0.0
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"
workers = 1
threads = 2
timeout = 120
loglevel = "info"
