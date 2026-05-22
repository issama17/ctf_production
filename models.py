"""
Modèles de domaine et de données pour la plateforme CTF.
Réécrit selon les principes du cours (Partie 2) : Encapsulation, Héritage et Polymorphisme.
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
#  PATRON STRATEGY : Statut Utilisateur
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

class ChallengeModele(db.Model):
    __tablename__ = "challenges"
    id = db.Column(db.String(64), primary_key=True)
    titre = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=False)
    points = db.Column(db.Integer, nullable=False)
    difficulte = db.Column(db.String(32), nullable=False)
    flag_hash = db.Column(db.String(256), nullable=False)
    category = db.Column(db.String(32), nullable=False)  # 'stegano', 'crypto', 'web', 'reverse'
    
    # Category-specific fields
    image_file = db.Column(db.String(255), nullable=True)
    tool_used = db.Column(db.String(64), nullable=True)
    cipher_text = db.Column(db.Text, nullable=True)
    hints = db.Column(db.Text, nullable=True)  # Store JSON-serialized list of hints
    crypto_category = db.Column(db.String(128), nullable=True)
    web_category = db.Column(db.String(128), nullable=True)
    evidence_filename = db.Column(db.String(255), nullable=True)
    lab_url = db.Column(db.String(255), nullable=True)
    binary_filename = db.Column(db.String(255), nullable=True)
    calculateur_type = db.Column(db.String(32), default="classique")  # 'classique' or 'degressif'


# ══════════════════════════════════════════════════════
#  MODÈLES DE DOMAINE (Logique Métier & Encapsulation)
# ══════════════════════════════════════════════════════

class CalculateurScore(ABC):
    @abstractmethod
    def calculer(self, points_base: int, tentatives: int) -> int: pass

class ScoreClassique(CalculateurScore):
    def calculer(self, points_base: int, tentatives: int) -> int: return points_base

class ScoreDegressif(CalculateurScore):
    def calculer(self, points_base: int, tentatives: int) -> int:
        perte = min(tentatives * 0.10, 0.50)
        return int(points_base * (1 - perte))

class Utilisateur(UserMixin, ABC):
    def __init__(self, user_modele: UserModele):
        # Encapsulation stricte : Attributs privés (double underscore)
        self.__id = user_modele.id
        self.__username = user_modele.username
        self.__email = user_modele.email
        self.__password_hash = user_modele.password_hash
        self.__score = user_modele.score or 0
        self.__registration_date = user_modele.registration_date
        self.__profile_pic = user_modele.profile_pic
        self.__statut_obj = FabriqueStatut.creer(user_modele.statut)
        self.__experience = user_modele.experience

    # Accesseurs (Getters) pour maintenir la compatibilité templates
    @property
    def id(self): return self.__id
    @property
    def username(self): return self.__username
    @property
    def email(self): return self.__email
    @property
    def score(self): return self.__score
    @property
    def profile_pic(self): return self.__profile_pic
    @property
    def experience(self): return self.__experience
    @property
    def date_inscription(self): return self.__registration_date
    @property
    def registration_date(self): return self.__registration_date
    
    @property
    def statut_nom(self): return self.__statut_obj.obtenir_nom()
    @property
    def statut_couleur(self): return self.__statut_obj.obtenir_couleur()

    def get_id(self): return str(self.__id)

    def verifier_mot_de_passe(self, password: str) -> bool:
        from werkzeug.security import check_password_hash
        h = self.__password_hash
        if h.startswith("pbkdf2:") or h.startswith("scrypt:") or h.startswith("bcrypt:"):
            return check_password_hash(h, password)
        return hashlib.sha256(password.encode()).hexdigest() == h

    @staticmethod
    def hacher_mot_de_passe(password: str) -> str:
        from werkzeug.security import generate_password_hash
        return generate_password_hash(password)

    @abstractmethod
    def obtenir_role(self) -> str: pass

class Participant(Utilisateur):
    def obtenir_role(self) -> str: return "participant"

class Administrateur(Utilisateur):
    def obtenir_role(self) -> str: return "admin"

class UsineUtilisateur:
    @staticmethod
    def creer(user_modele: UserModele) -> Utilisateur:
        if user_modele.role == "admin": return Administrateur(user_modele)
        return Participant(user_modele)

class UsineDefi:
    @staticmethod
    def creer(m: ChallengeModele) -> 'Defi':
        import json
        calc = ScoreDegressif() if m.calculateur_type == "degressif" else ScoreClassique()
        
        try:
            hints = json.loads(m.hints) if m.hints else []
        except Exception:
            hints = []
            
        if m.category == "stegano":
            return DefiStegano(
                identifiant=m.id, titre=m.titre, description=m.description,
                points=m.points, difficulte=m.difficulte, flag_hash=m.flag_hash,
                image_file=m.image_file, tool_used=m.tool_used, calculateur_score=calc
            )
        elif m.category == "crypto":
            return DefiCrypto(
                identifiant=m.id, titre=m.titre, description=m.description,
                points=m.points, difficulte=m.difficulte, flag_hash=m.flag_hash,
                cipher_text=m.cipher_text, hints=hints, crypto_category=m.crypto_category,
                calculateur_score=calc
            )
        elif m.category == "web":
            return DefiWeb(
                identifiant=m.id, titre=m.titre, description=m.description,
                points=m.points, difficulte=m.difficulte, flag_hash=m.flag_hash,
                web_category=m.web_category, hints=hints, evidence_filename=m.evidence_filename,
                calculateur_score=calc, lab_url=m.lab_url
            )
        elif m.category == "reverse":
            return DefiReverse(
                identifiant=m.id, titre=m.titre, description=m.description,
                points=m.points, difficulte=m.difficulte, flag_hash=m.flag_hash,
                binary_filename=m.binary_filename, hints=hints, calculateur_score=calc
            )
        else:
            raise ValueError(f"Catégorie de défi inconnue: {m.category}")


class Defi(ABC):
    def __init__(self, identifiant, titre, description, points, difficulte, flag_hash, calculateur_score=None, lab_url=None):
        self.__id = identifiant
        self.__titre = titre
        self.__description = description
        self.__points = points
        self.__difficulte = difficulte
        self.__flag_hash = flag_hash
        self.__calculateur_score = calculateur_score or ScoreClassique()
        self.__lab_url = lab_url

    # Getters
    @property
    def id(self): return self.__id
    @property
    def titre(self): return self.__titre
    @property
    def description(self): return self.__description
    @property
    def points(self): return self.__points
    @property
    def difficulte(self): return self.__difficulte
    @property
    def lab_url(self): return self.__lab_url

    def valider_flag(self, tentative: str) -> bool:
        return hashlib.sha256(tentative.strip().encode()).hexdigest() == self.__flag_hash

    def calculer_recompense(self, tentatives: int) -> int:
        return self.__calculateur_score.calculer(self.__points, tentatives)

    @abstractmethod
    def obtenir_indice(self, attempts_count: int) -> str: pass

    @abstractmethod
    def en_dictionnaire(self) -> dict: pass

class DefiStegano(Defi):
    def __init__(self, identifiant, titre, description, points, difficulte, flag_hash, image_file, tool_used, calculateur_score=None):
        super().__init__(identifiant, titre, description, points, difficulte, flag_hash, calculateur_score)
        self.__image_file = image_file
        self.__tool_used = tool_used

    def obtenir_indice(self, attempts_count: int) -> str:
        if attempts_count < 3: return "Le secret se cache dans les pixels..."
        if attempts_count < 6: return f"Essayez d'extraire avec {self.__tool_used}."
        return f"Commande : {self.__tool_used} extract -sf {self.__image_file}"

    def en_dictionnaire(self) -> dict:
        return {
            "id": self.id, "titre": self.titre, "description": self.description,
            "points": self.points, "difficulte": self.difficulte,
            "type": "stegano", "fichier": self.__image_file, "outil": self.__tool_used
        }

class DefiCrypto(Defi):
    def __init__(self, identifiant, titre, description, points, difficulte, flag_hash, cipher_text, hints, crypto_category, calculateur_score=None):
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
            "id": self.id, "titre": self.titre, "description": self.description,
            "points": self.points, "difficulte": self.difficulte,
            "type": "crypto", "texte_chiffre": self.__cipher_text, "categorie_crypto": self.__crypto_category
        }

class DefiWeb(Defi):
    def __init__(self, identifiant, titre, description, points, difficulte, flag_hash, web_category, hints, evidence_filename, calculateur_score=None, lab_url=None):
        super().__init__(identifiant, titre, description, points, difficulte, flag_hash, calculateur_score, lab_url)
        self.__web_category = web_category
        self.__hints = hints
        self.__evidence_filename = evidence_filename

    def obtenir_indice(self, attempts_count: int) -> str:
        if not self.__hints: return ""
        idx = min(attempts_count // 3, len(self.__hints) - 1)
        return self.__hints[idx]

    def en_dictionnaire(self) -> dict:
        return {
            "id": self.id, "titre": self.titre, "description": self.description,
            "points": self.points, "difficulte": self.difficulte,
            "type": "web", "categorie_web": self.__web_category, "evidence_file": self.__evidence_filename, "lab_url": self.lab_url
        }

class DefiReverse(Defi):
    def __init__(self, identifiant, titre, description, points, difficulte, flag_hash, binary_filename, hints, calculateur_score=None):
        super().__init__(identifiant, titre, description, points, difficulte, flag_hash, calculateur_score)
        self.__binary_filename = binary_filename
        self.__hints = hints

    def obtenir_indice(self, attempts_count: int) -> str:
        if not self.__hints: return ""
        idx = min(attempts_count // 3, len(self.__hints) - 1)
        return self.__hints[idx]

    def en_dictionnaire(self) -> dict:
        return {
            "id": self.id, "titre": self.titre, "description": self.description,
            "points": self.points, "difficulte": self.difficulte,
            "type": "reverse", "fichier": self.__binary_filename
        }

# State Pattern pour la gestion des tentatives
class EtatDefi(ABC):
    @abstractmethod
    def soumettre(self, contexte, tentative: str) -> bool: pass

class EtatDisponible(EtatDefi):
    def soumettre(self, contexte, tentative: str) -> bool:
        if contexte.defi.valider_flag(tentative):
            contexte.changer_etat(EtatResolu())
            return True
        contexte.incrementer_tentatives()
        if contexte.tentatives >= 10: contexte.changer_etat(EtatBloque())
        return False

class EtatBloque(EtatDefi):
    def soumettre(self, contexte, tentative: str): 
        raise DefiBloqueException("Nombre maximal de tentatives atteint. Ce défi est bloqué.")

class EtatResolu(EtatDefi):
    def soumettre(self, contexte, tentative: str): 
        raise DefiDejaResoluException("Vous avez déjà résolu ce défi !")

class ContexteDefi:
    def __init__(self, defi: Defi, tentatives: int, resolu: bool):
        self.defi = defi
        self.tentatives = tentatives
        if resolu: self.etat = EtatResolu()
        elif tentatives >= 10: self.etat = EtatBloque()
        else: self.etat = EtatDisponible()

    def changer_etat(self, nouvel_etat: EtatDefi): self.etat = nouvel_etat
    def incrementer_tentatives(self): self.tentatives += 1
    def essayer_flag(self, tentative: str) -> bool: return self.etat.soumettre(self, tentative)
