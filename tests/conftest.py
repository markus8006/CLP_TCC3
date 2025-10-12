# tests/conftest.py - Configuração adaptada para nova estrutura

import pytest
import os
import sys

# Adicionar o diretório raiz ao path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.app import create_app
from src.app.extensions import db
from src.models.Users import User, Role, Permission, role_permissions
from src.models.PLCs import PLC, Organization
from src.models.Registers import Register


@pytest.fixture(scope="function")
def app():
    """Fixture da aplicação Flask para testes"""
    application = create_app('testing')
    
    # Configurações específicas para testes
    application.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "WTF_CSRF_ENABLED": False,  # Desabilita CSRF para testes
        "LOGIN_DISABLED": False,
        "SECRET_KEY": "test-secret-key",
        "CACHE_TYPE": "simple",
    })

    with application.app_context():
        # Criar tabelas
        db.create_all()
        _create_test_roles_and_permissions()
        
        yield application
        
        # Cleanup
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    """Cliente de teste isolado por teste"""
    return app.test_client()


@pytest.fixture(scope="function")
def viewer_role(app):
    """Role VIEWER para testes"""
    return Role.query.filter_by(name='VIEWER').first()


@pytest.fixture(scope="function")
def admin_role(app):
    """Role ADMIN para testes"""
    return Role.query.filter_by(name='ADMIN').first()


@pytest.fixture(scope="function")
def new_user(app, viewer_role):
    """Usuário básico para testes"""
    user = User(
        username="testuser",
        email="test@example.com",
        first_name="Test",
        last_name="User",
        role=viewer_role,
        is_active=True
    )
    user.set_password("testpassword")
    return user


@pytest.fixture(scope="function")
def new_admin(app, admin_role):
    """Usuário admin para testes"""
    admin = User(
        username="adminuser",
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        role=admin_role,
        is_active=True
    )
    admin.set_password("adminpassword")
    return admin


@pytest.fixture(scope="function")
def logged_user(app, client, new_user):
    """Usuário logado para testes que precisam de autenticação"""
    db.session.add(new_user)
    db.session.commit()
    
    # Fazer login
    client.post('/auth/login', data={
        'username': 'testuser',
        'password': 'testpassword'
    })
    
    return new_user


@pytest.fixture(scope="function")
def logged_admin(app, client, new_admin):
    """Admin logado para testes que precisam de permissões admin"""
    db.session.add(new_admin)
    db.session.commit()
    
    # Fazer login
    client.post('/auth/login', data={
        'username': 'adminuser',
        'password': 'adminpassword'
    })
    
    return new_admin


@pytest.fixture(scope="function")
def sample_plc(app):
    """PLC de exemplo para testes"""
    plc = PLC(
        name="Test PLC",
        ip_address="192.168.1.100",
        protocol="modbus",
        port=502,
        description="PLC para testes",
        is_active=True
    )
    return plc


@pytest.fixture(scope="function")
def sample_register(app, sample_plc):
    """Registrador de exemplo para testes"""
    # Salvar PLC primeiro
    db.session.add(sample_plc)
    db.session.commit()
    
    register = Register(
        plc_id=sample_plc.id,
        name="Temperature",
        address="0",
        register_type="holding",
        data_type="int16",
        unit="°C",
        scale_factor=0.1,
        offset=0,
        is_active=True
    )
    return register


@pytest.fixture(scope="function") 
def sample_organization(app):
    """Organização de exemplo para testes"""
    org = Organization(
        name="Test Organization",
        description="Organização para testes"
    )
    return org


def _create_test_roles_and_permissions():
    """Cria roles e permissions básicas para testes"""
    
    # Permissions
    permissions_data = [
        {'name': 'read_plc', 'resource': 'plc', 'action': 'read'},
        {'name': 'create_plc', 'resource': 'plc', 'action': 'create'},
        {'name': 'update_plc', 'resource': 'plc', 'action': 'update'},
        {'name': 'delete_plc', 'resource': 'plc', 'action': 'delete'},
        {'name': 'control_polling', 'resource': 'polling', 'action': 'control'},
        {'name': 'read_alarms', 'resource': 'alarm', 'action': 'read'},
        {'name': 'acknowledge_alarms', 'resource': 'alarm', 'action': 'acknowledge'},
        {'name': 'manage_users', 'resource': 'user', 'action': 'manage'},
        {'name': 'system_admin', 'resource': 'system', 'action': 'admin'},
    ]
    
    permissions = []
    for perm_data in permissions_data:
        perm = Permission(**perm_data)
        permissions.append(perm)
        db.session.add(perm)
    
    # Roles
    viewer_role = Role(
        name='VIEWER',
        description='Apenas visualização'
    )
    admin_role = Role(
        name='ADMIN', 
        description='Administração completa'
    )
    
    db.session.add(viewer_role)
    db.session.add(admin_role)
    db.session.flush()  # Para obter IDs
    
    # Associar permissions aos roles
    # VIEWER: apenas leitura
    viewer_permissions = ['read_plc', 'read_alarms']
    for perm_name in viewer_permissions:
        perm = next(p for p in permissions if p.name == perm_name)
        viewer_role.permissions.append(perm)
    
    # ADMIN: todas as permissions
    for perm in permissions:
        admin_role.permissions.append(perm)
    
    db.session.commit()


# Fixtures para dados de teste mais complexos
@pytest.fixture(scope="function")
def multiple_plcs(app):
    """Múltiplos PLCs para testes de listagem"""
    plcs = []
    for i in range(3):
        plc = PLC(
            name=f"PLC {i+1}",
            ip_address=f"192.168.1.{100+i}",
            protocol="modbus",
            port=502,
            is_active=True
        )
        plcs.append(plc)
        db.session.add(plc)
    
    db.session.commit()
    return plcs


@pytest.fixture(scope="function")
def plc_with_registers(app, sample_plc):
    """PLC com registradores para testes mais complexos"""
    db.session.add(sample_plc)
    db.session.commit()
    
    registers = []
    register_configs = [
        {"name": "Temperature", "address": "0", "unit": "°C"},
        {"name": "Pressure", "address": "1", "unit": "bar"},
        {"name": "Flow", "address": "2", "unit": "L/min"},
    ]
    
    for config in register_configs:
        register = Register(
            plc_id=sample_plc.id,
            name=config["name"],
            address=config["address"],
            register_type="holding",
            data_type="int16",
            unit=config["unit"],
            is_active=True
        )
        registers.append(register)
        db.session.add(register)
    
    db.session.commit()
    return sample_plc, registers