# gunicorn_conf.py

# Bind to all interfaces on port 5000
bind = "0.0.0.0:5000"

# Only 1 worker process is probably enough for light usage
workers = 1