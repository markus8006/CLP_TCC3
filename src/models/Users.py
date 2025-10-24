from src.app import db
from datetime import datetime, timezone
import enum
from werkzeug.security import generate_password_hash, check_password_hash


class UserRole(enum.Enum):
    USER = 'user'
    MODERATOR = 'moderator'
    ADMIN = 'admin'


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.USER)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)

    def is_admin(self):
        return self.role == UserRole.ADMIN
    
    def is_moderator(self):
        return self.role == UserRole.MODERATOR
    
    def is_user(self):
        return self.role == UserRole.USER
    
    def has_permission(self, min_role):

        hierarchy = {
            UserRole.USER: 1,
            UserRole.MODERATOR: 2,
            UserRole.ADMIN: 3
        }
    
        if isinstance(min_role, str):
            try: 
                min_role = UserRole(min_role)
            except:
                raise ValueError(f"Role: {min_role} invalida")
        user_level = hierarchy.get(self.role, 0)
        required_level = hierarchy.get(min_role, 0)
        return user_level >= required_level
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_authenticated(self):
        return self.is_active

    def get_id(self):
        return self.id