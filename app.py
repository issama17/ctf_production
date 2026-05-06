"""
Main Application Setup & Factory
Configures the Flask app and wires the OOP dependencies together.
"""
import os
import secrets
import logging
import base64
import cloudinary
from flask import Flask
from flask_login import LoginManager

from models import db, SteganoChallenge, CryptoChallenge
from repository import UserRepository, ChallengeRepository
from services import AuthService, CTFService
from routes import register_routes

def configure_cloudinary():
    """Configures the Cloudinary integration securely."""
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", ""),
        api_key=os.getenv("CLOUDINARY_API_KEY", ""),
        api_secret=os.getenv("CLOUDINARY_API_SECRET", ""),
        secure=True,
    )

def create_app():
    """
    Application Factory Pattern for Flask.
    Instantiates dependencies and configures the application.
    """
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

    # Secure Session Cookies
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    MAX_FILE_SIZE_MB = 5
    app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024

    # Database Configuration (PostgreSQL friendly for Railway)
    database_url = os.getenv("DATABASE_URL", "sqlite:///ctf_platform.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    configure_cloudinary()
    
    # ── Initialize Domain Repositories ──
    user_repo = UserRepository()
    challenge_repo = ChallengeRepository()

    # ── Initialize Domain Services ──
    url_base = os.getenv("CTF_URL", "http://127.0.0.1:5000")
    
    auth_service = AuthService(user_repo, url_base)
    ctf_service = CTFService(challenge_repo, user_repo)

    # ── Populate Challenges ──
    _initialize_challenges(ctf_service)

    # ── Configure Login Manager ──
    lm = LoginManager()
    lm.init_app(app)
    lm.login_view = "main.login"
    lm.login_message = "Connectez-vous pour accéder à cette page."
    lm.login_message_category = "warning"

    @lm.user_loader
    def load_user(uid):
        return auth_service.load_user(int(uid))

    register_routes(app, auth_service, ctf_service, user_repo)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s — %(message)s")

    # Create DB tables
    with app.app_context():
        db.create_all()

    return app

def _initialize_challenges(ctf_service: CTFService):
    """Initializes and registers standard challenges."""
    
    ctf_service.register_challenge(SteganoChallenge(
        identifier="stegano_01",
        title="Ombres Numériques",
        description=(
            "Une image anodine circule sur les réseaux. "
            "Les services de renseignement pensent qu'un message secret y est dissimulé. "
            "Votre mission : extraire le flag caché dans les données de ce fichier image. "
            "Le format attendu est <code>CTF{...}</code>."
        ),
        points=150, 
        difficulty="Moyen",
        flag_hash="8d5b82e063fabdcaeda624e1c207319982c3b47d8c13f232472a8225816fdf6a",
        image_file="image_piege.jpg", 
        tool_used="steghide"
    ))

    ctf_service.register_challenge(CryptoChallenge(
        identifier="crypto_01",
        title="César et la Légion",
        description=(
            "Un général a intercepté ce message ennemi. "
            "Il sait que le chiffrement utilisé est très ancien — "
            "une simple rotation de l'alphabet. "
            "Déchiffrez le message et soumettez le flag au format <code>CTF{...}</code>."
        ),
        points=100, 
        difficulty="Facile",
        flag_hash="1f72750f7aeb55383037ec1a768bc33c956eb8e27a2707940a53803cb2381d84",
        cipher_text="PGS{prfne_qrpbqr_irav_ivqv_ivpv}",
        hints=[
            "Ce chiffrement substitue chaque lettre par une autre décalée d'un nombre fixe de positions.",
            "Le chiffre de César utilise un décalage constant. Essayez tous les décalages de 1 à 25.",
            "Le décalage utilisé ici est 13 (ROT13). Appliquez ROT13 à chaque lettre du texte chiffré.",
        ],
        crypto_category="Chiffrement par substitution / César"
    ))

    xor_hex = "".join(f"{b ^ 0x42:02x}" for b in base64.b64encode(b"CTF{x0r_and_b4se64_master}"))
    ctf_service.register_challenge(CryptoChallenge(
        identifier="crypto_02",
        title="Double Masque",
        description=(
            "Un agent a encodé son message en deux étapes : "
            "d'abord un encodage Base64, puis un XOR avec la clé <code>0x42</code>. "
            "Le résultat a ensuite été converti en hexadécimal. "
            "Retrouvez le flag original. Format : <code>CTF{...}</code>."
        ),
        points=200, 
        difficulty="Moyen",
        flag_hash="ffd5b388f088758411891462fc6eddb0b5c0f5447fb5428b4523b0ec23f7590a",
        cipher_text=xor_hex,
        hints=[
            "Le texte est en hexadécimal. Convertissez-le d'abord en octets.",
            "Chaque octet a été XORé avec 0x42. Appliquez XOR(0x42) à chaque octet pour inverser l'opération.",
            "Après le XOR vous obtenez une chaîne Base64. Décodez-la pour obtenir le flag final.",
        ],
        crypto_category="XOR / Base64"
    ))

    ctf_service.register_challenge(CryptoChallenge(
        identifier="crypto_03",
        title="RSA Brisé",
        description=(
            "Un serveur utilise RSA avec des paramètres intentionnellement faibles. "
            "Clé publique : <code>n = 3233</code>, <code>e = 17</code>. "
            "Message chiffré : <code>c = 2790</code>. "
            "Factorisez n, calculez la clé privée d, puis déchiffrez c. "
            "Le flag est <code>CTF{m}</code> où m est le message en clair (entier décimal)."
        ),
        points=300, 
        difficulty="Difficile",
        flag_hash="b39aa6ea303b098db050c8cd97cd5101567acc0fd8d6289067e016133daf5d3c",
        cipher_text="n = 3233  |  e = 17  |  c = 2790",
        hints=[
            "n = 3233 est petit. Trouvez p et q tels que p x q = n en essayant des diviseurs.",
            "p = 61 et q = 53. Calculez phi(n) = (p-1)(q-1) = 3120, puis trouvez d tel que e*d = 1 (mod phi(n)).",
            "d = 2753. Déchiffrez : m = c^d mod n = 2201^2753 mod 3233. Le flag est CTF{m}.",
        ],
        crypto_category="RSA"
    ))

# Keep the ApplicationCTF interface for backward compatibility if wsgi.py is not updated yet
class ApplicationCTF:
    def __init__(self):
        self._app = create_app()

    def lancer(self, debug=False, port=5000):
        self._app.run(debug=debug, port=port)

if __name__ == "__main__":
    ApplicationCTF().lancer(debug=True)
