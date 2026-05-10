"""
Modèles de domaine et de données pour la plateforme CTF.
Intègre les Design Patterns Strategy et State pour une architecture POO avancée.
"""
from abc import ABC, abstractmethod
from datetime import datetime
import hashlib
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

from exceptions import DefiBloqueException, DefiDejaResoluException

# Initialisation de SQLAlchemy
db = SQLAlchemy()

# ══════════════════════════════════════════════════════
#  PATRON STRATEGY / FACTORY : Statut Utilisateur
# ══════════════════════════════════════════════════════
class StatutUtilisateur(ABC):
    @abstractmethod
    def obtenir_nom(self) -> str: pass
    @abstractmethod
    def obtenir_couleur(self) -> str: pass

class StatutEtudiant(StatutUtilisateur):
    def obtenir_nom(self) -> str: return "Étudiant"
    def obtenir_couleur(self) -> str: return "var(--cyan)"

class StatutProfesseur(StatutUtilisateur):
    def obtenir_nom(self) -> str: return "Professeur"
    def obtenir_couleur(self) -> str: return "var(--yellow)"

class StatutExterne(StatutUtilisateur):
    def obtenir_nom(self) -> str: return "Externe"
    def obtenir_couleur(self) -> str: return "var(--text-dim)"

class FabriqueStatut:
    @staticmethod
    def creer(statut_str: str) -> StatutUtilisateur:
        if statut_str == "Professeur": return StatutProfesseur()
        if statut_str == "Externe": return StatutExterne()
        return StatutEtudiant()

# ══════════════════════════════════════════════════════
#  MODÈLES ORM (Couche d'accès aux données)
# ══════════════════════════════════════════════════════

