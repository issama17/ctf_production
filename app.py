"""
Plateforme CTF — v2 avec Authentification
Architecture : 100% Programmation Orientée Objet (POO)
Nouvelles classes : Utilisateur, BaseDeDonnees, GestionnaireAuth, ServiceEmail
"""

from flask import Flask, render_template, request, jsonify, send_from_directory, \
                  redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, \
                        login_required, current_user
from abc import ABC, abstractmethod
import hashlib, os, logging, sqlite3, secrets, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps


# ══════════════════════════════════════════════════════
#  COUCHE DONNÉES — BaseDeDonnees
# ══════════════════════════════════════════════════════

class BaseDeDonnees:
    """
    Gère toutes les interactions avec SQLite.
    Encapsulation totale : le reste de l'app ne touche jamais SQL directement.
    """

    def __init__(self, chemin: str = "ctf_platform.db"):
        self.__chemin = chemin
        self._initialiser_tables()

    def _connexion(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.__chemin)
        conn.row_factory = sqlite3.Row   # accès par nom de colonne
        return conn

    def _initialiser_tables(self) -> None:
        with self._connexion() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS utilisateurs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom_utilisateur TEXT    UNIQUE NOT NULL,
                    email           TEXT    UNIQUE NOT NULL,
                    mot_de_passe    TEXT    NOT NULL,
                    score           INTEGER DEFAULT 0,
                    confirme        INTEGER DEFAULT 0,
                    token_confirm   TEXT,
                    token_expiry    TEXT,
                    date_inscription TEXT   DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS soumissions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    defi_id     TEXT    NOT NULL,
                    succes      INTEGER NOT NULL,
                    date_soumis TEXT    DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES utilisateurs(id)
                );
            """)

    # ── Utilisateurs ────────────────────────────────
    def creer_utilisateur(self, nom: str, email: str,
                          mdp_hash: str, token: str, expiry: str) -> bool:
        try:
            with self._connexion() as conn:
                conn.execute(
                    "INSERT INTO utilisateurs "
                    "(nom_utilisateur, email, mot_de_passe, token_confirm, token_expiry) "
                    "VALUES (?,?,?,?,?)",
                    (nom, email, mdp_hash, token, expiry)
                )
            return True
        except sqlite3.IntegrityError:
            return False   # email ou nom déjà utilisé

    def obtenir_par_email(self, email: str) -> sqlite3.Row | None:
        with self._connexion() as conn:
            return conn.execute(
                "SELECT * FROM utilisateurs WHERE email=?", (email,)
            ).fetchone()

    def obtenir_par_id(self, uid: int) -> sqlite3.Row | None:
        with self._connexion() as conn:
            return conn.execute(
                "SELECT * FROM utilisateurs WHERE id=?", (uid,)
            ).fetchone()

    def obtenir_par_token(self, token: str) -> sqlite3.Row | None:
        with self._connexion() as conn:
            return conn.execute(
                "SELECT * FROM utilisateurs WHERE token_confirm=?", (token,)
            ).fetchone()

    def confirmer_utilisateur(self, uid: int) -> None:
        with self._connexion() as conn:
            conn.execute(
                "UPDATE utilisateurs SET confirme=1, token_confirm=NULL "
                "WHERE id=?", (uid,)
            )

    def ajouter_score(self, uid: int, points: int) -> None:
        with self._connexion() as conn:
            conn.execute(
                "UPDATE utilisateurs SET score = score + ? WHERE id=?",
                (points, uid)
            )

    def a_deja_resolu(self, uid: int, defi_id: str) -> bool:
        with self._connexion() as conn:
            row = conn.execute(
                "SELECT id FROM soumissions WHERE user_id=? AND defi_id=? AND succes=1",
                (uid, defi_id)
            ).fetchone()
            return row is not None

    def enregistrer_soumission(self, uid: int, defi_id: str, succes: bool) -> None:
        with self._connexion() as conn:
            conn.execute(
                "INSERT INTO soumissions (user_id, defi_id, succes) VALUES (?,?,?)",
                (uid, defi_id, int(succes))
            )

    def historique_soumissions(self, uid: int) -> list:
        with self._connexion() as conn:
            return conn.execute(
                "SELECT defi_id, succes, date_soumis FROM soumissions "
                "WHERE user_id=? ORDER BY date_soumis DESC LIMIT 20",
                (uid,)
            ).fetchall()


# ══════════════════════════════════════════════════════
#  COUCHE DOMAINE — Utilisateur (Flask-Login)
# ══════════════════════════════════════════════════════

class Utilisateur(UserMixin):
    """
    Modèle utilisateur compatible Flask-Login.
    Wraps une ligne SQLite et expose les attributs nécessaires.
    """

    def __init__(self, row: sqlite3.Row):
        self.id              = row["id"]
        self.nom_utilisateur = row["nom_utilisateur"]
        self.email           = row["email"]
        self._mdp_hash       = row["mot_de_passe"]
        self.score           = row["score"]
        self.confirme        = bool(row["confirme"])
        self.date_inscription= row["date_inscription"]

    def verifier_mot_de_passe(self, mdp: str) -> bool:
        return hashlib.sha256(mdp.encode()).hexdigest() == self._mdp_hash

    @staticmethod
    def hasher_mdp(mdp: str) -> str:
        return hashlib.sha256(mdp.encode()).hexdigest()

    def get_id(self) -> str:
        return str(self.id)


# ══════════════════════════════════════════════════════
#  SERVICE EMAIL
# ══════════════════════════════════════════════════════

class ServiceEmail:
    """
    Gère l'envoi d'emails de confirmation.
    Configurez vos identifiants SMTP dans config.py ou variables d'environnement.
    """

    def __init__(self, smtp_host: str, smtp_port: int,
                 expediteur: str, mdp_smtp: str):
        self.__host       = smtp_host
        self.__port       = smtp_port
        self.__expediteur = expediteur
        self.__mdp        = mdp_smtp
        self._logger      = logging.getLogger(self.__class__.__name__)

    def envoyer_confirmation(self, destinataire: str,
                              nom: str, lien: str) -> bool:
        """Envoie l'email de confirmation d'inscription."""
        sujet = "CTF_LAB — Confirmez votre adresse email"

        corps_html = f"""
        <div style="font-family:monospace;background:#050810;color:#c8d8f0;padding:30px;border-radius:8px;">
          <h2 style="color:#00ff88;">CTF_LAB</h2>
          <p>Bonjour <strong>{nom}</strong>,</p>
          <p>Merci de votre inscription. Cliquez sur le lien ci-dessous pour confirmer votre adresse :</p>
          <a href="{lien}"
             style="display:inline-block;margin:20px 0;padding:12px 24px;
                    background:#00ff88;color:#000;text-decoration:none;
                    border-radius:4px;font-weight:bold;">
            ✅ Confirmer mon compte
          </a>
          <p style="color:#5a7090;font-size:12px;">
            Ce lien expire dans 24 heures.<br/>
            Si vous n'avez pas créé de compte, ignorez cet email.
          </p>
        </div>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = sujet
        msg["From"]    = self.__expediteur
        msg["To"]      = destinataire
        msg.attach(MIMEText(corps_html, "html"))

        try:
            with smtplib.SMTP_SSL(self.__host, self.__port) as srv:
                srv.login(self.__expediteur, self.__mdp)
                srv.sendmail(self.__expediteur, destinataire, msg.as_string())
            self._logger.info(f"Email envoyé à {destinataire}")
            return True
        except Exception as e:
            self._logger.error(f"Échec envoi email : {e}")
            return False


