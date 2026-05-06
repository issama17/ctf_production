"""
Business Logic Layer (Services)
Contains domain logic, interacting with Repositories and Domain Models.
"""
import logging

from models import User, UserFactory, Challenge
from repository import UserRepository, ChallengeRepository


class AuthService:
    """
    Service for user authentication and registration.
    """
    def __init__(self, user_repo: UserRepository, base_url: str):
        self._user_repo = user_repo
        self._base_url = base_url
        self._logger = logging.getLogger(self.__class__.__name__)

    def register(self, username: str, email: str, password: str) -> dict:
        """
        + register(username, email, password) -> dict
        """
        if len(username) < 3:
            return {"succes": False, "message": "Le nom doit faire au moins 3 caractères."}
        if len(password) < 6:
            return {"succes": False, "message": "Le mot de passe doit faire au moins 6 caractères."}
        if "@" not in email:
            return {"succes": False, "message": "Email invalide."}
        
        pwd_hash = User.hash_password(password)
        success = self._user_repo.create_user(username, email, pwd_hash)
        
        if not success:
            return {"succes": False, "message": "Email ou nom d'utilisateur déjà utilisé."}
        
        return {"succes": True, "message": "Inscription réussie ! Vous pouvez vous connecter."}

    def login(self, email: str, password: str) -> dict:
        """
        + login(email, password) -> dict
        """
        row = self._user_repo.get_by_email(email)
        if not row:
            return {"succes": False, "message": "Email ou mot de passe incorrect."}
        
        user = UserFactory.create(row)
        if not user.verify_password(password):
            return {"succes": False, "message": "Email ou mot de passe incorrect."}
        

            
        return {"succes": True, "utilisateur": user}

    def load_user(self, uid: int) -> User:
        """
        + load_user(uid) -> User
        """
        row = self._user_repo.get_by_id(uid)
        return UserFactory.create(row) if row else None


class CTFService:
    """
    Service for managing CTF challenges and submissions.
    """
    def __init__(self, challenge_repo: ChallengeRepository, user_repo: UserRepository):
        self._challenge_repo = challenge_repo
        self._user_repo = user_repo
        self._challenges = {}
        self._logger = logging.getLogger(self.__class__.__name__)

    def register_challenge(self, challenge: Challenge) -> None:
        """
        + register_challenge(challenge: Challenge) -> None
        """
        self._challenges[challenge.id] = challenge

    def get_challenge(self, challenge_id: str) -> Challenge:
        """
        + get_challenge(challenge_id: str) -> Challenge
        """
        return self._challenges.get(challenge_id)

    def list_challenges(self, user_id: int) -> list:
        """
        + list_challenges(user_id: int) -> list
        Returns all challenges with user-specific state appended.
        """
        results = []
        for challenge in self._challenges.values():
            d = challenge.to_dict()
            if user_id:
                d["resolu"] = self._challenge_repo.has_solved(user_id, challenge.id)
                d["tentatives"] = self._challenge_repo.get_attempts(user_id, challenge.id)
                d["bloque"] = d["tentatives"] >= 10
            else:
                d["resolu"] = False
                d["tentatives"] = 0
                d["bloque"] = False
            results.append(d)
        return results

    def get_challenge_view(self, challenge_id: str, user_id: int) -> dict:
        """
        + get_challenge_view(challenge_id, user_id) -> dict
        Returns a single challenge with user-specific state.
        """
        challenge = self.get_challenge(challenge_id)
        if not challenge:
            return None
        
        d = challenge.to_dict()
        d["resolu"] = self._challenge_repo.has_solved(user_id, challenge_id)
        d["tentatives"] = self._challenge_repo.get_attempts(user_id, challenge_id)
        d["bloque"] = d["tentatives"] >= 10
        return d

    def submit_flag(self, challenge_id: str, attempt: str, user_id: int) -> dict:
        """
        + submit_flag(challenge_id, attempt, user_id) -> dict
        """
        challenge = self.get_challenge(challenge_id)
        if not challenge:
            return {"succes": False, "message": "Défi introuvable.", "code": 404}
            
        if self._challenge_repo.has_solved(user_id, challenge_id):
            return {"succes": True, "message": "Vous avez déjà résolu ce défi !", "points": 0, "deja_resolu": True, "code": 200}
            
        attempts = self._challenge_repo.get_attempts(user_id, challenge_id)
        if attempts >= 10:
            return {"succes": False, "message": "Trop de tentatives. Défi bloqué.", "code": 429}

        # Increment user attempts
        attempts = self._challenge_repo.increment_attempts(user_id, challenge_id)
        
        is_correct = challenge.validate_flag(attempt)
        self._challenge_repo.record_submission(user_id, challenge_id, is_correct)

        if is_correct:
            self._user_repo.add_score(user_id, challenge.points)
            return {"succes": True, "message": f"Félicitations ! +{challenge.points} points !", "points": challenge.points, "code": 200}
            
        return {
            "succes": False, 
            "message": "Flag incorrect. Continuez à chercher...",
            "indice": challenge.get_hint(attempts), 
            "tentatives": attempts, 
            "code": 200
        }
