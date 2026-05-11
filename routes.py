"""
Couche de Présentation (Routes)
"""
import os
import logging
import secrets
import cloudinary.uploader
from werkzeug.utils import secure_filename
from werkzeug.exceptions import Forbidden

from flask import render_template, request, jsonify, send_from_directory, redirect, url_for, flash, current_app, session
from flask_login import login_user, logout_user, login_required, current_user

from exceptions import FlagIncorrectException

def register_routes(app, service_auth, service_ctf, user_repo, oauth):
    
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    
    def fichier_autorise(filename: str) -> bool:
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    @app.route("/")
    def index():
        uid = current_user.id if current_user.is_authenticated else None
        defis = service_ctf.lister_defis(uid)
        return render_template("index.html", defis=defis)

    @app.route("/inscription", methods=["GET", "POST"])
    def inscription():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
            
        if request.method == "POST":
            res = service_auth.inscrire(
                request.form.get("nom", "").strip(),
                request.form.get("email", "").strip().lower(),
                request.form.get("mdp", ""),
                request.form.get("statut", "Étudiant"),
                request.form.get("experience", "Débutant"),
            )
            flash(res["message"], "success" if res["succes"] else "danger")
            if res["succes"]:
                return redirect(url_for("login"))
                
        return render_template("inscription.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
            
        if request.method == "POST":
            res = service_auth.connecter(
                request.form.get("email", "").strip().lower(),
                request.form.get("mdp", ""),
            )
            if res["succes"]:
                login_user(res["utilisateur"], remember=True)
                next_page = request.args.get("next")
                if next_page and not next_page.startswith('/'):
                    next_page = url_for("index")
                return redirect(next_page or url_for("index"))
            flash(res["message"], "danger")
            
        return render_template("login.html")

    @app.route("/deconnexion")
    @login_required
    def deconnexion():
        logout_user()
        flash("Déconnexion réussie.", "info")
        return redirect(url_for("login"))

    # ══════════════════════════════════════════════════════
    #  OAUTH GOOGLE
    # ══════════════════════════════════════════════════════

    @app.route("/login/google")
    def login_google():
        # Capturer les options choisies par l'utilisateur (Statut et Expérience)
        session['google_statut'] = request.args.get('statut', 'Étudiant')
        session['google_experience'] = request.args.get('experience', 'Débutant')
        
        # L'URL de redirection doit être configurée dans la console Google Cloud
        # ex: https://votre-app.up.railway.app/google/auth
        
        # On utilise CTF_URL si défini pour forcer l'URL externe correcte
        ctf_url = os.getenv("CTF_URL")
        if ctf_url:
            redirect_uri = f"{ctf_url.rstrip('/')}{url_for('google_auth')}"
        else:
            redirect_uri = url_for("google_auth", _external=True)
            
        logging.info(f"OAuth Redirect URI: {redirect_uri}")
        return oauth.google.authorize_redirect(redirect_uri)

    @app.route("/google/auth")
    def google_auth():
        try:
            token = oauth.google.authorize_access_token()
            user_info = oauth.google.get('https://www.googleapis.com/oauth2/v3/userinfo').json()
        except Exception as e:
            flash("Erreur d'authentification Google.", "danger")
            logging.error(f"OAuth Error: {e}")
            return redirect(url_for("login"))

        email = user_info.get("email")
        name = user_info.get("name") or email.split("@")[0]
        picture = user_info.get("picture")

        # Récupérer les options depuis la session (ou valeurs par défaut)
        statut = session.pop('google_statut', 'Étudiant')
        experience = session.pop('google_experience', 'Débutant')

        # Chercher l'utilisateur par email
        user_row = user_repo.obtenir_par_email(email)
        
        if not user_row:
            # Créer un compte s'il n'existe pas
            random_pwd = secrets.token_urlsafe(16)
            res = service_auth.inscrire(name, email, random_pwd, statut=statut, experience=experience)
            if not res["succes"]:
                flash("Impossible de créer votre compte via Google.", "danger")
                return redirect(url_for("login"))
            user_row = user_repo.obtenir_par_email(email)
            
            # Mettre à jour la photo de profil si fournie par Google
            if picture:
                user_repo.mettre_a_jour_photo(user_row.id, picture)

        # Connecter l'utilisateur
        from models import UsineUtilisateur
        utilisateur = UsineUtilisateur.creer(user_row)
        login_user(utilisateur, remember=True)
        
        flash(f"Bienvenue, {utilisateur.username} !", "success")
        return redirect(url_for("index"))

    @app.route("/profil")
    @login_required
    def profil():
        historique = service_ctf.obtenir_historique_utilisateur(current_user.id)
        defis_total = service_ctf.obtenir_nombre_defis()
        return render_template("profil.html", historique=historique, defis_total=defis_total)

    @app.route("/profil/parametres", methods=["GET", "POST"])
    @login_required
    def parametres_profil():
        if request.method == "POST":
            if "username" in request.form and "email" in request.form:
                username = request.form.get("username", "").strip()
                email = request.form.get("email", "").strip().lower()
                res = service_auth.mettre_a_jour_profil(current_user.id, username, email)
                flash(res["message"], "success" if res["succes"] else "danger")
                return redirect(url_for("parametres_profil"))

            if "photo" not in request.files:
                flash("Aucun fichier sélectionné.", "danger")
                return redirect(url_for("parametres_profil"))

            fichier = request.files["photo"]
            if fichier.filename == "":
                flash("Aucun fichier sélectionné.", "danger")
                return redirect(url_for("parametres_profil"))

            if not fichier_autorise(fichier.filename):
                flash("Format non supporté. Utilisez PNG, JPG, GIF ou WEBP.", "danger")
                return redirect(url_for("parametres_profil"))

            try:
                resultat = cloudinary.uploader.upload(
                    fichier,
                    folder="ctf_lab/avatars",
                    public_id=f"user_{current_user.id}",
                    overwrite=True,
                    transformation=[
                        {"width": 256, "height": 256, "crop": "fill", "gravity": "face"}
                    ],
                    resource_type="image",
                )
                url_photo = resultat.get("secure_url")
                user_repo.mettre_a_jour_photo(current_user.id, url_photo)
                flash("Photo de profil mise à jour avec succès !", "success")
            except Exception as e:
                logging.getLogger("upload").error(f"Cloudinary upload error: {e}")
                flash(f"Erreur d'upload : {str(e)}", "danger")

            return redirect(url_for("parametres_profil"))

        user_row = user_repo.obtenir_par_id(current_user.id)
        photo_actuelle = user_row.profile_pic if user_row else None
        return render_template("parametres_profil.html", photo_actuelle=photo_actuelle)

    @app.route("/mot_de_passe_oublie", methods=["GET", "POST"])
    def mot_de_passe_oublie():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
            
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            new_password = request.form.get("new_password", "")
            res = service_auth.reinitialiser_mot_de_passe(email, new_password)
            flash(res["message"], "success" if res["succes"] else "danger")
            if res["succes"]:
                return redirect(url_for("login"))
                
        return render_template("mot_de_passe_oublie.html")

    from models import FabriqueStatut
    @app.route("/scoreboard")
    @login_required
    def scoreboard():
        rows = user_repo.obtenir_classement()
        joueurs = []
        for row in rows:
            resolus = service_ctf.obtenir_nombre_resolus(row.id)
            statut_obj = FabriqueStatut.creer(row.statut)
            joueurs.append({
                "nom":          row.username,
                "score":        row.score or 0,
                "profile_pic":  row.profile_pic,
                "defis_resolus": resolus,
                "statut_nom":   statut_obj.obtenir_nom(),
                "statut_couleur": statut_obj.obtenir_couleur(),
                "experience":   row.experience,
                "est_moi":      row.id == current_user.id,
            })
        return render_template("scoreboard.html", joueurs=joueurs)

    @app.route("/defi/<identifiant>")
    @login_required
    def page_defi(identifiant):
        d = service_ctf.obtenir_vue_defi(identifiant, current_user.id)
        if not d:
            return render_template("404.html"), 404
            
        deja = d["resolu"]
        if d["type"] == "crypto":
            return render_template("defi_crypto.html", defi=d, id=identifiant, deja_resolu=deja)
        elif d["type"] == "web":
            return render_template("defi_web.html", defi=d, id=identifiant, deja_resolu=deja)
        elif d["type"] == "reverse":
            return render_template("defi_reverse.html", defi=d, id=identifiant, deja_resolu=deja)
        return render_template("defi.html", defi=d, id=identifiant, deja_resolu=deja)

    @app.route("/api/soumettre", methods=["POST"])
    @login_required
    def api_soumettre():
        data = request.get_json(force=True)
        try:
            res = service_ctf.soumettre_flag(
                data.get("id", ""), 
                data.get("flag", ""), 
                current_user.id
            )
            return jsonify(res), res.get("code", 200)
        except FlagIncorrectException as e:
            # Traitement explicite de notre exception personnalisée
            return jsonify({
                "succes": False,
                "message": str(e),
                "tentatives": e.tentatives,
                "indice": e.indice
            }), 200

    @app.route("/telecharger/<nom_fichier>")
    @login_required
    def telecharger(nom_fichier):
        safe_filename = secure_filename(nom_fichier)
        if not safe_filename:
            return "Nom de fichier invalide", 400
            
        for sous_dossier in ["images", "evidence"]:
            dossier = os.path.join(current_app.root_path, "static", sous_dossier)
            if os.path.exists(os.path.join(dossier, safe_filename)):
                return send_from_directory(dossier, safe_filename, as_attachment=True)
                
        return "Fichier non trouvé", 404

    @app.route("/admin")
    @login_required
    def admin_dashboard():
        """Route d'administration. Démontre l'utilisation du polymorphisme des Rôles."""
        if current_user.obtenir_role() != "admin":
            flash("Accès refusé. Vous devez être administrateur.", "danger")
            return redirect(url_for("index"))
            
        utilisateurs = user_repo.obtenir_classement()
        stats = {
            "total_users": len(utilisateurs),
            "top_score": utilisateurs[0].score if utilisateurs else 0
        }
        return render_template("admin.html", utilisateurs=utilisateurs, stats=stats)

    @app.route("/lab/sqli/login", methods=["GET", "POST"])
    def lab_sqli_login():
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            
            sqli_patterns = ["'--", "' --", "' or ", "' OR ", 
                             "1=1", "OR 1", "or 1", "\"--", "admin'"]
            is_sqli = any(p in username for p in sqli_patterns)
            
            if is_sqli:
                session["lab_sqli_pwned"] = True
                return redirect(url_for("lab_sqli_admin"))
            else:
                session["lab_sqli_pwned"] = False
                return render_template("lab/sqli_login.html", error="Identifiants incorrects")
        
        return render_template("lab/sqli_login.html", error=None)

    @app.route("/lab/sqli/admin")
    def lab_sqli_admin():
        if not session.get("lab_sqli_pwned"):
            return redirect(url_for("lab_sqli_login"))
        
        # Le flag est stocké uniquement sous sa forme chiffrée (Hex) pour GitHub.
        # Format original: CTF{...}
        # Chiffrement: XOR avec la clé 'EST_SECRET_KEY_99'
        encrypted_flag = "0607122400140f1b1a191e18111c0d667c16070b0b16110c07041a22"
        
        return render_template("lab/sqli_admin.html", flag=encrypted_flag)

    @app.route("/lab/sqli/reset")
    def lab_sqli_reset():
        session.pop("lab_sqli_pwned", None)
        return redirect(url_for("lab_sqli_login"))

