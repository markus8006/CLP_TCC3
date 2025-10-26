from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, EmailField
from wtforms.validators import DataRequired, EqualTo, ValidationError
from src.models.Users import User, UserRole
from flask_wtf import FlaskForm
from wtforms import SubmitField

class DeleteForm(FlaskForm):
    submit = SubmitField('Excluir')


class LoginForm(FlaskForm):
    username = StringField('Usuário', validators=[DataRequired()])
    password = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Entrar')

ROLE_CHOICES = [
    (UserRole.USER.value, 'Utilizador Padrão'),
    (UserRole.ALARM_DEFINITION.value, 'Gestor de Alarmes'),
    (UserRole.MODERATOR.value, 'Moderador'),
    (UserRole.ADMIN.value, 'Administrador'),
]


class RegistrationForm(FlaskForm):
    username = StringField('Usuário', validators=[DataRequired()])
    password = PasswordField('Senha', validators=[DataRequired()])
    email = EmailField('Email', validators=[DataRequired()])
    password2 = PasswordField(
        'Repetir Senha', validators=[DataRequired(), EqualTo('password', message='As senhas devem ser iguais.')])
    user_type = SelectField(
        'Tipo de Conta',
        choices=ROLE_CHOICES,
        validators=[DataRequired()]
    )

    submit = SubmitField('Registrar')

    def validate_username(self, username):
        """Verifica se o nome de usuário já existe no banco de dados."""
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Este nome de usuário já está em uso. Por favor, escolha outro.')