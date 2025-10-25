# /clp_app/users/auth_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError

from src.app.routes.login_routes.forms_auht import LoginForm, RegistrationForm
from src.models.Users import User, UserRole
from src.utils import role_required
from src.app import db 

# Cria um Blueprint para as rotas de autenticação
auth_bp = Blueprint('auth', __name__)




@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Utilizador ou senha inválidos.', 'danger')
            return redirect(url_for('auth.login'))
        
        login_user(user)
        # Redireciona para a página principal (que está no blueprint 'main')
        return redirect(url_for('main.index'))
    
    return render_template('users_page/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sessão encerrada.', 'info')
    return redirect(url_for('auth.login'))



@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Flag para saber se ainda não existe nenhum utilizador
    first_user = (User.query.count() == 0)

    # Se não for o primeiro utilizador, apenas ADMIN autenticado pode registar novos
    if not first_user:
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('O registo de novos utilizadores está desabilitado. Apenas o administrador pode criar utilizadores.', 'warning')
            return redirect(url_for('auth.login'))

    form = RegistrationForm()
    if form.validate_on_submit():
        # guarda o estado actual (evita recálculo depois do commit)
        was_first = first_user

        # definir papel: primeiro -> ADMIN, senão usar o escolhido no form
        role = UserRole.ADMIN if was_first else UserRole(form.user_type.data)

        user = User(username=form.username.data, role=role, email=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            flash('Erro ao registar: nome de utilizador já existe', 'danger')
            return render_template('users_page/register.html', form=form, first_user=first_user)

        if was_first:
            flash('Primeiro utilizador (Administrador) registado com sucesso! Por favor, faça o login.', 'success')
        else:
            flash('Novo utilizador registado com sucesso!', 'success')

        return redirect(url_for('auth.login'))

    return render_template('users_page/register.html', form=form, first_user=first_user)