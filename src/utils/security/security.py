from werkzeug.security import generate_password_hash, check_password_hash
import re

class PasswordSecurity:
    @staticmethod
    def validate_password_strength(password):
        """Valida força da senha"""
        checks = {
            'length': len(password) >= 8,
            'uppercase': bool(re.search(r'[A-Z]', password)),
            'lowercase': bool(re.search(r'[a-z]', password)), 
            'digit': bool(re.search(r'\d', password)),
            'special': bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password))
        }
        
        return all(checks.values()), checks
    
    @staticmethod
    def hash_password(password):
        return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)
