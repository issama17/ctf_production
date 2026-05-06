"""
Data Access Layer (Repositories)
Abstracts database queries behind clean interfaces.
"""
from models import db, UserModel, SubmissionModel, AttemptModel
from typing import Optional, List

class UserRepository:
    """
    Handles database operations for Users.
    """
    def create_user(self, username: str, email: str, pwd_hash: str, role: str = "participant") -> bool:
        """
        + create_user(username, email, pwd_hash, role) -> bool
        Creates a new user in the database.
        """
        try:
            u = UserModel(username=username, email=email, password_hash=pwd_hash, role=role)
            db.session.add(u)
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

    def get_by_email(self, email: str) -> Optional[UserModel]:
        """
        + get_by_email(email) -> Optional[UserModel]
        """
        return UserModel.query.filter_by(email=email).first()

    def get_by_id(self, uid: int) -> Optional[UserModel]:
        """
        + get_by_id(uid) -> Optional[UserModel]
        """
        return db.session.get(UserModel, uid)

    def add_score(self, uid: int, points: int) -> None:
        """
        + add_score(uid, points) -> None
        """
        u = self.get_by_id(uid)
        if u:
            u.score = (u.score or 0) + points
            db.session.commit()

    def update_profile_pic(self, uid: int, url: str) -> None:
        """
        + update_profile_pic(uid, url) -> None
        """
        u = self.get_by_id(uid)
        if u:
            u.profile_pic = url
            db.session.commit()

    def get_scoreboard(self) -> List[UserModel]:
        """
        + get_scoreboard() -> List[UserModel]
        Returns users ordered by score.
        """
        return UserModel.query.order_by(UserModel.score.desc()).all()


class ChallengeRepository:
    """
    Handles database operations for Challenge attempts and submissions.
    """
    def has_solved(self, uid: int, challenge_id: str) -> bool:
        """
        + has_solved(uid, challenge_id) -> bool
        Checks if the user has already solved the challenge.
        """
        return SubmissionModel.query.filter_by(user_id=uid, challenge_id=challenge_id, success=True).first() is not None

    def record_submission(self, uid: int, challenge_id: str, success: bool) -> None:
        """
        + record_submission(uid, challenge_id, success) -> None
        """
        s = SubmissionModel(user_id=uid, challenge_id=challenge_id, success=success)
        db.session.add(s)
        db.session.commit()

    def get_attempts(self, uid: int, challenge_id: str) -> int:
        """
        + get_attempts(uid, challenge_id) -> int
        """
        attempt = AttemptModel.query.filter_by(user_id=uid, challenge_id=challenge_id).first()
        return attempt.attempts_count if attempt else 0

    def increment_attempts(self, uid: int, challenge_id: str) -> int:
        """
        + increment_attempts(uid, challenge_id) -> int
        Increments and returns the attempt count for a user on a specific challenge.
        """
        attempt = AttemptModel.query.filter_by(user_id=uid, challenge_id=challenge_id).first()
        if not attempt:
            attempt = AttemptModel(user_id=uid, challenge_id=challenge_id, attempts_count=1)
            db.session.add(attempt)
        else:
            attempt.attempts_count += 1
        db.session.commit()
        return attempt.attempts_count

    def get_submission_history(self, uid: int) -> List[dict]:
        """
        + get_submission_history(uid) -> List[dict]
        """
        rows = SubmissionModel.query.filter_by(user_id=uid).order_by(SubmissionModel.submission_date.desc()).limit(20).all()
        return [{"challenge_id": r.challenge_id, "success": r.success, "date_soumis": r.submission_date} for r in rows]

    def get_solved_count(self, uid: int) -> int:
        """
        + get_solved_count(uid) -> int
        """
        return SubmissionModel.query.filter_by(user_id=uid, success=True).count()
