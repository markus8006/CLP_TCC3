from cryptography.fernet import Fernet
import os

class DataEncryption:
    def __init__(self):
        key = os.environ.get('ENCRYPTION_KEY') or Fernet.generate_key()
        self.cipher = Fernet(key)
    
    def encrypt_sensitive_data(self, data):
        """Criptografa dados sensíveis como senhas de PLCs"""
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt_sensitive_data(self, encrypted_data):
        """Descriptografa dados sensíveis"""
        return self.cipher.decrypt(encrypted_data.encode()).decode()
