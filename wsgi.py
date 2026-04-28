"""
Point d'entrée WSGI pour Railway + Gunicorn.
Commande de démarrage : gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2
"""
from app import ApplicationCTF

_instance = ApplicationCTF()
app = _instance._app

if __name__ == "__main__":
    app.run()
