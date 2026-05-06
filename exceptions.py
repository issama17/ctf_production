"""
Exceptions personnalisées pour le domaine CTF.
Démontre une hiérarchie d'erreurs orientée objet.
"""

class CTFException(Exception):
    """Exception de base pour toutes les erreurs métier du CTF."""
    pass

class FlagIncorrectException(CTFException):
    """Levée quand le flag soumis est incorrect."""
    def __init__(self, message, tentatives, indice):
        super().__init__(message)
        self.tentatives = tentatives
        self.indice = indice

class DefiBloqueException(CTFException):
    """Levée quand le joueur a dépassé le nombre maximum de tentatives."""
    pass

class DefiDejaResoluException(CTFException):
    """Levée quand le joueur a déjà résolu le défi."""
    pass