# ══════════════════════════════════════════════════════
#  COUCHE SERVICE — GestionnaireAuth
# ══════════════════════════════════════════════════════

class GestionnaireAuth:
    """
    Orchestre l'inscription, la connexion et la confirmation email.
    """

    def __init__(self, db: BaseDeDonnees, service_email: ServiceEmail,
                 url_base: str):
        self.__db            = db
        self.__service_email = service_email
        self.__url_base      = url_base
        self._logger         = logging.getLogger(self.__class__.__name__)

    def inscrire(self, nom: str, email: str, mdp: str) -> dict:
        """Crée un compte et le confirme automatiquement sans email."""

        # Validations basiques
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

        # Confirmation automatique
        row = self.__db.obtenir_par_email(email)
        if row:
            self.__db.confirmer_utilisateur(row["id"])

        return {"succes": True, "message": "Inscription réussie ! Vous pouvez vous connecter."}

    def confirmer_email(self, token: str) -> dict:
        row = self.__db.obtenir_par_token(token)
        if not row:
            return {"succes": False, "message": "Lien invalide ou déjà utilisé."}

        expiry = datetime.fromisoformat(row["token_expiry"])
        if datetime.utcnow() > expiry:
            return {"succes": False, "message": "Lien expiré. Réinscrivez-vous."}

        self.__db.confirmer_utilisateur(row["id"])
        return {"succes": True, "message": "Email confirmé ! Vous pouvez vous connecter."}

    def connecter(self, email: str, mdp: str) -> dict:
        row = self.__db.obtenir_par_email(email)
        if not row:
            return {"succes": False, "message": "Email ou mot de passe incorrect."}

        user = Utilisateur(row)
        if not user.verifier_mot_de_passe(mdp):
            return {"succes": False, "message": "Email ou mot de passe incorrect."}

        if not user.confirme:
            return {"succes": False,
                    "message": "Compte non confirmé. Vérifiez votre email."}

        return {"succes": True, "utilisateur": user}

    def charger_utilisateur(self, uid: int) -> Utilisateur | None:
        row = self.__db.obtenir_par_id(uid)
        return Utilisateur(row) if row else None


