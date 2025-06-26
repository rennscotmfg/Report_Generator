# gunicorn_conf.py

# Bind to all interfaces on port 5000
bind = "0.0.0.0:5000"

workers = 2

threads = 4

worker_class = "gthread"

worker_tmp_dir = "/dev/shm"