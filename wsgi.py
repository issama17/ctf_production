"""
wsgi.py — Point d'entrée pour le serveur de production (Gunicorn / Render.com)
Lancement : gunicorn wsgi:app
"""

from app import ApplicationCTF

# Instancier la plateforme et exposer l'objet Flask
_plateforme = ApplicationCTF()
app = _plateforme._app
