"""
Couche d'Accès aux Données (Repositories)
Abstrait les requêtes de base de données.
"""
from models import db, UserModele, SubmissionModele, AttemptModele
from typing import Optional, List

class UtilisateurRepository:
    """
    Gère les opérations de base de données pour les Utilisateurs.
    """
    def creer_utilisateur(self, username: str, email: str, pwd_hash: str, role: str = "participant", statut: str = "Étudiant", experience: str = "Débutant") -> bool:
        """Crée un nouvel utilisateur."""
        try:
            u = UserModele(username=username, email=email, password_hash=pwd_hash, role=role, statut=statut, experience=experience)
            db.session.add(u)
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

    def obtenir_par_email(self, email: str) -> Optional[UserModele]:
        return UserModele.query.filter_by(email=email).first()

    def obtenir_par_id(self, uid: int) -> Optional[UserModele]:
        return db.session.get(UserModele, uid)

    def ajouter_score(self, uid: int, points: int) -> None:
        u = self.obtenir_par_id(uid)
        if u:
            u.score = (u.score or 0) + points
            db.session.commit()

    def mettre_a_jour_photo(self, uid: int, url: str) -> None:
        u = self.obtenir_par_id(uid)
        if u:
            u.profile_pic = url
            db.session.commit()

    def obtenir_classement(self) -> List[UserModele]:
        return UserModele.query.order_by(UserModele.score.desc()).all()

    def mettre_a_jour_profil(self, uid: int, username: str, email: str) -> bool:
        u = self.obtenir_par_id(uid)
        if u:
            existing = UserModele.query.filter((UserModele.email == email) | (UserModele.username == username)).first()
            if existing and existing.id != uid:
                return False
            u.username = username
            u.email = email
            db.session.commit()
            return True
        return False

    def mettre_a_jour_mot_de_passe(self, email: str, pwd_hash: str) -> bool:
        u = self.obtenir_par_email(email)
        if u:
            u.password_hash = pwd_hash
            db.session.commit()
            return True
        return False


class DefiRepository:
    """
    Gère les opérations de base de données pour les défis et soumissions.
    """
    def a_resolu(self, uid: int, challenge_id: str) -> bool:
        return SubmissionModele.query.filter_by(user_id=uid, challenge_id=challenge_id, success=True).first() is not None

    def enregistrer_soumission(self, uid: int, challenge_id: str, success: bool) -> None:
        s = SubmissionModele(user_id=uid, challenge_id=challenge_id, success=success)
        db.session.add(s)
        db.session.commit()

    def obtenir_tentatives(self, uid: int, challenge_id: str) -> int:
        attempt = AttemptModele.query.filter_by(user_id=uid, challenge_id=challenge_id).first()
        return attempt.attempts_count if attempt else 0

    def incrementer_tentatives(self, uid: int, challenge_id: str) -> int:
        attempt = AttemptModele.query.filter_by(user_id=uid, challenge_id=challenge_id).first()
        if not attempt:
            attempt = AttemptModele(user_id=uid, challenge_id=challenge_id, attempts_count=1)
            db.session.add(attempt)
        else:
            attempt.attempts_count += 1
        db.session.commit()
        return attempt.attempts_count

    def obtenir_historique(self, uid: int) -> List[dict]:
        rows = SubmissionModele.query.filter_by(user_id=uid).order_by(SubmissionModele.submission_date.desc()).limit(20).all()
        return [{"challenge_id": r.challenge_id, "type": r.challenge_id.split('_')[0], "success": r.success, "date_soumis": r.submission_date} for r in rows]

    def obtenir_nombre_resolus(self, uid: int) -> int:
        return SubmissionModele.query.filter_by(user_id=uid, success=True).count()
