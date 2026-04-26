"""
Plateforme CTF — v3 avec Cryptographie
Architecture : 100% Programmation Orientée Objet (POO)
Ajout : DefiCrypto + 3 défis cryptographiques
"""

from flask import Flask, render_template, request, jsonify, send_from_directory, \
                  redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, \
                        login_required, current_user
from abc import ABC, abstractmethod
import hashlib, os, logging, sqlite3, secrets, smtplib, base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps


# ══════════════════════════════════════════════════════
#  COUCHE DONNÉES — BaseDeDonnees
# ══════════════════════════════════════════════════════

class BaseDeDonnees:
    def __init__(self, chemin: str = "ctf_platform.db"):
        self.__chemin = chemin
        self._initialiser_tables()

    def _connexion(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.__chemin)
        conn.row_factory = sqlite3.Row
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

    def creer_utilisateur(self, nom, email, mdp_hash, token, expiry) -> bool:
        try:
            with self._connexion() as conn:
                conn.execute(
                    "INSERT INTO utilisateurs (nom_utilisateur,email,mot_de_passe,token_confirm,token_expiry) VALUES (?,?,?,?,?)",
                    (nom, email, mdp_hash, token, expiry)
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def obtenir_par_email(self, email):
        with self._connexion() as conn:
            return conn.execute("SELECT * FROM utilisateurs WHERE email=?", (email,)).fetchone()

    def obtenir_par_id(self, uid):
        with self._connexion() as conn:
            return conn.execute("SELECT * FROM utilisateurs WHERE id=?", (uid,)).fetchone()

    def obtenir_par_token(self, token):
        with self._connexion() as conn:
            return conn.execute("SELECT * FROM utilisateurs WHERE token_confirm=?", (token,)).fetchone()

    def confirmer_utilisateur(self, uid) -> None:
        with self._connexion() as conn:
            conn.execute("UPDATE utilisateurs SET confirme=1, token_confirm=NULL WHERE id=?", (uid,))

    def ajouter_score(self, uid, points) -> None:
        with self._connexion() as conn:
            conn.execute("UPDATE utilisateurs SET score = score + ? WHERE id=?", (points, uid))

    def a_deja_resolu(self, uid, defi_id) -> bool:
        with self._connexion() as conn:
            row = conn.execute(
                "SELECT id FROM soumissions WHERE user_id=? AND defi_id=? AND succes=1",
                (uid, defi_id)
            ).fetchone()
            return row is not None

    def enregistrer_soumission(self, uid, defi_id, succes) -> None:
        with self._connexion() as conn:
            conn.execute(
                "INSERT INTO soumissions (user_id,defi_id,succes) VALUES (?,?,?)",
                (uid, defi_id, int(succes))
            )

    def historique_soumissions(self, uid) -> list:
        with self._connexion() as conn:
            return conn.execute(
                "SELECT defi_id, succes, date_soumis FROM soumissions WHERE user_id=? ORDER BY date_soumis DESC LIMIT 20",
                (uid,)
            ).fetchall()


# ══════════════════════════════════════════════════════
#  COUCHE DOMAINE — Utilisateur
# ══════════════════════════════════════════════════════

class Utilisateur(UserMixin):
    def __init__(self, row):
        self.id              = row["id"]
        self.nom_utilisateur = row["nom_utilisateur"]
        self.email           = row["email"]
        self._mdp_hash       = row["mot_de_passe"]
        self.score           = row["score"]
        self.confirme        = bool(row["confirme"])
        self.date_inscription= row["date_inscription"]

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
          <a href="{lien}" style="display:inline-block;margin:20px 0;padding:12px 24px;background:#00ff88;color:#000;">✅ Confirmer</a>
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
            self.__db.confirmer_utilisateur(row["id"])
        return {"succes": True, "message": "Inscription réussie ! Vous pouvez vous connecter."}

    def confirmer_email(self, token) -> dict:
        row = self.__db.obtenir_par_token(token)
        if not row:
            return {"succes": False, "message": "Lien invalide ou déjà utilisé."}
        expiry = datetime.fromisoformat(row["token_expiry"])
        if datetime.utcnow() > expiry:
            return {"succes": False, "message": "Lien expiré."}
        self.__db.confirmer_utilisateur(row["id"])
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
        if n < 3: return "💡 Le secret se cache dans les pixels…"
        if n < 6: return f"💡 Essayez d'extraire avec {self._outil_cache}."
        return f"💡 Commande : {self._outil_cache} extract -sf image.jpg -p [mot_de_passe]"

    def to_dict(self) -> dict:
        return {
            "titre": self._titre, "description": self._description,
            "points": self._points, "difficulte": self._difficulte,
            "fichier": self._fichier_image, "outil": self._outil_cache,
            "resolu": self._resolu, "tentatives": self.__validateur.tentatives,
            "bloque": self.__validateur.bloque, "type": "stegano",
        }


class DefiCrypto(DefiCTF):
    """Défi de cryptographie avec texte chiffré et indices progressifs."""

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
            return {"succes": True, "message": "✅ Vous avez déjà résolu ce défi !", "points": 0, "deja_resolu": True, "code": 200}
        if defi.bloque:
            return {"succes": False, "message": "🔒 Trop de tentatives.", "code": 429}
        correct = defi.verifier_flag(tentative)
        db.enregistrer_soumission(uid, identifiant, correct)
        if correct:
            db.ajouter_score(uid, defi.points)
            return {"succes": True, "message": f"🎉 Félicitations ! +{defi.points} points !", "points": defi.points, "code": 200}
        return {"succes": False, "message": "❌ Flag incorrect. Continuez à chercher…",
                "indice": defi.obtenir_indice(), "tentatives": defi.tentatives, "code": 200}

    def liste_defis(self):
        return [{"id": k, **v.to_dict()} for k, v in self._defis.items()]


# ══════════════════════════════════════════════════════
#  APPLICATION FLASK
# ══════════════════════════════════════════════════════

class ApplicationCTF:

    def __init__(self):
        self._app = Flask(__name__)
        self._app.secret_key = secrets.token_hex(32)
        self._service_email = ServiceEmail(
            smtp_host="smtp.gmail.com", smtp_port=465,
            expediteur=os.getenv("CTF_EMAIL", "votre.email@gmail.com"),
            mdp_smtp=os.getenv("CTF_EMAIL_MDP", "votre_mot_de_passe_app"),
        )
        self._url_base = os.getenv("CTF_URL", "http://127.0.0.1:5000")
        self._db = BaseDeDonnees()
        self._auth = GestionnaireAuth(self._db, self._service_email, self._url_base)
        self._gestionnaire = GestionnaireCTF()
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
        # ── Stéganographie ──────────────────────────
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

        # ── Crypto 1 — César ROT13 (Facile) ─────────
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
                "💡 Ce chiffrement substitue chaque lettre par une autre décalée d'un nombre fixe de positions.",
                "💡 Le chiffre de César utilise un décalage constant. Essayez tous les décalages de 1 à 25.",
                "💡 Le décalage utilisé ici est 13 (ROT13). Appliquez ROT13 à chaque lettre du texte chiffré.",
            ],
            categorie_crypto="Chiffrement par substitution / César",
        ))

        # ── Crypto 2 — Base64 + XOR (Moyen) ─────────
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
                "💡 Le texte est en hexadécimal. Convertissez-le d'abord en octets.",
                "💡 Chaque octet a été XORé avec 0x42. Appliquez XOR(0x42) à chaque octet pour inverser l'opération.",
                "💡 Après le XOR vous obtenez une chaîne Base64. Décodez-la pour obtenir le flag final.",
            ],
            categorie_crypto="XOR / Base64",
        ))

        # ── Crypto 3 — RSA faible (Difficile) ───────
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
                "💡 n = 3233 est petit. Trouvez p et q tels que p × q = n en essayant des diviseurs.",
                "💡 p = 61 et q = 53. Calculez φ(n) = (p−1)(q−1) = 3120, puis trouvez d tel que e·d ≡ 1 (mod φ(n)).",
                "💡 d = 2753. Déchiffrez : m = c^d mod n = 2201^2753 mod 3233. Le flag est CTF{m}.",
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

    def lancer(self, debug=True, port=5000):
        self._app.run(debug=debug, port=port)


if __name__ == "__main__":
    ApplicationCTF().lancer()
