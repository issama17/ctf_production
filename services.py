"""
Couche Logique Métier (Services)
Implémente le Design Pattern Observer pour les notifications et les logs.
"""
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from abc import ABC, abstractmethod
from models import Utilisateur, UsineUtilisateur, Defi, ContexteDefi
from repository import UtilisateurRepository, DefiRepository
from exceptions import DefiBloqueException, DefiDejaResoluException, FlagIncorrectException

class ServiceAuth:
    """Service pour l'authentification et l'inscription."""
    def __init__(self, user_repo: UtilisateurRepository, base_url: str):
        self.__user_repo = user_repo
        self.__base_url = base_url
        self.__logger = logging.getLogger(self.__class__.__name__)

    def inscrire(self, username: str, email: str, password: str, statut: str = "Étudiant", experience: str = "Débutant") -> dict:
        if len(username) < 3: return {"succes": False, "message": "Le nom doit faire au moins 3 caractères."}
        if len(password) < 6: return {"succes": False, "message": "Le mot de passe doit faire au moins 6 caractères."}
        if "@" not in email: return {"succes": False, "message": "Email invalide."}
            
        if self.__user_repo.obtenir_par_email(email):
            return {"succes": False, "message": "Cet email est déjà utilisé."}
            
        pwd_hash = Utilisateur.hacher_mot_de_passe(password)
        total_users = len(self.__user_repo.obtenir_classement())
        role = "admin" if total_users == 0 else "participant"
        
        success = self.__user_repo.creer_utilisateur(username, email, pwd_hash, role, statut, experience)
        if not success: return {"succes": False, "message": "Erreur lors de l'inscription."}
        return {"succes": True, "message": "Inscription réussie !"}

    def connecter(self, email: str, password: str) -> dict:
        row = self.__user_repo.obtenir_par_email(email)
        if not row: return {"succes": False, "message": "Email ou mot de passe incorrect."}
        
        utilisateur = UsineUtilisateur.creer(row)
        if not utilisateur.verifier_mot_de_passe(password):
            return {"succes": False, "message": "Email ou mot de passe incorrect."}
        return {"succes": True, "utilisateur": utilisateur}

    def charger_utilisateur(self, uid: int) -> Utilisateur:
        row = self.__user_repo.obtenir_par_id(uid)
        return UsineUtilisateur.creer(row) if row else None

    def mettre_a_jour_profil(self, uid: int, username: str, email: str) -> dict:
        success = self.__user_repo.mettre_a_jour_profil(uid, username, email)
        if not success: return {"succes": False, "message": "Erreur lors de la mise à jour."}
        return {"succes": True, "message": "Profil mis à jour."}

    def reinitialiser_mot_de_passe(self, email: str, new_password: str) -> dict:
        pwd_hash = Utilisateur.hacher_mot_de_passe(new_password)
        success = self.__user_repo.mettre_a_jour_mot_de_passe(email, pwd_hash)
        if not success: return {"succes": False, "message": "Email introuvable."}
        return {"succes": True, "message": "Mot de passe réinitialisé."}

    def envoyer_email_reinitialisation(self, email: str, reset_url: str) -> bool:
        """Envoie un e-mail contenant le lien de réinitialisation de mot de passe."""
        serveur_smtp = os.getenv("SMTP_SERVER")
        try:
            port_smtp = int(os.getenv("SMTP_PORT", "587"))
        except ValueError:
            port_smtp = 587
            
        utilisateur_smtp = os.getenv("SMTP_USER")
        mot_de_passe_smtp = os.getenv("SMTP_PASSWORD")
        expediteur = os.getenv("SMTP_FROM", utilisateur_smtp)
        
        if not all([serveur_smtp, utilisateur_smtp, mot_de_passe_smtp]):
            self.__logger.error("SMTP non configuré dans les variables d'environnement. Impossible d'envoyer l'e-mail.")
            return False
            
        sujet = "Réinitialisation de votre mot de passe - CTF_LAB"
        
        # Template HTML premium correspondant à la charte graphique de CTF_LAB
        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Réinitialisation de votre mot de passe</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0d1117; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #c9d1d9;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0d1117; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="600" border="0" cellspacing="0" cellpadding="0" style="background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
          <!-- Header -->
          <tr>
            <td align="center" style="background-color: #0d1117; padding: 30px; border-bottom: 2px solid #00e676;">
              <h2 style="margin: 0; color: #00e676; font-size: 24px; letter-spacing: 2px; text-transform: uppercase; font-weight: 700;">CTF_LAB</h2>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding: 40px 30px;">
              <p style="margin-top: 0; font-size: 16px; line-height: 1.6;">Bonjour,</p>
              <p style="font-size: 16px; line-height: 1.6;">Une demande de réinitialisation de mot de passe a été effectuée pour votre compte sur la plateforme CTF_LAB.</p>
              <p style="font-size: 16px; line-height: 1.6;">Pour définir un nouveau mot de passe, veuillez cliquer sur le bouton ci-dessous :</p>
              
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 30px 0;">
                <tr>
                  <td align="center">
                    <a href="{reset_url}" target="_blank" style="display: inline-block; padding: 14px 28px; background-color: #00e676; color: #0d1117; font-weight: bold; text-decoration: none; border-radius: 4px; font-size: 16px; box-shadow: 0 0 10px rgba(0,230,118,0.4); text-transform: uppercase; letter-spacing: 1px;">Réinitialiser mon mot de passe</a>
                  </td>
                </tr>
              </table>
              
              <p style="font-size: 14px; color: #8b949e; line-height: 1.6;">Ce lien est à usage unique et expirera dans <strong>1 heure</strong>.</p>
              <p style="font-size: 14px; color: #8b949e; line-height: 1.6; margin-bottom: 0;">Si vous n'avez pas demandé cette modification, vous pouvez ignorer cet e-mail en toute sécurité.</p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td align="center" style="padding: 20px; background-color: #0d1117; border-top: 1px solid #21262d; font-size: 12px; color: #8b949e;">
              <p style="margin: 0;">© 2026 CTF_LAB — Plateforme d'apprentissage Cybersécurité</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = sujet
        msg["From"] = expediteur
        msg["To"] = email
        msg.attach(MIMEText(html_content, "html"))
        
        try:
            if port_smtp == 465:
                with smtplib.SMTP_SSL(serveur_smtp, port_smtp) as server:
                    server.login(utilisateur_smtp, mot_de_passe_smtp)
                    server.sendmail(expediteur, email, msg.as_string())
            else:
                with smtplib.SMTP(serveur_smtp, port_smtp) as server:
                    server.starttls()
                    server.login(utilisateur_smtp, mot_de_passe_smtp)
                    server.sendmail(expediteur, email, msg.as_string())
            self.__logger.info(f"E-mail de réinitialisation envoyé avec succès à {email}.")
            return True
        except Exception as e:
            self.__logger.error(f"Erreur d'envoi d'e-mail SMTP à {email}: {e}")
            return False

