"""
Presentation Layer (Routes)
Flask routes containing the application endpoints.
"""
import os
import logging
import cloudinary.uploader
from werkzeug.utils import secure_filename

from flask import render_template, request, jsonify, send_from_directory, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user

def register_routes(app, auth_service, ctf_service, user_repo):
    """
    + register_routes(app, auth_service, ctf_service, user_repo) -> None
    Registers the main application routes directly on the app instance.
    """
    
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    
    def allowed_file(filename: str) -> bool:
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    @app.route("/")
    def index():
        uid = current_user.id if current_user.is_authenticated else None
        defis = ctf_service.list_challenges(uid)
        return render_template("index.html", defis=defis)

    @app.route("/inscription", methods=["GET", "POST"])
    def inscription():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
            
        if request.method == "POST":
            res = auth_service.register(
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
            res = auth_service.login(
                request.form.get("email", "").strip().lower(),
                request.form.get("mdp", ""),
            )
            if res["succes"]:
                login_user(res["utilisateur"], remember=True)
                # Secure redirect to avoid open redirect vulnerabilities
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
        # Requires ChallengeRepository for history
        historique = ctf_service._challenge_repo.get_submission_history(current_user.id)
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

            if not allowed_file(fichier.filename):
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
                user_repo.update_profile_pic(current_user.id, url_photo)
                flash("Photo de profil mise à jour avec succès !", "success")
            except Exception as e:
                logging.getLogger("upload").error(f"Cloudinary upload error: {e}")
                flash("Erreur lors de l'upload. Vérifiez vos clés Cloudinary.", "danger")

            return redirect(url_for("parametres_profil"))

        user_row = user_repo.get_by_id(current_user.id)
        photo_actuelle = user_row.profile_pic if user_row else None
        return render_template("parametres_profil.html", photo_actuelle=photo_actuelle)

    @app.route("/scoreboard")
    @login_required
    def scoreboard():
        rows = user_repo.get_scoreboard()
        joueurs = []
        for row in rows:
            resolus = ctf_service._challenge_repo.get_solved_count(row.id)
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
        d = ctf_service.get_challenge_view(identifiant, current_user.id)
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
        # Implement Rate Limiting / Validation here if needed
        res = ctf_service.submit_flag(
            data.get("id", ""), 
            data.get("flag", ""), 
            current_user.id
        )
        return jsonify(res), res["code"]

    @app.route("/telecharger/<nom_fichier>")
    @login_required
    def telecharger(nom_fichier):
        # Security: Prevent directory traversal with secure_filename
        safe_filename = secure_filename(nom_fichier)
        if not safe_filename:
            return "Invalid filename", 400
            
        dossier = os.path.join(current_app.root_path, "static", "images")
        return send_from_directory(dossier, safe_filename, as_attachment=True)
