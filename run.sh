#!/bin/bash

# Start the Gunicorn web server in the background
gunicorn --workers 1 --timeout 120 --log-level debug --bind 0.0.0.0:8080 app:app &

# REVISED: Explicitly set the PYTHONPATH for the Celery worker.
# This tells the worker to look for modules in the current directory (/app),
# which allows it to find your 'bot' module and resolves the ModuleNotFoundError.
PYTHONPATH=. celery -A celery_app.celery_app worker --loglevel=info --pool=solo