# ══════════════════════════════════════════════════════
#  COUCHE DOMAINE CTF (inchangée)
# ══════════════════════════════════════════════════════

class DefiCTF(ABC):
    def __init__(self, titre, description, points, difficulte):
        self._titre       = titre
        self._description = description
        self._points      = points
        self._difficulte  = difficulte
        self._resolu      = False

    @property
    def titre(self):       return self._titre
    @property
    def description(self): return self._description
    @property
    def points(self):      return self._points
    @property
    def difficulte(self):  return self._difficulte
    @property
    def resolu(self):      return self._resolu

    @abstractmethod
    def verifier_flag(self, tentative: str) -> bool: pass
    @abstractmethod
    def obtenir_indice(self) -> str: pass

    def marquer_resolu(self):
        self._resolu = True


class ValidateurFlag:
    def __init__(self, flag_secret: str):
        self.__hash_secret    = hashlib.sha256(flag_secret.encode()).hexdigest()
        self.__tentatives     = 0
        self.__MAX_TENTATIVES = 10

    @property
    def tentatives(self): return self.__tentatives
    @property
    def bloque(self):     return self.__tentatives >= self.__MAX_TENTATIVES

    def valider(self, tentative: str) -> bool:
        if self.bloque: return False
        self.__tentatives += 1
        return hashlib.sha256(tentative.strip().encode()).hexdigest() == self.__hash_secret


class DefiStegano(DefiCTF):
    def __init__(self, titre, description, points, flag_secret, fichier_image, outil_cache):
        super().__init__(titre, description, points, "Moyen")
        self.__validateur   = ValidateurFlag(flag_secret)
        self._fichier_image = fichier_image
        self._outil_cache   = outil_cache

    @property
    def fichier_image(self): return self._fichier_image
    @property
    def outil_cache(self):   return self._outil_cache
    @property
    def tentatives(self):    return self.__validateur.tentatives
    @property
    def bloque(self):        return self.__validateur.bloque

    def verifier_flag(self, tentative: str) -> bool:
        if not tentative.startswith("CTF{") or not tentative.endswith("}"):
            return False
        correct = self.__validateur.valider(tentative)
        if correct: self.marquer_resolu()
        return correct

    def obtenir_indice(self) -> str:
        n = self.__validateur.tentatives
        if n < 3:  return "💡 Le secret se cache dans les pixels…"
        if n < 6:  return f"💡 Essayez d'extraire avec {self._outil_cache}."
        return f"💡 Commande : {self._outil_cache} extract -sf image.jpg -p [mot_de_passe]"

    def to_dict(self) -> dict:
        return {
            "titre": self._titre, "description": self._description,
            "points": self._points, "difficulte": self._difficulte,
            "fichier": self._fichier_image, "outil": self._outil_cache,
            "resolu": self._resolu,
            "tentatives": self.__validateur.tentatives,
            "bloque": self.__validateur.bloque,
        }


class GestionnaireCTF:
    def __init__(self):
        self._defis  = {}
        self._logger = logging.getLogger(self.__class__.__name__)

    def enregistrer_defi(self, identifiant, defi):
        self._defis[identifiant] = defi

    def obtenir_defi(self, identifiant):
        return self._defis.get(identifiant)

    def soumettre_flag(self, identifiant, tentative, db, uid):
        defi = self.obtenir_defi(identifiant)
        if not defi:
            return {"succes": False, "message": "Défi introuvable.", "code": 404}

        # Vérifier si déjà résolu par cet utilisateur
        if db.a_deja_resolu(uid, identifiant):
            return {"succes": True,
                    "message": "✅ Vous avez déjà résolu ce défi !",
                    "points": 0, "deja_resolu": True, "code": 200}

        if isinstance(defi, DefiStegano) and defi.bloque:
            return {"succes": False,
                    "message": "🔒 Trop de tentatives.", "code": 429}

        correct = defi.verifier_flag(tentative)
        db.enregistrer_soumission(uid, identifiant, correct)

        if correct:
            db.ajouter_score(uid, defi.points)
            return {"succes": True,
                    "message": f"🎉 Félicitations ! +{defi.points} points !",
                    "points": defi.points, "code": 200}
        else:
            indice     = defi.obtenir_indice() if isinstance(defi, DefiStegano) else ""
            tentatives = defi.tentatives if isinstance(defi, DefiStegano) else 0
            return {"succes": False,
                    "message": "❌ Flag incorrect. Continuez à chercher…",
                    "indice": indice, "tentatives": tentatives, "code": 200}

    def liste_defis(self):
        return [{"id": k, **v.to_dict()}
                for k, v in self._defis.items()
                if isinstance(v, DefiStegano)]


