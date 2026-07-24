import os

# Automatically bind Gunicorn to Render's dynamic PORT on 0.0.0.0 with 4 threads for concurrent requests
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"
workers = 1
threads = 4
timeout = 120
loglevel = "info"