# ══════════════════════════════════════════════════════
#  PATRON OBSERVER : SYSTEME DE NOTIFICATIONS
# ══════════════════════════════════════════════════════

class ObservateurCTF(ABC):
    @abstractmethod
    def notifier(self, evenement: str, user_id: int, defi: Defi, data: dict): pass

class AuditLogObservateur(ObservateurCTF):
    def notifier(self, evenement: str, user_id: int, defi: Defi, data: dict):
        logger = logging.getLogger("AuditCTF")
        if evenement == "FLAG_VALIDE":
            logger.info(f"[AUDIT] Utilisateur {user_id} a résolu {defi.id} !")
        elif evenement == "DEFI_BLOQUE":
            logger.warning(f"[AUDIT] Utilisateur {user_id} a été BLOQUÉ sur {defi.id} !")

class BadgeObservateur(ObservateurCTF):
    def notifier(self, evenement: str, user_id: int, defi: Defi, data: dict):
        if evenement == "FLAG_VALIDE" and defi.points >= 300:
            logging.getLogger("BadgeSystem").info(f"[BADGE] Utilisateur {user_id} : EXTERMINATEUR !")

class ServiceCTF:
    """Service pour la gestion des défis CTF."""
    def __init__(self, challenge_repo: DefiRepository, user_repo: UtilisateurRepository):
        self.__challenge_repo = challenge_repo
        self.__user_repo = user_repo
        self.__defis = {}
        self.__observateurs = []

    def attacher_observateur(self, obs: ObservateurCTF):
        self.__observateurs.append(obs)

    def notifier_tous(self, evenement: str, user_id: int, defi: Defi, data: dict):
        for obs in self.__observateurs:
            obs.notifier(evenement, user_id, defi, data)

    def enregistrer_defi(self, defi: Defi):
        m = self.__challenge_repo.obtenir_par_id(defi.id)
        if not m:
            from models import ChallengeModele, ScoreDegressif
            import json
            
            category = ""
            image_file = None
            tool_used = None
            cipher_text = None
            hints = []
            crypto_category = None
            web_category = None
            evidence_filename = None
            binary_filename = None
            
            from models import DefiStegano, DefiCrypto, DefiWeb, DefiReverse
            if isinstance(defi, DefiStegano):
                category = "stegano"
                image_file = defi._DefiStegano__image_file
                tool_used = defi._DefiStegano__tool_used
            elif isinstance(defi, DefiCrypto):
                category = "crypto"
                cipher_text = defi._DefiCrypto__cipher_text
                hints = defi._DefiCrypto__hints
                crypto_category = defi._DefiCrypto__crypto_category
            elif isinstance(defi, DefiWeb):
                category = "web"
                web_category = defi._DefiWeb__web_category
                hints = defi._DefiWeb__hints
                evidence_filename = defi._DefiWeb__evidence_filename
            elif isinstance(defi, DefiReverse):
                category = "reverse"
                binary_filename = defi._DefiReverse__binary_filename
                hints = defi._DefiReverse__hints

            calc_type = "degressif" if isinstance(defi._Defi__calculateur_score, ScoreDegressif) else "classique"
            
            m = ChallengeModele(
                id=defi.id,
                titre=defi.titre,
                description=defi.description,
                points=defi.points,
                difficulte=defi.difficulte,
                flag_hash=defi._Defi__flag_hash,
                category=category,
                image_file=image_file,
                tool_used=tool_used,
                cipher_text=cipher_text,
                hints=json.dumps(hints),
                crypto_category=crypto_category,
                web_category=web_category,
                evidence_filename=evidence_filename,
                lab_url=defi.lab_url,
                binary_filename=binary_filename,
                calculateur_type=calc_type
            )
            self.__challenge_repo.sauvegarder(m)

    def obtenir_defi(self, challenge_id: str) -> Defi:
        m = self.__challenge_repo.obtenir_par_id(challenge_id)
        if not m: return None
        from models import UsineDefi
        return UsineDefi.creer(m)

    def lister_defis(self, user_id: int) -> list:
        resultats = []
        from models import UsineDefi
        models_list = self.__challenge_repo.obtenir_tous()
        for m in models_list:
            defi = UsineDefi.creer(m)
            d = defi.en_dictionnaire()
            if user_id:
                d["resolu"] = self.__challenge_repo.a_resolu(user_id, defi.id)
                d["tentatives"] = self.__challenge_repo.obtenir_tentatives(user_id, defi.id)
                d["bloque"] = d["tentatives"] >= 10
            else:
                d["resolu"] = False
                d["tentatives"] = 0
                d["bloque"] = False
            resultats.append(d)
        return resultats

    def obtenir_vue_defi(self, challenge_id: str, user_id: int) -> dict:
        defi = self.obtenir_defi(challenge_id)
        if not defi: return None
        d = defi.en_dictionnaire()
        d["resolu"] = self.__challenge_repo.a_resolu(user_id, challenge_id)
        d["tentatives"] = self.__challenge_repo.obtenir_tentatives(user_id, challenge_id)
        d["bloque"] = d["tentatives"] >= 10
        return d

    def soumettre_flag(self, challenge_id: str, attempt: str, user_id: int) -> dict:
        defi = self.obtenir_defi(challenge_id)
        if not defi: return {"succes": False, "message": "Défi introuvable."}
            
        resolu = self.__challenge_repo.a_resolu(user_id, challenge_id)
        tentatives_avant = self.__challenge_repo.obtenir_tentatives(user_id, challenge_id)

        contexte = ContexteDefi(defi, tentatives_avant, resolu)
        try:
            est_correct = contexte.essayer_flag(attempt)
        except (DefiDejaResoluException, DefiBloqueException) as e:
            return {"succes": False, "message": str(e)}

        nouvelles_tentatives = self.__challenge_repo.incrementer_tentatives(user_id, challenge_id)
        self.__challenge_repo.enregistrer_soumission(user_id, challenge_id, est_correct)

        if est_correct:
            points_gagnes = defi.calculer_recompense(tentatives_avant)
            self.__user_repo.ajouter_score(user_id, points_gagnes)
            self.notifier_tous("FLAG_VALIDE", user_id, defi, {"points": points_gagnes})
            return {"succes": True, "message": f"Félicitations ! +{points_gagnes} points !", "points": points_gagnes}
        else:
            if nouvelles_tentatives >= 10:
                self.notifier_tous("DEFI_BLOQUE", user_id, defi, {})
            raise FlagIncorrectException(
                message="Flag incorrect.",
                tentatives=nouvelles_tentatives,
                indice=defi.obtenir_indice(nouvelles_tentatives)
            )
    
    # Getter pour le nombre de défis
    def obtenir_nombre_defis(self) -> int:
        from models import ChallengeModele
        return ChallengeModele.query.count()

    def obtenir_nombre_resolus(self, user_id: int) -> int:
        return self.__challenge_repo.obtenir_nombre_resolus(user_id)

    def obtenir_historique_utilisateur(self, user_id: int) -> list:
        return self.__challenge_repo.obtenir_historique(user_id)