# ══════════════════════════════════════════════════════
#  APPLICATION FLASK
# ══════════════════════════════════════════════════════

class ApplicationCTF:

    def __init__(self):
        self._app = Flask(__name__)
        self._app.secret_key = secrets.token_hex(32)

        # ── Configuration SMTP ── Modifiez ici avec vos identifiants ──
        self._service_email = ServiceEmail(
            smtp_host  = "smtp.gmail.com",
            smtp_port  = 465,
            expediteur = os.getenv("CTF_EMAIL", "votre.email@gmail.com"),
            mdp_smtp   = os.getenv("CTF_EMAIL_MDP", "votre_mot_de_passe_app"),
        )
        self._url_base    = os.getenv("CTF_URL", "http://127.0.0.1:5000")
        self._db          = BaseDeDonnees()
        self._auth        = GestionnaireAuth(self._db, self._service_email, self._url_base)
        self._gestionnaire = GestionnaireCTF()

        self._configurer_login_manager()
        self._initialiser_defis()
        self._enregistrer_routes()
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s [%(name)s] %(levelname)s — %(message)s")

    def _configurer_login_manager(self):
        lm = LoginManager()
        lm.init_app(self._app)
        lm.login_view      = "login"
        lm.login_message   = "Connectez-vous pour accéder à cette page."
        lm.login_message_category = "warning"

        @lm.user_loader
        def charger_utilisateur(uid):
            return self._auth.charger_utilisateur(int(uid))

    def _initialiser_defis(self):
        self._gestionnaire.enregistrer_defi("stegano_01", DefiStegano(
            titre        = "Ombres Numériques",
            description  = (
                "Une image anodine circule sur les réseaux. "
                "Les services de renseignement pensent qu'un message secret y est dissimulé. "
                "Votre mission : extraire le flag caché dans les données de ce fichier image. "
                "Le format attendu est <code>CTF{...}</code>."
            ),
            points       = 150,
            flag_secret  = "CTF{st3g4n0_m4st3r_2024}",
            fichier_image= "image_piege.jpg",
            outil_cache  = "steghide",
        ))

    def _enregistrer_routes(self):
        app = self._app

        # ── Pages publiques ──────────────────────────
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
                if res.get("lien_dev"):
                    flash(f"[DEV] Lien : {res['lien_dev']}", "info")
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

        # ── Pages protégées ──────────────────────────
        @app.route("/profil")
        @login_required
        def profil():
            historique = self._db.historique_soumissions(current_user.id)
            return render_template("profil.html", historique=historique)

        @app.route("/defi/<identifiant>")
        @login_required
        def page_defi(identifiant):
            defi = self._gestionnaire.obtenir_defi(identifiant)
            if not defi:
                return render_template("404.html"), 404
            deja = self._db.a_deja_resolu(current_user.id, identifiant)
            return render_template("defi.html", defi=defi.to_dict(),
                                   id=identifiant, deja_resolu=deja)

        @app.route("/api/soumettre", methods=["POST"])
        @login_required
        def api_soumettre():
            data   = request.get_json(force=True)
            res    = self._gestionnaire.soumettre_flag(
                data.get("id", ""), data.get("flag", ""),
                self._db, current_user.id
            )
            return jsonify(res), res["code"]

        @app.route("/telecharger/<nom_fichier>")
        @login_required
        def telecharger(nom_fichier):
            dossier = os.path.join(app.root_path, "static", "images")
            return send_from_directory(dossier, nom_fichier, as_attachment=True)

    def lancer(self, debug=True, port=5000):
        self._app.run(debug=debug, port=port)


if __name__ == "__main__":
    ApplicationCTF().lancer()
