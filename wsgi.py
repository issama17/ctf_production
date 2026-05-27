"""
WSGI entry point for Gunicorn.
Instantiates the ApplicationCTF class and exposes the inner Flask app.
"""
import os
from dotenv import load_dotenv

# Load .env before the app factory runs so all os.getenv() calls see the values
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from app import ApplicationCTF

_instance = ApplicationCTF()
application = _instance.app   # Gunicorn looks for 'application' by convention

# Also expose as 'app' for compatibility
app = application
