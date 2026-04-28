"""
Plateforme CTF — v4 avec PostgreSQL + Cloudinary
Architecture : 100% Programmation Orientée Objet (POO)
Nouvelles fonctionnalités : Photo de profil (Cloudinary) + PostgreSQL persistant
"""

from flask import Flask, render_template, request, jsonify, send_from_directory, \
                  redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, \
                        login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from abc import ABC, abstractmethod
import hashlib, os, logging, secrets, smtplib, base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import cloudinary
import cloudinary.uploader
import cloudinary.api


# ══════════════════════════════════════════════════════
#  CONFIGURATION CLOUDINARY
# ══════════════════════════════════════════════════════

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", ""),
    api_key=os.getenv("CLOUDINARY_API_KEY", ""),
    api_secret=os.getenv("CLOUDINARY_API_SECRET", ""),
    secure=True,
)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILE_SIZE_MB = 5


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ══════════════════════════════════════════════════════
#  INITIALISATION SQLALCHEMY (partagée)
# ══════════════════════════════════════════════════════

db_sql = SQLAlchemy()


# ══════════════════════════════════════════════════════
#  MODÈLES SQLALCHEMY
# ══════════════════════════════════════════════════════

class UtilisateurModel(db_sql.Model):
    """Modèle SQLAlchemy pour la table utilisateurs (PostgreSQL)."""
    __tablename__ = "utilisateurs"

    id               = db_sql.Column(db_sql.Integer, primary_key=True, autoincrement=True)
    nom_utilisateur  = db_sql.Column(db_sql.String(64), unique=True, nullable=False)
    email            = db_sql.Column(db_sql.String(255), unique=True, nullable=False)
    mot_de_passe     = db_sql.Column(db_sql.String(256), nullable=False)
    score            = db_sql.Column(db_sql.Integer, default=0)
    confirme         = db_sql.Column(db_sql.Boolean, default=False)
    token_confirm    = db_sql.Column(db_sql.String(256), nullable=True)
    token_expiry     = db_sql.Column(db_sql.String(64), nullable=True)
    date_inscription = db_sql.Column(db_sql.String(64), default=lambda: datetime.utcnow().isoformat())
    # NEW: URL persistante de la photo de profil (stockée sur Cloudinary)
    profile_pic      = db_sql.Column(db_sql.String(512), nullable=True, default=None)

    soumissions = db_sql.relationship("SoumissionModel", backref="utilisateur", lazy=True)


class SoumissionModel(db_sql.Model):
    """Modèle SQLAlchemy pour la table soumissions."""
    __tablename__ = "soumissions"

    id          = db_sql.Column(db_sql.Integer, primary_key=True, autoincrement=True)
    user_id     = db_sql.Column(db_sql.Integer, db_sql.ForeignKey("utilisateurs.id"), nullable=False)
    defi_id     = db_sql.Column(db_sql.String(64), nullable=False)
    succes      = db_sql.Column(db_sql.Boolean, nullable=False)
    date_soumis = db_sql.Column(db_sql.String(64), default=lambda: datetime.utcnow().isoformat())


# ══════════════════════════════════════════════════════
#  COUCHE DONNÉES — BaseDeDonnees (PostgreSQL via SQLAlchemy)
# ══════════════════════════════════════════════════════

class BaseDeDonnees:
    """Couche d'accès aux données utilisant SQLAlchemy + PostgreSQL."""

    def creer_utilisateur(self, nom, email, mdp_hash, token, expiry) -> bool:
        try:
            u = UtilisateurModel(
                nom_utilisateur=nom, email=email, mot_de_passe=mdp_hash,
                token_confirm=token, token_expiry=expiry
            )
            db_sql.session.add(u)
            db_sql.session.commit()
            return True
        except Exception:
            db_sql.session.rollback()
            return False

    def obtenir_par_email(self, email):
        return UtilisateurModel.query.filter_by(email=email).first()

    def obtenir_par_id(self, uid):
        return db_sql.session.get(UtilisateurModel, uid)

    def obtenir_par_token(self, token):
        return UtilisateurModel.query.filter_by(token_confirm=token).first()

    def confirmer_utilisateur(self, uid) -> None:
        u = db_sql.session.get(UtilisateurModel, uid)
        if u:
            u.confirme = True
            u.token_confirm = None
            db_sql.session.commit()

    def ajouter_score(self, uid, points) -> None:
        u = db_sql.session.get(UtilisateurModel, uid)
        if u:
            u.score = (u.score or 0) + points
            db_sql.session.commit()

    def a_deja_resolu(self, uid, defi_id) -> bool:
        return SoumissionModel.query.filter_by(
            user_id=uid, defi_id=defi_id, succes=True
        ).first() is not None

    def enregistrer_soumission(self, uid, defi_id, succes) -> None:
        s = SoumissionModel(user_id=uid, defi_id=defi_id, succes=bool(succes))
        db_sql.session.add(s)
        db_sql.session.commit()

    def historique_soumissions(self, uid) -> list:
        rows = (
            SoumissionModel.query
            .filter_by(user_id=uid)
            .order_by(SoumissionModel.date_soumis.desc())
            .limit(20)
            .all()
        )
        return [{"defi_id": r.defi_id, "succes": r.succes, "date_soumis": r.date_soumis} for r in rows]

    def mettre_a_jour_photo(self, uid, url: str) -> None:
        """Met à jour l'URL Cloudinary de la photo de profil."""
        u = db_sql.session.get(UtilisateurModel, uid)
        if u:
            u.profile_pic = url
            db_sql.session.commit()


