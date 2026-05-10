"""
Couche Logique Métier (Services)
Intègre le Design Pattern Observer pour les notifications et les logs.
"""
import logging
from abc import ABC, abstractmethod
from models import Utilisateur, UsineUtilisateur, Defi, ContexteDefi
from repository import UtilisateurRepository, DefiRepository
from exceptions import DefiBloqueException, DefiDejaResoluException, FlagIncorrectException

class ServiceAuth:
    """Service pour l'authentification et l'inscription."""
    def __init__(self, user_repo: UtilisateurRepository, base_url: str):
        self._user_repo = user_repo
        self._base_url = base_url
        self._logger = logging.getLogger(self.__class__.__name__)

    def inscrire(self, username: str, email: str, password: str, statut: str = "Étudiant", experience: str = "Débutant") -> dict:
        if len(username) < 3:
            return {"succes": False, "message": "Le nom doit faire au moins 3 caractères."}
        if len(password) < 6:
            return {"succes": False, "message": "Le mot de passe doit faire au moins 6 caractères."}
        if "@" not in email:
            return {"succes": False, "message": "Email invalide."}
            
        if self._user_repo.obtenir_par_email(email):
            return {"succes": False, "message": "Cet email est déjà utilisé."}
            
        pwd_hash = Utilisateur.hacher_mot_de_passe(password)
        
        # Le premier utilisateur inscrit devient admin automatiquement
        total_users = len(self._user_repo.obtenir_classement())
        role = "admin" if total_users == 0 else "participant"
        
        success = self._user_repo.creer_utilisateur(username, email, pwd_hash, role, statut, experience)
        
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

    def mettre_a_jour_profil(self, uid: int, username: str, email: str) -> dict:
        if len(username) < 3:
            return {"succes": False, "message": "Le nom doit faire au moins 3 caractères."}
        if "@" not in email:
            return {"succes": False, "message": "Email invalide."}
            
        success = self._user_repo.mettre_a_jour_profil(uid, username, email)
        if not success:
            return {"succes": False, "message": "Cet email ou nom d'utilisateur est déjà pris."}
        return {"succes": True, "message": "Profil mis à jour avec succès."}

    def reinitialiser_mot_de_passe(self, email: str, new_password: str) -> dict:
        if len(new_password) < 6:
            return {"succes": False, "message": "Le mot de passe doit faire au moins 6 caractères."}
        pwd_hash = Utilisateur.hacher_mot_de_passe(new_password)
        success = self._user_repo.mettre_a_jour_mot_de_passe(email, pwd_hash)
        if not success:
            return {"succes": False, "message": "Aucun utilisateur trouvé avec cet email."}
        return {"succes": True, "message": "Mot de passe réinitialisé avec succès."}

# ══════════════════════════════════════════════════════
#  PATRON OBSERVER : SYSTEME DE NOTIFICATIONS
# ══════════════════════════════════════════════════════

class ObservateurCTF(ABC):
    @abstractmethod
    def notifier(self, evenement: str, user_id: int, defi: Defi, data: dict):
        pass

class AuditLogObservateur(ObservateurCTF):
    def __init__(self):
        self.logger = logging.getLogger("AuditCTF")
    
    def notifier(self, evenement: str, user_id: int, defi: Defi, data: dict):
        if evenement == "FLAG_VALIDE":
            points = data.get('points', 0)
            self.logger.info(f"[AUDIT] Utilisateur {user_id} a résolu {defi.id} (+{points} pts) !")
        elif evenement == "DEFI_BLOQUE":
            self.logger.warning(f"[AUDIT ALERTE] Utilisateur {user_id} a été BLOQUÉ sur {defi.id} (Trop de tentatives) !")

class BadgeObservateur(ObservateurCTF):
    def __init__(self):
        self.logger = logging.getLogger("BadgeSystem")
        
    def notifier(self, evenement: str, user_id: int, defi: Defi, data: dict):
        if evenement == "FLAG_VALIDE" and defi.points >= 300:
            self.logger.info(f"[BADGE] Utilisateur {user_id} a débloqué le badge : EXTERMINATEUR DE DEFIS !")


class ServiceCTF:
    """Service pour la gestion des défis CTF."""
    def __init__(self, challenge_repo: DefiRepository, user_repo: UtilisateurRepository):
        self._challenge_repo = challenge_repo
        self._user_repo = user_repo
        self._defis = {}
        self._observateurs = []
        self._logger = logging.getLogger(self.__class__.__name__)

    def attacher_observateur(self, obs: ObservateurCTF):
        self._observateurs.append(obs)

    def notifier_tous(self, evenement: str, user_id: int, defi: Defi, data: dict):
        for obs in self._observateurs:
            obs.notifier(evenement, user_id, defi, data)

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
            
        resolu = self._challenge_repo.a_resolu(user_id, challenge_id)
        tentatives_avant = self._challenge_repo.obtenir_tentatives(user_id, challenge_id)

        # Utilisation du patron State pour gérer la soumission
        contexte = ContexteDefi(defi, tentatives_avant, resolu)

        try:
            est_correct = contexte.essayer_flag(attempt)
        except DefiDejaResoluException as e:
            return {"succes": True, "message": str(e), "points": 0, "deja_resolu": True, "code": 200}
        except DefiBloqueException as e:
            return {"succes": False, "message": str(e), "code": 429}

        # Sauvegarde en BDD
        nouvelles_tentatives = self._challenge_repo.incrementer_tentatives(user_id, challenge_id)
        self._challenge_repo.enregistrer_soumission(user_id, challenge_id, est_correct)

        if est_correct:
            # Calcul des points selon le patron Strategy
            points_gagnes = defi.calculer_recompense(tentatives_avant)
            self._user_repo.ajouter_score(user_id, points_gagnes)
            
            # Notification Observer
            self.notifier_tous("FLAG_VALIDE", user_id, defi, {"points": points_gagnes})
            return {"succes": True, "message": f"Félicitations ! +{points_gagnes} points !", "points": points_gagnes, "code": 200}
        else:
            if nouvelles_tentatives >= 10:
                self.notifier_tous("DEFI_BLOQUE", user_id, defi, {})
                
            raise FlagIncorrectException(
                message="Flag incorrect. Continuez à chercher...",
                tentatives=nouvelles_tentatives,
                indice=defi.obtenir_indice(nouvelles_tentatives)
            )
