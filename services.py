"""
Couche Logique Métier (Services)
"""
import logging
from models import Utilisateur, UsineUtilisateur, Defi
from repository import UtilisateurRepository, DefiRepository

class ServiceAuth:
    """Service pour l'authentification et l'inscription."""
    def __init__(self, user_repo: UtilisateurRepository, base_url: str):
        self._user_repo = user_repo
        self._base_url = base_url
        self._logger = logging.getLogger(self.__class__.__name__)

    def inscrire(self, username: str, email: str, password: str) -> dict:
        if len(username) < 3:
            return {"succes": False, "message": "Le nom doit faire au moins 3 caractères."}
        if len(password) < 6:
            return {"succes": False, "message": "Le mot de passe doit faire au moins 6 caractères."}
        if "@" not in email:
            return {"succes": False, "message": "Email invalide."}
        
        pwd_hash = Utilisateur.hacher_mot_de_passe(password)
        success = self._user_repo.creer_utilisateur(username, email, pwd_hash)
        
        if not success:
            return {"succes": False, "message": "Email ou nom d'utilisateur déjà utilisé."}
        
        return {"succes": True, "message": "Inscription réussie ! Vous pouvez vous connecter."}

    def connecter(self, email: str, password: str) -> dict:
        row = self._user_repo.obtenir_par_email(email)
        if not row:
            return {"succes": False, "message": "Email ou mot de passe incorrect."}
        
        utilisateur = UsineUtilisateur.creer(row)
        if not utilisateur.verifier_mot_de_passe(password):
            return {"succes": False, "message": "Email ou mot de passe incorrect."}
            
        return {"succes": True, "utilisateur": utilisateur}

    def charger_utilisateur(self, uid: int) -> Utilisateur:
        row = self._user_repo.obtenir_par_id(uid)
        return UsineUtilisateur.creer(row) if row else None


class ServiceCTF:
    """Service pour la gestion des défis CTF."""
    def __init__(self, challenge_repo: DefiRepository, user_repo: UtilisateurRepository):
        self._challenge_repo = challenge_repo
        self._user_repo = user_repo
        self._defis = {}
        self._logger = logging.getLogger(self.__class__.__name__)

    def enregistrer_defi(self, defi: Defi) -> None:
        self._defis[defi.id] = defi

    def obtenir_defi(self, challenge_id: str) -> Defi:
        return self._defis.get(challenge_id)

    def lister_defis(self, user_id: int) -> list:
        resultats = []
        for defi in self._defis.values():
            d = defi.en_dictionnaire()
            if user_id:
                d["resolu"] = self._challenge_repo.a_resolu(user_id, defi.id)
                d["tentatives"] = self._challenge_repo.obtenir_tentatives(user_id, defi.id)
                d["bloque"] = d["tentatives"] >= 10
            else:
                d["resolu"] = False
                d["tentatives"] = 0
                d["bloque"] = False
            resultats.append(d)
        return resultats

    def obtenir_vue_defi(self, challenge_id: str, user_id: int) -> dict:
        defi = self.obtenir_defi(challenge_id)
        if not defi:
            return None
        
        d = defi.en_dictionnaire()
        d["resolu"] = self._challenge_repo.a_resolu(user_id, challenge_id)
        d["tentatives"] = self._challenge_repo.obtenir_tentatives(user_id, challenge_id)
        d["bloque"] = d["tentatives"] >= 10
        return d

    def soumettre_flag(self, challenge_id: str, attempt: str, user_id: int) -> dict:
        defi = self.obtenir_defi(challenge_id)
        if not defi:
            return {"succes": False, "message": "Défi introuvable.", "code": 404}
            
        if self._challenge_repo.a_resolu(user_id, challenge_id):
            return {"succes": True, "message": "Vous avez déjà résolu ce défi !", "points": 0, "deja_resolu": True, "code": 200}
            
        attempts = self._challenge_repo.obtenir_tentatives(user_id, challenge_id)
        if attempts >= 10:
            return {"succes": False, "message": "Trop de tentatives. Défi bloqué.", "code": 429}

        attempts = self._challenge_repo.incrementer_tentatives(user_id, challenge_id)
        
        is_correct = defi.valider_flag(attempt)
        self._challenge_repo.enregistrer_soumission(user_id, challenge_id, is_correct)

        if is_correct:
            self._user_repo.ajouter_score(user_id, defi.points)
            return {"succes": True, "message": f"Félicitations ! +{defi.points} points !", "points": defi.points, "code": 200}
            
        return {
            "succes": False, 
            "message": "Flag incorrect. Continuez à chercher...",
            "indice": defi.obtenir_indice(attempts), 
            "tentatives": attempts, 
            "code": 200
        }
