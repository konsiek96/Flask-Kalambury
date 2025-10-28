#!/bin/sh
# wait for DB (simple loop) - optional: you can use better wait-for script
sleep 1
# Run DB migrations? (not implemented here) - just start app
exec gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5000 "run:app"
