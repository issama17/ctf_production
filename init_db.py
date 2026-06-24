"""
Helper script to initialize the database schema and populate challenges.
This can be run locally or in production environments.
"""
import os
import logging
from dotenv import load_dotenv

# Load .env variables
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from app import ApplicationCTF
from models import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s — %(message)s")
logger = logging.getLogger("init_db")

def init():
    logger.info("Initializing CTF platform database...")
    app_inst = ApplicationCTF()
    app = app_inst.app

    with app.app_context():
        try:
            logger.info("Creating all database tables...")
            db.create_all()
            
            # Seeding challenges
            logger.info("Populating challenges data...")
            app_inst._ApplicationCTF__initialiser_defis()
            
            # Applying schema migrations/patches
            logger.info("Checking schema migrations...")
            from sqlalchemy import text
            
            # 1. Renommer 'filiere' en 'statut' s'il existe
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE users RENAME COLUMN filiere TO statut"))
                    conn.commit()
                    logger.info("Renamed 'filiere' to 'statut' if existed.")
            except Exception: pass
            
            # 2. Ajouter 'statut' s'il n'existe pas
            try: 
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN statut VARCHAR(64) DEFAULT 'Étudiant'"))
                    conn.commit()
                    logger.info("Added column 'statut' if missing.")
            except Exception: pass
                
            # 3. Ajouter 'experience' s'il n'existe pas
            try: 
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN experience VARCHAR(32) DEFAULT 'Débutant'"))
                    conn.commit()
                    logger.info("Added column 'experience' if missing.")
            except Exception: pass
            
            logger.info("Database initialization completed successfully!")
        except Exception as e:
            logger.error(f"Error during database initialization: {e}")

if __name__ == "__main__":
    init()
