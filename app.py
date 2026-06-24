"""
Configuration principale & Factory
Refonte selon les principes du cours (Partie 2) : Encapsulation et Organisation Objet.
"""
import os
import secrets
import logging
import base64
import cloudinary
from flask import Flask
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix

from models import db, DefiStegano, DefiCrypto, DefiWeb, ScoreClassique, ScoreDegressif, DefiReverse
from repository import UtilisateurRepository, DefiRepository
from services import ServiceAuth, ServiceCTF, AuditLogObservateur, BadgeObservateur
from routes import register_routes

class ConfigurateurCloudinary:
    @staticmethod
    def configurer():
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", ""),
            api_key=os.getenv("CLOUDINARY_API_KEY", ""),
            api_secret=os.getenv("CLOUDINARY_API_SECRET", ""),
            secure=True,
        )

class ApplicationCTF:
    """Classe principale représentant l'application (Patron Façade / Composition)."""
    def __init__(self):
        self.__app = Flask(__name__, template_folder='templates', static_folder='static')
        # Fix pour Railway/Vercel (HTTPS derrière un proxy)
        self.__app.wsgi_app = ProxyFix(self.__app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
        self.__db_initialized = False
        
        self.__configurer_app()
        self.__init_db()
        self.__init_services()
        self.__init_auth()
        self.__setup_lazy_db_init()

    def __setup_lazy_db_init(self):
        """Configure l'initialisation paresseuse de la base de données."""
        @self.__app.before_request
        def initialiser_base_si_necessaire():
            if not self.__db_initialized:
                self.__appliquer_migrations()

    def __appliquer_migrations(self):
        """Applique les migrations et crée les tables dans le contexte Flask (Paresseux)."""
        # 1. Tenter de détecter rapidement si la base est déjà initialisée (évite les écritures et locks au démarrage)
        try:
            from models import ChallengeModele
            # Si cette requête passe et qu'on a déjà des défis en base, on considère que c'est déjà initialisé.
            if db.session.query(ChallengeModele).first() is not None:
                self.__db_initialized = True
                return
        except Exception:
            # En cas d'erreur (ex: table inexistante), on doit impérativement faire un rollback
            # car PostgreSQL invalide toute la transaction courante en cas d'erreur de requête.
            try:
                db.session.rollback()
            except Exception:
                pass

        logging.getLogger("db_init").info("Initialisation de la base de données (Paresseuse/Lazy)...")
        with self.__app.app_context():
            try:
                db.create_all()
                self.__initialiser_defis()
                
                # Patch de schéma de base de données si nécessaire
                from sqlalchemy import text
                # 1. Renommer 'filiere' en 'statut' s'il existe
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE users RENAME COLUMN filiere TO statut"))
                        conn.commit()
                except Exception: pass
                
                # 2. Ajouter 'statut' s'il n'existe pas
                try: 
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE users ADD COLUMN statut VARCHAR(64) DEFAULT 'Étudiant'"))
                        conn.commit()
                except Exception: pass
                    
                # 3. Ajouter 'experience' s'il n'existe pas
                try: 
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE users ADD COLUMN experience VARCHAR(32) DEFAULT 'Débutant'"))
                        conn.commit()
                except Exception: pass
                
                self.__db_initialized = True
                logging.getLogger("db_init").info("Base de données initialisée et migrations appliquées avec succès.")
            except Exception as e:
                logging.getLogger("db_init").error(f"Erreur d'initialisation de la base de données : {e}")

    @property
    def app(self):
        """Expose l'instance Flask pour le serveur WSGI."""
        return self.__app

    def __configurer_app(self):
        self.__app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
        
        # Détection de l'environnement de production
        is_prod = os.getenv("FLASK_ENV") == "production"
        
        self.__app.config["SESSION_COOKIE_SECURE"] = is_prod
        self.__app.config["SESSION_COOKIE_HTTPONLY"] = True
        self.__app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        
        # Forcer le schéma HTTPS en production pour les redirections OAuth
        if is_prod:
            self.__app.config["PREFERRED_URL_SCHEME"] = "https"
            
        self.__app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
        
        database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("STORAGE_URL")
        
        # Fallback pour SQLite en gérant le système de fichiers en lecture seule de Vercel
        if not database_url:
            if os.getenv("VERCEL") == "1":
                database_url = "sqlite:////tmp/ctf_platform.db"
            else:
                database_url = "sqlite:///ctf_platform.db"
        elif database_url.startswith("sqlite:///"):
            # Si l'utilisateur a spécifié une SQLite locale relative mais qu'on est sur Vercel
            if os.getenv("VERCEL") == "1" and not database_url.startswith("sqlite:////tmp/"):
                database_url = "sqlite:////tmp/ctf_platform.db"

        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
            
        # Support automatique pour pg8000 si disponible (recommandé pour Vercel / serverless pour éviter C-extensions)
        if "postgresql" in database_url and not database_url.startswith("postgresql+"):
            try:
                import pg8000
                database_url = database_url.replace("postgresql://", "postgresql+pg8000://", 1)
                # pg8000 ne supporte pas certains paramètres de requête de Neon (channel_binding, sslmode, etc.) dans l'URI
                # On les retire car pg8000 gère le SSL nativement et automatiquement avec Neon
                if "?" in database_url:
                    database_url = database_url.split("?", 1)[0]
            except ImportError:
                pass

        self.__app.config["SQLALCHEMY_DATABASE_URI"] = database_url
        self.__app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        
        # Options d'optimisation du pool de connexion pour PostgreSQL en serverless
        if "postgresql" in database_url:
            self.__app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": 280,
                "pool_pre_ping": True,
            }

    def __init_db(self):
        db.init_app(self.__app)
        ConfigurateurCloudinary.configurer()

    def __init_services(self):
        self.__user_repo = UtilisateurRepository()
        self.__challenge_repo = DefiRepository()
        
        url_base = os.getenv("CTF_URL", "http://127.0.0.1:5000")
        self.__service_auth = ServiceAuth(self.__user_repo, url_base)
        self.__service_ctf = ServiceCTF(self.__challenge_repo, self.__user_repo)

        # Observer Pattern
        self.__service_ctf.attacher_observateur(AuditLogObservateur())
        self.__service_ctf.attacher_observateur(BadgeObservateur())

    def __init_auth(self):
        self.__lm = LoginManager()
        self.__lm.init_app(self.__app)
        self.__lm.login_view = "login"
        self.__lm.login_message = "Connectez-vous pour accéder à cette page."
        
        @self.__lm.user_loader
        def charger_utilisateur(uid):
            return self.__service_auth.charger_utilisateur(int(uid))

        # Configuration OAuth
        google_id = os.getenv("GOOGLE_CLIENT_ID")
        google_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        if google_id and google_secret:
            self.__oauth = OAuth(self.__app)
            self.__oauth.register(
                name='google',
                client_id=google_id,
                client_secret=google_secret,
                server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
                client_kwargs={'scope': 'openid email profile'}
            )
        else:
            self.__oauth = None
            logging.getLogger("oauth").warning("GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not configured. Google OAuth disabled.")

        register_routes(self.__app, self.__service_auth, self.__service_ctf, self.__user_repo, self.__oauth)

    def __initialiser_defis(self):
        s = self.__service_ctf
        
        # 1. Stegano
        s.enregistrer_defi(DefiStegano(
            identifiant="stegano_01",
            titre="Ombres Numériques",
            description=(
                "Une image anodine circule sur les réseaux. "
                "Les services de renseignement pensent qu'un message secret y est dissimulé. "
                "Votre mission : extraire le flag caché dans les données de ce fichier image. "
                "Le format attendu est <code>CTF{...}</code>."
            ),
            points=150, difficulte="Moyen",
            flag_hash="8d5b82e063fabdcaeda624e1c207319982c3b47d8c13f232472a8225816fdf6a",
            image_file="image_piege.jpg", tool_used="steghide",
            calculateur_score=ScoreDegressif()
        ))

        # 2. Crypto 1 (César)
        s.enregistrer_defi(DefiCrypto(
            identifiant="crypto_01", titre="César et la Légion",
            description=(
                "Un général a intercepté ce message ennemi. "
                "Il sait que le chiffrement utilisé est très ancien — "
                "une simple rotation de l'alphabet. "
                "Déchiffrez le message et soumettez le flag au format <code>CTF{...}</code>. "
                "<br><span class='text-warning'><i class='bi bi-exclamation-triangle'></i> Ce défi utilise un score dégressif ! Chaque tentative ratée coûte des points.</span>"
            ),
            points=100, difficulte="Facile",
            flag_hash="8e55004368f4afe9e8789e11a00db2fa143f05623dc222846f0de1b55d918aa5",
            cipher_text="PGS{prfne_qrpbqr_irav_ivqv_ivpv}",
            hints=[
                "Ce chiffrement substitue chaque lettre par une autre décalée d'un nombre fixe de positions.",
                "Le chiffre de César utilise un décalage constant. Essayez tous les décalages de 1 à 25.",
                "Le décalage utilisé ici est 13 (ROT13). Appliquez ROT13 à chaque lettre du texte chiffré.",
            ],
            crypto_category="Chiffrement par substitution / César", calculateur_score=ScoreDegressif()
        ))

        # 3. Crypto 2 (XOR)
        xor_hex = "1373100527712535212e7b2a202f10241b28103818161b721a70732a2171102e212c727f"
        s.enregistrer_defi(DefiCrypto(
            identifiant="crypto_02", titre="Double Masque",
            description=(
                "Un agent a encodé son message en deux étapes : "
                "d'abord un encodage Base64, puis un XOR avec la clé <code>0x42</code>. "
                "Le résultat a ensuite été converti en hexadécimal. "
                "Retrouvez le flag original. Format : <code>CTF{...}</code>. "
                "<br><span class='text-warning'><i class='bi bi-exclamation-triangle'></i> Ce défi utilise un score dégressif !</span>"
            ),
            points=200, difficulte="Moyen",
            flag_hash="ffd5b388f088758411891462fc6eddb0b5c0f5447fb5428b4523b0ec23f7590a",
            cipher_text=xor_hex,
            hints=[
                "Le texte est en hexadécimal. Convertissez-le d'abord en octets.",
                "Chaque octet a été XORé avec 0x42. Appliquez XOR(0x42) à chaque octet pour inverser l'opération.",
                "Après le XOR vous obtenez une chaîne Base64. Décodez-la pour obtenir le flag final.",
            ],
            crypto_category="XOR / Base64", calculateur_score=ScoreDegressif()
        ))

        # 4. Crypto 3 (RSA)
        s.enregistrer_defi(DefiCrypto(
            identifiant="crypto_03", titre="RSA Brisé",
            description=(
                "Un serveur utilise RSA avec des paramètres intentionnellement faibles. "
                "Clé publique : <code>n = 3233</code>, <code>e = 17</code>. "
                "Message chiffré : <code>c = 2790</code>. "
                "Factorisez n, calculez la clé privée d, puis déchiffrez c. "
                "Le flag est <code>CTF{m}</code> où m est le message en clair (entier décimal)."
            ),
            points=300, difficulte="Difficile",
            flag_hash="c5521b3eb3ee62692fe991a5dc2b6803cb15466cb915b4fd47ec7843639b9370",
            cipher_text="n = 3233  |  e = 17  |  c = 2790",
            hints=[
                "n = 3233 est petit. Trouvez p et q tels que p x q = n en essayant des diviseurs.",
                "p = 61 et q = 53. Calculez phi(n) = (p-1)(q-1) = 3120, puis trouvez d tel que e*d = 1 (mod phi(n)).",
                "d = 2753. Déchiffrez : m = c^d mod n = 2201^2753 mod 3233. Le flag est CTF{m}.",
            ],
            crypto_category="RSA", calculateur_score=ScoreDegressif()
        ))

        # 5. Web 1 (NULLSIG)
        s.enregistrer_defi(DefiWeb(
            identifiant="web_01", titre="NULLSIG — L'Algorithme Fantôme",
            description=(
                "Une alerte SOC signale un accès non autorisé à l'API interne de la société CorpVault. "
                "L'attaquant a réussi à atteindre l'endpoint <code>/api/admin/flag</code> "
                "sans connaître le secret JWT du serveur. "
                "<br><br>"
                "Votre mission : analyser le pack de preuves réseau fourni "
                "(logs d'accès, requêtes capturées, fragment de configuration serveur) "
                "et reconstituer la technique d'attaque utilisée. "
                "Le flag se trouve dans la réponse HTTP finale capturée par le SOC. "
                "<br><br>"
                "<span class='text-warning'>"
                "<i class='bi bi-exclamation-triangle'></i> "
                "Ce défi utilise un score dégressif ! Chaque tentative ratée coûte des points."
                "</span>"
            ),
            points=250, difficulte="Moyen",
            flag_hash="0ae102db73aed0c695e0e1fea835c051c3613497eb457aa353e3ba0d1ce22413",
            web_category="JWT / Authentification / Analyse forensique HTTP", 
            hints=[
                "Commencez par le fichier access_log.txt. Repérez la séquence temporelle.",
                "Lisez server_config_fragment.txt. JWT supporte un algorithme spécial sans signature.",
                "L'attaquant a utilisé l'attaque 'alg:none'. Le flag est dans flag_response.txt.",
            ],
            evidence_filename="nullsig_evidence_pack.zip", calculateur_score=ScoreDegressif()
        ))

        # 6. Web 2 (SQLi Lab)
        s.enregistrer_defi(DefiWeb(
            identifiant="sqli-login-bypass", titre="SQL Injection — Login Bypass",
            description=(
                "<div class='text-center mb-4'><img src='https://www.est.uae.ma/latest_assests/logo.png' style='height:80px; filter: drop-shadow(0 0 10px rgba(1,62,116,0.3));'></div>"
                "Une vulnérabilité SQL Injection a été détectée sur le portail "
                "académique de l'EST Tétouan. Le système d'authentification construit ses "
                "requêtes SQL par concaténation de chaînes — une erreur fatale.<br><br>"
                "Exploitez cette faille pour accéder au panneau d'administration et "
                "récupérez le flag caché dans la base de données.<br><br>"
                "<code class='text-pink'>🎯 Target : Portail EST Tétouan</code>"
            ),
            points=200, difficulte="Moyen",
            flag_hash=os.getenv("FLAG_SQLI_HASH", "470e9f47f3e0127e9e18f31262cda6b64ee10e3b4d85baab9335d58cc06f3939"),
            web_category="SQL Injection", hints=[], evidence_filename=None, lab_url="/lab/sqli/login"
        ))

        # 7. Reverse
        s.enregistrer_defi(DefiReverse(
            identifiant="rev_01", titre="Rev Challenge",
            description=(
                "Un binaire ELF 64-bit strippé (sans symboles) qui vous demande un flag. "
                "Le flag est encodé par XOR et décodé à la volée juste avant la comparaison. "
                "Votre mission : intercepter le flag décodé depuis le registre <code>%rsi</code> "
                "lors de l'instruction de comparaison (offset <code>0x1427</code> par rapport à la base)."
            ),
            points=300, difficulte="Moyen",
            flag_hash="58d295fbba51da4dbf961dfe64edd48dddd04175e881868c4edbda0cf1356ba8",
            binary_filename="chall", hints=[
                "Le binaire est PIE — l'adresse de base change à chaque exécution. Vérifiez <code>info proc mappings</code> dans GDB.",
                "La comparaison a lieu à l'offset <code>0x1427</code>. Placez un point d'arrêt (breakpoint) à cet endroit.",
                "Une fois le breakpoint atteint, inspectez <code>$rsi</code> avec <code>x/s $rsi</code> pour lire le flag décodé."
            ],
            calculateur_score=ScoreDegressif()
        ))

        # 8. Web 3 (NexusCorp)
        s.enregistrer_defi(DefiWeb(
            identifiant="web_nexuscorp", titre="NexusCorp — The Forgotten Artifact",
            description=(
                "L'équipe de sécurité de NexusCorp a découvert une ancienne page de maintenance "
                "supposée être hors service depuis des années. Cependant, des logs internes suggèrent "
                "qu'un employé nommé « reeeda » aurait laissé des traces d'identifiants opérationnels "
                "dans les métadonnées du processus de déploiement.<br><br>"
                "Votre mission est d'analyser les artefacts fournis, de remonter l'historique "
                "de déploiement et de pivoter à travers l'infrastructure de l'entreprise pour "
                "récupérer le flag d'accès maître.<br><br>"
                "Format : <code>CTF{...}</code>"
            ),
            points=350, difficulte="Difficile",
            flag_hash="536db512fef9426c36dad6b1b5da32e9f93ea2b0f13dc58b0aba4834db670ef6",
            web_category="OSINT / Web / DNS / Cryptographie", 
            hints=[
                "Inspectez les commentaires HTML pour trouver des traces de versions précédentes (commit hashes).",
                "Le 'note' dans la configuration de déploiement semble être de l'hexadécimal. Qu'est-ce qu'il indique ?",
                "Une fois que vous avez le domaine d'opérations, vérifiez ses enregistrements TXT. Le résultat final semble être encodé en Base64 et protégé par un XOR avec la clé 'darkweb_hunter'.",
            ],
            evidence_filename="nexuscorp_challenge.zip", calculateur_score=ScoreDegressif()
        ))

    def lancer(self, debug=True, port=5000):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s — %(message)s")
        with self.__app.app_context():
            db.create_all()
        self.__app.run(debug=debug, port=port)

if __name__ == "__main__":
    app_inst = ApplicationCTF()
    app_inst.lancer()
