"""
Couche de Présentation (Routes)
"""
import os
import logging
import cloudinary.uploader
from werkzeug.utils import secure_filename

from flask import render_template, request, jsonify, send_from_directory, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user

LAST_CLOUDINARY_ERROR = "No errors yet."

def register_routes(app, service_auth, service_ctf, user_repo):
    
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

    @app.route("/profil")
    @login_required
    def profil():
        historique = service_ctf._challenge_repo.obtenir_historique(current_user.id)
        return render_template("profil.html", historique=historique)

    @app.route("/profil/parametres", methods=["GET", "POST"])
    @login_required
    def parametres_profil():
        if request.method == "POST":
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
                global LAST_CLOUDINARY_ERROR
                LAST_CLOUDINARY_ERROR = str(e)
                logging.getLogger("upload").error(f"Cloudinary upload error: {e}")
                flash(f"Erreur d'upload : {str(e)}", "danger")

            return redirect(url_for("parametres_profil"))

        user_row = user_repo.obtenir_par_id(current_user.id)
        photo_actuelle = user_row.profile_pic if user_row else None
        return render_template("parametres_profil.html", photo_actuelle=photo_actuelle)

    @app.route("/scoreboard")
    @login_required
    def scoreboard():
        rows = user_repo.obtenir_classement()
        joueurs = []
        for row in rows:
            resolus = service_ctf._challenge_repo.obtenir_nombre_resolus(row.id)
            joueurs.append({
                "nom":          row.username,
                "score":        row.score or 0,
                "profile_pic":  row.profile_pic,
                "defis_resolus": resolus,
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
        return render_template("defi.html", defi=d, id=identifiant, deja_resolu=deja)

    @app.route("/api/soumettre", methods=["POST"])
    @login_required
    def api_soumettre():
        data = request.get_json(force=True)
        res = service_ctf.soumettre_flag(
            data.get("id", ""), 
            data.get("flag", ""), 
            current_user.id
        )
        return jsonify(res), res["code"]

    @app.route("/debug-env")
    def debug_env():
        cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
        api_key = os.getenv("CLOUDINARY_API_KEY", "")
        api_secret = os.getenv("CLOUDINARY_API_SECRET", "")
        return jsonify({
            "cloud_name": f"{cloud_name[:3]}... (len: {len(cloud_name)})",
            "api_key": f"{api_key[:3]}... (len: {len(api_key)})",
            "api_secret": f"{api_secret[:3]}... (len: {len(api_secret)})",
            "env_keys": list(os.environ.keys())
        })

    @app.route("/debug-upload")
    def debug_upload():
        global LAST_CLOUDINARY_ERROR
        return jsonify({
            "last_error": LAST_CLOUDINARY_ERROR
        })

    @app.route("/telecharger/<nom_fichier>")
    @login_required
    def telecharger(nom_fichier):
        safe_filename = secure_filename(nom_fichier)
        if not safe_filename:
            return "Nom de fichier invalide", 400
            
        dossier = os.path.join(current_app.root_path, "static", "images")
        return send_from_directory(dossier, safe_filename, as_attachment=True)
