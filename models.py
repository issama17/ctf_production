"""
Domain and Data models for the CTF platform.
Adheres to strict OOP principles with proper encapsulation and abstraction.
"""
from abc import ABC, abstractmethod
from datetime import datetime
import hashlib
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy
db = SQLAlchemy()

# ══════════════════════════════════════════════════════
#  ORM MODELS (Data Access Layer)
# ══════════════════════════════════════════════════════

class UserModel(db.Model):
    """
    SQLAlchemy model for the users table (PostgreSQL).
    """
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    score = db.Column(db.Integer, default=0)
    role = db.Column(db.String(32), default="participant")
    registration_date = db.Column(db.String(64), default=lambda: datetime.utcnow().isoformat())
    profile_pic = db.Column(db.String(512), nullable=True, default=None)

    submissions = db.relationship("SubmissionModel", backref="user", lazy=True)
    attempts = db.relationship("AttemptModel", backref="user", lazy=True)

class SubmissionModel(db.Model):
    """
    SQLAlchemy model for successful submissions.
    """
    __tablename__ = "submissions"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    challenge_id = db.Column(db.String(64), nullable=False)
    success = db.Column(db.Boolean, nullable=False)
    submission_date = db.Column(db.String(64), default=lambda: datetime.utcnow().isoformat())

class AttemptModel(db.Model):
    """
    SQLAlchemy model for tracking attempts per user per challenge.
    Fixes the security/logic flaw where attempts were global per challenge.
    """
    __tablename__ = "attempts"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    challenge_id = db.Column(db.String(64), nullable=False)
    attempts_count = db.Column(db.Integer, default=0)


# ══════════════════════════════════════════════════════
#  DOMAIN MODELS (Business Logic Layer)
# ══════════════════════════════════════════════════════

class User(UserMixin, ABC):
    """
    Abstract Base Class representing a User entity.
    
    Attributes:
        # _id: int
        # _username: str
        # _email: str
        # _password_hash: str
        # _score: int
        # _registration_date: str
        # _profile_pic: str
    """
    def __init__(self, user_model: UserModel):
        self._id = user_model.id
        self._username = user_model.username
        self._email = user_model.email
        self._password_hash = user_model.password_hash
        self._score = user_model.score
        self._registration_date = user_model.registration_date
        self._profile_pic = user_model.profile_pic

    @property
    def id(self) -> int:
        return self._id

    @property
    def username(self) -> str:
        return self._username

    @property
    def email(self) -> str:
        return self._email

    @property
    def score(self) -> int:
        return self._score

    @property
    def profile_pic(self) -> str:
        return self._profile_pic

    def get_id(self) -> str:
        """Required by Flask-Login."""
        return str(self.id)

    def verify_password(self, password: str) -> bool:
        """
        + verify_password(password: str) -> bool
        Validates the given password against the stored hash.
        """
        return self.hash_password(password) == self._password_hash

    @staticmethod
    def hash_password(password: str) -> str:
        """
        + hash_password(password: str) -> str
        Hashes a password using SHA-256.
        """
        return hashlib.sha256(password.encode()).hexdigest()

    @abstractmethod
    def get_role(self) -> str:
        """
        + get_role() -> str
        Returns the role of the user (e.g., 'participant', 'admin').
        """
        pass

class Participant(User):
    """
    Concrete class for standard participants.
    """
    def get_role(self) -> str:
        return "participant"

class Admin(User):
    """
    Concrete class for administrators.
    """
    def get_role(self) -> str:
        return "admin"

class Challenge(ABC):
    """
    Abstract Base Class representing a CTF Challenge.
    
    Attributes:
        # _id: str
        # _title: str
        # _description: str
        # _points: int
        # _difficulty: str
        # _flag_hash: str
    """
    def __init__(self, identifier: str, title: str, description: str, points: int, difficulty: str, flag_hash: str):
        self._id = identifier
        self._title = title
        self._description = description
        self._points = points
        self._difficulty = difficulty
        self._flag_hash = flag_hash

    @property
    def id(self) -> str:
        return self._id
    
    @property
    def title(self) -> str:
        return self._title
    
    @property
    def description(self) -> str:
        return self._description
    
    @property
    def points(self) -> int:
        return self._points
    
    @property
    def difficulty(self) -> str:
        return self._difficulty

    def validate_flag(self, attempt: str) -> bool:
        """
        + validate_flag(attempt: str) -> bool
        Validates the flag attempt against the stored hash.
        """
        return hashlib.sha256(attempt.strip().encode()).hexdigest() == self._flag_hash

    @abstractmethod
    def get_hint(self, attempts_count: int) -> str:
        """
        + get_hint(attempts_count: int) -> str
        Returns a hint based on the number of attempts.
        """
        pass

    @abstractmethod
    def to_dict(self) -> dict:
        """
        + to_dict() -> dict
        Serializes the challenge for frontend templates.
        """
        pass

class SteganoChallenge(Challenge):
    """
    Concrete class representing a Steganography Challenge.
    
    Attributes:
        - __image_file: str
        - __tool_used: str
    """
    def __init__(self, identifier: str, title: str, description: str, points: int, difficulty: str, flag_hash: str, image_file: str, tool_used: str):
        super().__init__(identifier, title, description, points, difficulty, flag_hash)
        self.__image_file = image_file
        self.__tool_used = tool_used

    def get_hint(self, attempts_count: int) -> str:
        if attempts_count < 3: return "Le secret se cache dans les pixels..."
        if attempts_count < 6: return f"Essayez d'extraire avec {self.__tool_used}."
        return f"Commande : {self.__tool_used} extract -sf {self.__image_file} -p [mot_de_passe]"

    def to_dict(self) -> dict:
        return {
            "id": self._id,
            "titre": self._title,
            "description": self._description,
            "points": self._points,
            "difficulte": self._difficulty,
            "type": "stegano",
            "fichier": self.__image_file,
            "outil": self.__tool_used
        }

class CryptoChallenge(Challenge):
    """
    Concrete class representing a Cryptography Challenge.
    
    Attributes:
        - __cipher_text: str
        - __hints: list
        - __crypto_category: str
    """
    def __init__(self, identifier: str, title: str, description: str, points: int, difficulty: str, flag_hash: str, cipher_text: str, hints: list, crypto_category: str):
        super().__init__(identifier, title, description, points, difficulty, flag_hash)
        self.__cipher_text = cipher_text
        self.__hints = hints
        self.__crypto_category = crypto_category

    def get_hint(self, attempts_count: int) -> str:
        if not self.__hints: return ""
        idx = min(attempts_count // 3, len(self.__hints) - 1)
        return self.__hints[idx]

    def to_dict(self) -> dict:
        return {
            "id": self._id,
            "titre": self._title,
            "description": self._description,
            "points": self._points,
            "difficulte": self._difficulty,
            "type": "crypto",
            "texte_chiffre": self.__cipher_text,
            "categorie_crypto": self.__crypto_category
        }

class UserFactory:
    """
    Factory class to create domain User objects from UserModel entities.
    """
    @staticmethod
    def create(user_model: UserModel) -> User:
        """
        + create(user_model: UserModel) -> User
        Instantiates the correct User subclass based on role.
        """
        if user_model.role == "admin":
            return Admin(user_model)
        return Participant(user_model)