# ══════════════════════════════════════════════════════
#  COUCHE DOMAINE — Utilisateur
# ══════════════════════════════════════════════════════

class Utilisateur(UserMixin):
    def __init__(self, row: UtilisateurModel):
        self.id               = row.id
        self.nom_utilisateur  = row.nom_utilisateur
        self.email            = row.email
        self._mdp_hash        = row.mot_de_passe
        self.score            = row.score
        self.confirme         = bool(row.confirme)
        self.date_inscription = row.date_inscription
        self.profile_pic      = row.profile_pic   # URL Cloudinary ou None

    def verifier_mot_de_passe(self, mdp) -> bool:
        return hashlib.sha256(mdp.encode()).hexdigest() == self._mdp_hash

    @staticmethod
    def hasher_mdp(mdp) -> str:
        return hashlib.sha256(mdp.encode()).hexdigest()

    def get_id(self) -> str:
        return str(self.id)


# ══════════════════════════════════════════════════════
#  SERVICE EMAIL
# ══════════════════════════════════════════════════════

class ServiceEmail:
    def __init__(self, smtp_host, smtp_port, expediteur, mdp_smtp):
        self.__host = smtp_host; self.__port = smtp_port
        self.__expediteur = expediteur; self.__mdp = mdp_smtp
        self._logger = logging.getLogger(self.__class__.__name__)

    def envoyer_confirmation(self, destinataire, nom, lien) -> bool:
        corps_html = f"""<div style="font-family:monospace;background:#050810;color:#c8d8f0;padding:30px;">
          <h2 style="color:#00ff88;">CTF_LAB</h2><p>Bonjour <strong>{nom}</strong>,</p>
          <a href="{lien}" style="display:inline-block;margin:20px 0;padding:12px 24px;background:#00ff88;color:#000;">Confirmer</a>
        </div>"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "CTF_LAB — Confirmez votre adresse email"
        msg["From"] = self.__expediteur; msg["To"] = destinataire
        msg.attach(MIMEText(corps_html, "html"))
        try:
            with smtplib.SMTP_SSL(self.__host, self.__port) as srv:
                srv.login(self.__expediteur, self.__mdp)
                srv.sendmail(self.__expediteur, destinataire, msg.as_string())
            return True
        except Exception as e:
            self._logger.error(f"Email error: {e}"); return False


# ══════════════════════════════════════════════════════
#  GESTIONNAIRE AUTH
# ══════════════════════════════════════════════════════

class GestionnaireAuth:
    def __init__(self, db, service_email, url_base):
        self.__db = db; self.__service_email = service_email
        self.__url_base = url_base
        self._logger = logging.getLogger(self.__class__.__name__)

    def inscrire(self, nom, email, mdp) -> dict:
        if len(nom) < 3:
            return {"succes": False, "message": "Le nom doit faire au moins 3 caractères."}
        if len(mdp) < 6:
            return {"succes": False, "message": "Le mot de passe doit faire au moins 6 caractères."}
        if "@" not in email:
            return {"succes": False, "message": "Email invalide."}
        mdp_hash = Utilisateur.hasher_mdp(mdp)
        ok = self.__db.creer_utilisateur(nom, email, mdp_hash, "confirmed", "confirmed")
        if not ok:
            return {"succes": False, "message": "Email ou nom d'utilisateur déjà utilisé."}
        row = self.__db.obtenir_par_email(email)
        if row:
            self.__db.confirmer_utilisateur(row.id)
        return {"succes": True, "message": "Inscription réussie ! Vous pouvez vous connecter."}

    def confirmer_email(self, token) -> dict:
        row = self.__db.obtenir_par_token(token)
        if not row:
            return {"succes": False, "message": "Lien invalide ou déjà utilisé."}
        expiry = datetime.fromisoformat(row.token_expiry)
        if datetime.utcnow() > expiry:
            return {"succes": False, "message": "Lien expiré."}
        self.__db.confirmer_utilisateur(row.id)
        return {"succes": True, "message": "Email confirmé !"}

    def connecter(self, email, mdp) -> dict:
        row = self.__db.obtenir_par_email(email)
        if not row:
            return {"succes": False, "message": "Email ou mot de passe incorrect."}
        user = Utilisateur(row)
        if not user.verifier_mot_de_passe(mdp):
            return {"succes": False, "message": "Email ou mot de passe incorrect."}
        if not user.confirme:
            return {"succes": False, "message": "Compte non confirmé."}
        return {"succes": True, "utilisateur": user}

    def charger_utilisateur(self, uid):
        row = self.__db.obtenir_par_id(uid)
        return Utilisateur(row) if row else None


# ══════════════════════════════════════════════════════
#  COUCHE DOMAINE CTF
# ══════════════════════════════════════════════════════

class DefiCTF(ABC):
    def __init__(self, titre, description, points, difficulte):
        self._titre = titre; self._description = description
        self._points = points; self._difficulte = difficulte
        self._resolu = False

    @property
    def titre(self): return self._titre
    @property
    def description(self): return self._description
    @property
    def points(self): return self._points
    @property
    def difficulte(self): return self._difficulte
    @property
    def resolu(self): return self._resolu

    @abstractmethod
    def verifier_flag(self, tentative: str) -> bool: pass
    @abstractmethod
    def obtenir_indice(self) -> str: pass

    def marquer_resolu(self): self._resolu = True


class ValidateurFlag:
    def __init__(self, flag_secret):
        self.__hash_secret = hashlib.sha256(flag_secret.encode()).hexdigest()
        self.__tentatives = 0
        self.__MAX = 10

    @property
    def tentatives(self): return self.__tentatives
    @property
    def bloque(self): return self.__tentatives >= self.__MAX

    def valider(self, tentative) -> bool:
        if self.bloque: return False
        self.__tentatives += 1
        return hashlib.sha256(tentative.strip().encode()).hexdigest() == self.__hash_secret


class DefiStegano(DefiCTF):
    def __init__(self, titre, description, points, flag_secret, fichier_image, outil_cache):
        super().__init__(titre, description, points, "Moyen")
        self.__validateur = ValidateurFlag(flag_secret)
        self._fichier_image = fichier_image; self._outil_cache = outil_cache

    @property
    def fichier_image(self): return self._fichier_image
    @property
    def outil_cache(self): return self._outil_cache
    @property
    def tentatives(self): return self.__validateur.tentatives
    @property
    def bloque(self): return self.__validateur.bloque

    def verifier_flag(self, tentative) -> bool:
        if not tentative.startswith("CTF{") or not tentative.endswith("}"): return False
        correct = self.__validateur.valider(tentative)
        if correct: self.marquer_resolu()
        return correct

    def obtenir_indice(self) -> str:
        n = self.__validateur.tentatives
        if n < 3: return "Le secret se cache dans les pixels..."
        if n < 6: return f"Essayez d'extraire avec {self._outil_cache}."
        return f"Commande : {self._outil_cache} extract -sf image.jpg -p [mot_de_passe]"

    def to_dict(self) -> dict:
        return {
            "titre": self._titre, "description": self._description,
            "points": self._points, "difficulte": self._difficulte,
            "fichier": self._fichier_image, "outil": self._outil_cache,
            "resolu": self._resolu, "tentatives": self.__validateur.tentatives,
            "bloque": self.__validateur.bloque, "type": "stegano",
        }


class DefiCrypto(DefiCTF):
    def __init__(self, titre, description, points, difficulte,
                 flag_secret, texte_chiffre, indices, categorie_crypto):
        super().__init__(titre, description, points, difficulte)
        self.__validateur = ValidateurFlag(flag_secret)
        self._texte_chiffre = texte_chiffre
        self._indices = indices
        self._categorie_crypto = categorie_crypto

    @property
    def texte_chiffre(self): return self._texte_chiffre
    @property
    def categorie_crypto(self): return self._categorie_crypto
    @property
    def tentatives(self): return self.__validateur.tentatives
    @property
    def bloque(self): return self.__validateur.bloque

    def verifier_flag(self, tentative) -> bool:
        if not tentative.startswith("CTF{") or not tentative.endswith("}"): return False
        correct = self.__validateur.valider(tentative)
        if correct: self.marquer_resolu()
        return correct

    def obtenir_indice(self) -> str:
        if not self._indices: return ""
        idx = min(self.__validateur.tentatives // 3, len(self._indices) - 1)
        return self._indices[idx]

    def to_dict(self) -> dict:
        return {
            "titre": self._titre, "description": self._description,
            "points": self._points, "difficulte": self._difficulte,
            "texte_chiffre": self._texte_chiffre,
            "categorie_crypto": self._categorie_crypto,
            "resolu": self._resolu, "tentatives": self.__validateur.tentatives,
            "bloque": self.__validateur.bloque, "type": "crypto",
        }


# ══════════════════════════════════════════════════════
#  GESTIONNAIRE CTF
# ══════════════════════════════════════════════════════

class GestionnaireCTF:
    def __init__(self):
        self._defis = {}
        self._logger = logging.getLogger(self.__class__.__name__)

    def enregistrer_defi(self, identifiant, defi): self._defis[identifiant] = defi
    def obtenir_defi(self, identifiant): return self._defis.get(identifiant)

    def soumettre_flag(self, identifiant, tentative, db, uid) -> dict:
        defi = self.obtenir_defi(identifiant)
        if not defi:
            return {"succes": False, "message": "Défi introuvable.", "code": 404}
        if db.a_deja_resolu(uid, identifiant):
            return {"succes": True, "message": "Vous avez déjà résolu ce défi !", "points": 0, "deja_resolu": True, "code": 200}
        if defi.bloque:
            return {"succes": False, "message": "Trop de tentatives.", "code": 429}
        correct = defi.verifier_flag(tentative)
        db.enregistrer_soumission(uid, identifiant, correct)
        if correct:
            db.ajouter_score(uid, defi.points)
            return {"succes": True, "message": f"Félicitations ! +{defi.points} points !", "points": defi.points, "code": 200}
        return {"succes": False, "message": "Flag incorrect. Continuez à chercher...",
                "indice": defi.obtenir_indice(), "tentatives": defi.tentatives, "code": 200}

    def liste_defis(self):
        return [{"id": k, **v.to_dict()} for k, v in self._defis.items()]


# ══════════════════════════════════════════════════════
#  APPLICATION FLASK
# ══════════════════════════════════════════════════════

class ApplicationCTF:

    def __init__(self):
        self._app = Flask(__name__)
        self._app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

        # ── Configuration base de données PostgreSQL ──
        # Sur Railway : DATABASE_URL est fourni automatiquement.
        # SQLAlchemy nécessite "postgresql://" et non "postgres://".
        database_url = os.getenv("DATABASE_URL", "sqlite:///ctf_platform.db")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        self._app.config["SQLALCHEMY_DATABASE_URI"] = database_url
        self._app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        self._app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024

        # Initialise SQLAlchemy avec l'app
        db_sql.init_app(self._app)

        self._service_email = ServiceEmail(
            smtp_host="smtp.gmail.com", smtp_port=465,
            expediteur=os.getenv("CTF_EMAIL", "votre.email@gmail.com"),
            mdp_smtp=os.getenv("CTF_EMAIL_MDP", "votre_mot_de_passe_app"),
        )
        self._url_base = os.getenv("CTF_URL", "http://127.0.0.1:5000")
        self._db = BaseDeDonnees()
        self._auth = GestionnaireAuth(self._db, self._service_email, self._url_base)
        self._gestionnaire = GestionnaireCTF()

        with self._app.app_context():
            db_sql.create_all()   # Crée les tables si elles n'existent pas

        self._configurer_login_manager()
        self._initialiser_defis()
        self._enregistrer_routes()
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s [%(name)s] %(levelname)s — %(message)s")

    def _configurer_login_manager(self):
        lm = LoginManager()
        lm.init_app(self._app)
        lm.login_view = "login"
        lm.login_message = "Connectez-vous pour accéder à cette page."
        lm.login_message_category = "warning"

        @lm.user_loader
        def charger_utilisateur(uid):
            return self._auth.charger_utilisateur(int(uid))

    def _initialiser_defis(self):
        self._gestionnaire.enregistrer_defi("stegano_01", DefiStegano(
            titre="Ombres Numériques",
            description=(
                "Une image anodine circule sur les réseaux. "
                "Les services de renseignement pensent qu'un message secret y est dissimulé. "
                "Votre mission : extraire le flag caché dans les données de ce fichier image. "
                "Le format attendu est <code>CTF{...}</code>."
            ),
            points=150, flag_secret="CTF{st3g4n0_m4st3r_2024}",
            fichier_image="image_piege.jpg", outil_cache="steghide",
        ))

        self._gestionnaire.enregistrer_defi("crypto_01", DefiCrypto(
            titre="César et la Légion",
            description=(
                "Un général a intercepté ce message ennemi. "
                "Il sait que le chiffrement utilisé est très ancien — "
                "une simple rotation de l'alphabet. "
                "Déchiffrez le message et soumettez le flag au format <code>CTF{...}</code>."
            ),
            points=100, difficulte="Facile",
            flag_secret="CTF{cesar_decode_veni_vidi_vici}",
            texte_chiffre="PGS{prfne_qrpbqr_irav_ivqv_ivpv}",
            indices=[
                "Ce chiffrement substitue chaque lettre par une autre décalée d'un nombre fixe de positions.",
                "Le chiffre de César utilise un décalage constant. Essayez tous les décalages de 1 à 25.",
                "Le décalage utilisé ici est 13 (ROT13). Appliquez ROT13 à chaque lettre du texte chiffré.",
            ],
            categorie_crypto="Chiffrement par substitution / César",
        ))

        xor_hex = "".join(f"{b ^ 0x42:02x}" for b in base64.b64encode(b"CTF{x0r_and_b4se64_master}"))
        self._gestionnaire.enregistrer_defi("crypto_02", DefiCrypto(
            titre="Double Masque",
            description=(
                "Un agent a encodé son message en deux étapes : "
                "d'abord un encodage Base64, puis un XOR avec la clé <code>0x42</code>. "
                "Le résultat a ensuite été converti en hexadécimal. "
                "Retrouvez le flag original. Format : <code>CTF{...}</code>."
            ),
            points=200, difficulte="Moyen",
            flag_secret="CTF{x0r_and_b4se64_master}",
            texte_chiffre=xor_hex,
            indices=[
                "Le texte est en hexadécimal. Convertissez-le d'abord en octets.",
                "Chaque octet a été XORé avec 0x42. Appliquez XOR(0x42) à chaque octet pour inverser l'opération.",
                "Après le XOR vous obtenez une chaîne Base64. Décodez-la pour obtenir le flag final.",
            ],
            categorie_crypto="XOR / Base64",
        ))

        self._gestionnaire.enregistrer_defi("crypto_03", DefiCrypto(
            titre="RSA Brisé",
            description=(
                "Un serveur utilise RSA avec des paramètres intentionnellement faibles. "
                "Clé publique : <code>n = 3233</code>, <code>e = 17</code>. "
                "Message chiffré : <code>c = 2790</code>. "
                "Factorisez n, calculez la clé privée d, puis déchiffrez c. "
                "Le flag est <code>CTF{m}</code> où m est le message en clair (entier décimal)."
            ),
            points=300, difficulte="Difficile",
            flag_secret="CTF{65}",
            texte_chiffre="n = 3233  |  e = 17  |  c = 2790",
            indices=[
                "n = 3233 est petit. Trouvez p et q tels que p x q = n en essayant des diviseurs.",
                "p = 61 et q = 53. Calculez phi(n) = (p-1)(q-1) = 3120, puis trouvez d tel que e*d = 1 (mod phi(n)).",
                "d = 2753. Déchiffrez : m = c^d mod n = 2201^2753 mod 3233. Le flag est CTF{m}.",
            ],
            categorie_crypto="RSA",
        ))

    def _enregistrer_routes(self):
        app = self._app

        @app.route("/")
        def index():
            defis = self._gestionnaire.liste_defis()
            return render_template("index.html", defis=defis)

        @app.route("/inscription", methods=["GET", "POST"])
        def inscription():
            if current_user.is_authenticated:
                return redirect(url_for("index"))
            if request.method == "POST":
                res = self._auth.inscrire(
                    request.form.get("nom", "").strip(),
                    request.form.get("email", "").strip().lower(),
                    request.form.get("mdp", ""),
                )
                flash(res["message"], "success" if res["succes"] else "danger")
                if res["succes"]:
                    return redirect(url_for("login"))
            return render_template("inscription.html")

        @app.route("/confirmer/<token>")
        def confirmer(token):
            res = self._auth.confirmer_email(token)
            flash(res["message"], "success" if res["succes"] else "danger")
            return redirect(url_for("login"))

        @app.route("/login", methods=["GET", "POST"])
        def login():
            if current_user.is_authenticated:
                return redirect(url_for("index"))
            if request.method == "POST":
                res = self._auth.connecter(
                    request.form.get("email", "").strip().lower(),
                    request.form.get("mdp", ""),
                )
                if res["succes"]:
                    login_user(res["utilisateur"], remember=True)
                    return redirect(request.args.get("next") or url_for("index"))
                flash(res["message"], "danger")
            return render_template("login.html")

        @app.route("/deconnexion")
        @login_required
        def deconnexion():
            logout_user()
            flash("Déconnexion réussie.", "info")
            return redirect(url_for("login"))

        @app.route("/profil")
        @login_required
        def profil():
            historique = self._db.historique_soumissions(current_user.id)
            return render_template("profil.html", historique=historique)

        # ── NOUVELLE ROUTE : Paramètres du profil (photo) ──────────────────
        @app.route("/profil/parametres", methods=["GET", "POST"])
        @login_required
        def parametres_profil():
            """Permet à l'utilisateur de changer sa photo de profil via Cloudinary."""
            if request.method == "POST":
                if "photo" not in request.files:
                    flash("Aucun fichier sélectionné.", "danger")
                    return redirect(url_for("parametres_profil"))

                fichier = request.files["photo"]
                if fichier.filename == "":
                    flash("Aucun fichier sélectionné.", "danger")
                    return redirect(url_for("parametres_profil"))

                if not allowed_file(fichier.filename):
                    flash("Format non supporté. Utilisez PNG, JPG, GIF ou WEBP.", "danger")
                    return redirect(url_for("parametres_profil"))

                try:
                    # Upload vers Cloudinary :
                    # - folder      : dossier Cloudinary dédié
                    # - public_id   : identifiant unique par utilisateur (écrase l'ancienne photo)
                    # - overwrite   : True pour remplacer l'existant
                    # - transformation : redimensionne en carré 256×256 centré sur le visage
                    resultat = cloudinary.uploader.upload(
                        fichier,
                        folder="ctf_lab/avatars",
                        public_id=f"user_{current_user.id}",
                        overwrite=True,
                        transformation=[
                            {"width": 256, "height": 256,
                             "crop": "fill", "gravity": "face"}
                        ],
                        resource_type="image",
                    )
                    url_photo = resultat.get("secure_url")
                    # Sauvegarde l'URL HTTPS dans PostgreSQL (persistant entre redéploiements)
                    self._db.mettre_a_jour_photo(current_user.id, url_photo)
                    flash("Photo de profil mise à jour avec succès !", "success")
                except Exception as e:
                    logging.getLogger("upload").error(f"Cloudinary upload error: {e}")
                    flash("Erreur lors de l'upload. Vérifiez vos clés Cloudinary.", "danger")

                return redirect(url_for("parametres_profil"))

            # GET : recharge depuis BDD pour avoir la photo la plus récente
            user_row = self._db.obtenir_par_id(current_user.id)
            photo_actuelle = user_row.profile_pic if user_row else None
            return render_template("parametres_profil.html", photo_actuelle=photo_actuelle)

        @app.route("/defi/<identifiant>")
        @login_required
        def page_defi(identifiant):
            defi = self._gestionnaire.obtenir_defi(identifiant)
            if not defi:
                return render_template("404.html"), 404
            deja = self._db.a_deja_resolu(current_user.id, identifiant)
            d = defi.to_dict()
            if d["type"] == "crypto":
                return render_template("defi_crypto.html", defi=d, id=identifiant, deja_resolu=deja)
            return render_template("defi.html", defi=d, id=identifiant, deja_resolu=deja)

        @app.route("/api/soumettre", methods=["POST"])
        @login_required
        def api_soumettre():
            data = request.get_json(force=True)
            res = self._gestionnaire.soumettre_flag(
                data.get("id", ""), data.get("flag", ""), self._db, current_user.id
            )
            return jsonify(res), res["code"]

        @app.route("/telecharger/<nom_fichier>")
        @login_required
        def telecharger(nom_fichier):
            dossier = os.path.join(app.root_path, "static", "images")
            return send_from_directory(dossier, nom_fichier, as_attachment=True)

    def lancer(self, debug=False, port=5000):
        self._app.run(debug=debug, port=port)


if __name__ == "__main__":
    ApplicationCTF().lancer(debug=True)