class UserModele(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    score = db.Column(db.Integer, default=0)
    role = db.Column(db.String(32), default="participant")
    registration_date = db.Column(db.String(64), default=lambda: datetime.utcnow().isoformat())
    profile_pic = db.Column(db.String(512), nullable=True, default=None)
    statut = db.Column(db.String(64), nullable=True, default="Étudiant")
    experience = db.Column(db.String(32), nullable=True, default="Débutant")

    submissions = db.relationship("SubmissionModele", backref="user", lazy=True)
    attempts = db.relationship("AttemptModele", backref="user", lazy=True)

class SubmissionModele(db.Model):
    __tablename__ = "submissions"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    challenge_id = db.Column(db.String(64), nullable=False)
    success = db.Column(db.Boolean, nullable=False)
    submission_date = db.Column(db.String(64), default=lambda: datetime.utcnow().isoformat())

class AttemptModele(db.Model):
    __tablename__ = "attempts"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    challenge_id = db.Column(db.String(64), nullable=False)
    attempts_count = db.Column(db.Integer, default=0)


# ══════════════════════════════════════════════════════
#  PATRON STRATEGY : CALCULATEUR DE SCORE
# ══════════════════════════════════════════════════════

class CalculateurScore(ABC):
    @abstractmethod
    def calculer(self, points_base: int, tentatives: int) -> int:
        pass

class ScoreClassique(CalculateurScore):
    """Donne toujours le nombre de points par défaut."""
    def calculer(self, points_base: int, tentatives: int) -> int:
        return points_base

class ScoreDegressif(CalculateurScore):
    """Diminue les points de 10% par tentative ratée (maximum 50% de perte)."""
    def calculer(self, points_base: int, tentatives: int) -> int:
        perte = min(tentatives * 0.10, 0.50)
        return int(points_base * (1 - perte))


# ══════════════════════════════════════════════════════
#  MODÈLES DE DOMAINE (Couche Logique)
# ══════════════════════════════════════════════════════

class Utilisateur(UserMixin, ABC):
    def __init__(self, user_modele: UserModele):
        self._id = user_modele.id
        self._username = user_modele.username
        self._email = user_modele.email
        self._password_hash = user_modele.password_hash
        self._score = user_modele.score or 0
        self._registration_date = user_modele.registration_date
        self._profile_pic = user_modele.profile_pic
        self._statut_obj = FabriqueStatut.creer(user_modele.statut)
        self._experience = user_modele.experience

    @property
    def id(self) -> int: return self._id
    @property
    def username(self) -> str: return self._username
    @property
    def email(self) -> str: return self._email
    @property
    def score(self) -> int: return self._score
    @property
    def profile_pic(self) -> str: return self._profile_pic
    
    @property
    def statut_nom(self) -> str: return self._statut_obj.obtenir_nom()
    @property
    def statut_couleur(self) -> str: return self._statut_obj.obtenir_couleur()
    
    @property
    def experience(self) -> str: return self._experience

    @property
    def date_inscription(self) -> str:
        return self._registration_date

    def get_id(self) -> str:
        return str(self.id)

    def verifier_mot_de_passe(self, password: str) -> bool:
        return self.hacher_mot_de_passe(password) == self._password_hash

    @staticmethod
    def hacher_mot_de_passe(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    @abstractmethod
    def obtenir_role(self) -> str:
        pass

class Participant(Utilisateur):
    def obtenir_role(self) -> str:
        return "participant"

class Administrateur(Utilisateur):
    def obtenir_role(self) -> str:
        return "admin"

class Defi(ABC):
    def __init__(self, identifiant: str, titre: str, description: str, points: int, difficulte: str, flag_hash: str, calculateur_score: CalculateurScore = None, lab_url: str = None):
        self._id = identifiant
        self._titre = titre
        self._description = description
        self._points = points
        self._difficulte = difficulte
        self._flag_hash = flag_hash
        self._calculateur_score = calculateur_score or ScoreClassique()
        self._lab_url = lab_url

    @property
    def id(self) -> str: return self._id
    @property
    def titre(self) -> str: return self._titre
    @property
    def description(self) -> str: return self._description
    @property
    def points(self) -> int: return self._points
    @property
    def difficulte(self) -> str: return self._difficulte
    @property
    def lab_url(self) -> str: return self._lab_url

    def valider_flag(self, tentative: str) -> bool:
        return hashlib.sha256(tentative.strip().encode()).hexdigest() == self._flag_hash

    def calculer_recompense(self, tentatives: int) -> int:
        """Calcule les points selon le patron Strategy."""
        return self._calculateur_score.calculer(self._points, tentatives)

    @abstractmethod
    def obtenir_indice(self, attempts_count: int) -> str:
        pass

    @abstractmethod
    def en_dictionnaire(self) -> dict:
        pass

class DefiStegano(Defi):
    def __init__(self, identifiant: str, titre: str, description: str, points: int, difficulte: str, flag_hash: str, image_file: str, tool_used: str, calculateur_score: CalculateurScore = None):
        super().__init__(identifiant, titre, description, points, difficulte, flag_hash, calculateur_score)
        self.__image_file = image_file
        self.__tool_used = tool_used

    def obtenir_indice(self, attempts_count: int) -> str:
        if attempts_count < 3: return "Le secret se cache dans les pixels..."
        if attempts_count < 6: return f"Essayez d'extraire avec {self.__tool_used}."
        return f"Commande : {self.__tool_used} extract -sf {self.__image_file} -p [mot_de_passe]"

    def en_dictionnaire(self) -> dict:
        return {
            "id": self._id, "titre": self._titre, "description": self._description,
            "points": self._points, "difficulte": self._difficulte,
            "type": "stegano", "fichier": self.__image_file, "outil": self.__tool_used
        }

class DefiCrypto(Defi):
    def __init__(self, identifiant: str, titre: str, description: str, points: int, difficulte: str, flag_hash: str, cipher_text: str, hints: list, crypto_category: str, calculateur_score: CalculateurScore = None):
        super().__init__(identifiant, titre, description, points, difficulte, flag_hash, calculateur_score)
        self.__cipher_text = cipher_text
        self.__hints = hints
        self.__crypto_category = crypto_category

    def obtenir_indice(self, attempts_count: int) -> str:
        if not self.__hints: return ""
        idx = min(attempts_count // 3, len(self.__hints) - 1)
        return self.__hints[idx]

    def en_dictionnaire(self) -> dict:
        return {
            "id": self._id, "titre": self._titre, "description": self._description,
            "points": self._points, "difficulte": self._difficulte,
            "type": "crypto", "texte_chiffre": self.__cipher_text, "categorie_crypto": self.__crypto_category
        }

class DefiWeb(Defi):
    """
    Défi de type Web / Forensique HTTP.
    Le joueur analyse des artefacts réseau (logs, tokens JWT, configs)
    pour reconstituer l'attaque et en extraire le flag.
    """

    def __init__(
        self,
        identifiant: str,
        titre: str,
        description: str,
        points: int,
        difficulte: str,
        flag_hash: str,
        web_category: str,
        hints: list,
        evidence_filename: str,
        calculateur_score: CalculateurScore = None,
        lab_url: str = None,
    ):
        super().__init__(identifiant, titre, description, points, difficulte, flag_hash, calculateur_score, lab_url)
        self.__web_category   = web_category
        self.__hints          = hints
        self.__evidence_filename = evidence_filename

    @property
    def evidence_filename(self) -> str:
        return self.__evidence_filename

    @property
    def web_category(self) -> str:
        return self.__web_category

    def obtenir_indice(self, attempts_count: int) -> str:
        if not self.__hints:
            return ""
        idx = min(attempts_count // 3, len(self.__hints) - 1)
        return self.__hints[idx]

    def en_dictionnaire(self) -> dict:
        return {
            "id":               self._id,
            "titre":            self._titre,
            "description":      self._description,
            "points":           self._points,
            "difficulte":       self._difficulte,
            "type":             "web",
            "categorie_web":    self.__web_category,
            "evidence_file":    self.__evidence_filename,
            "lab_url":          self._lab_url,
        }

class UsineUtilisateur:
    @staticmethod
    def creer(user_modele: UserModele) -> Utilisateur:
        if user_modele.role == "admin":
            return Administrateur(user_modele)
        return Participant(user_modele)


# ══════════════════════════════════════════════════════
#  PATRON STATE : ETAT DE RESOLUTION DU DEFI
# ══════════════════════════════════════════════════════

class EtatDefi(ABC):
    @abstractmethod
    def soumettre(self, contexte, tentative: str) -> bool:
        pass

class EtatDisponible(EtatDefi):
    def soumettre(self, contexte, tentative: str) -> bool:
        if contexte.defi.valider_flag(tentative):
            contexte.changer_etat(EtatResolu())
            return True
        else:
            contexte.incrementer_tentatives()
            if contexte.tentatives >= 10:
                contexte.changer_etat(EtatBloque())
            return False

class EtatBloque(EtatDefi):
    def soumettre(self, contexte, tentative: str) -> bool:
        raise DefiBloqueException("Trop de tentatives. Ce défi est bloqué pour vous.")

class EtatResolu(EtatDefi):
    def soumettre(self, contexte, tentative: str) -> bool:
        raise DefiDejaResoluException("Vous avez déjà résolu ce défi !")

class ContexteDefi:
    """Gère le contexte d'un défi pour un utilisateur spécifique selon le patron State."""
    def __init__(self, defi: Defi, tentatives: int, resolu: bool):
        self.defi = defi
        self.tentatives = tentatives
        if resolu:
            self.etat = EtatResolu()
        elif tentatives >= 10:
            self.etat = EtatBloque()
        else:
            self.etat = EtatDisponible()

    def changer_etat(self, nouvel_etat: EtatDefi):
        self.etat = nouvel_etat

    def incrementer_tentatives(self):
        self.tentatives += 1

    def essayer_flag(self, tentative: str) -> bool:
        return self.etat.soumettre(self, tentative)
