"""
Couche Logique Métier (Services)
Implémente le Design Pattern Observer pour les notifications et les logs.
"""
import logging
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
        self.__defis[defi.id] = defi

    def obtenir_defi(self, challenge_id: str) -> Defi:
        return self.__defis.get(challenge_id)

    def lister_defis(self, user_id: int) -> list:
        resultats = []
        for defi in self.__defis.values():
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
        return len(self.__defis)

    def obtenir_nombre_resolus(self, user_id: int) -> int:
        return self.__challenge_repo.obtenir_nombre_resolus(user_id)

    def obtenir_historique_utilisateur(self, user_id: int) -> list:
        return self.__challenge_repo.obtenir_historique(user_id)
