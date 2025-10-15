# tests/conftest.py
import pytest
from src.app import create_app   # ajuste se seu create_app está em outro módulo
from src.app.extensions import db as _db
from sqlalchemy import event

# Repos (assumimos que você já salvou o arquivo de repositórios em src/repos/repositories.py)
from src.repository.PLC_repository import PLCRepo
from src.repository.Registers_repository import RegisterRepo
from src.repository.Data_repository import DataLogRepo

# Tentar importar modelos de localizações possíveis

from src.models.PLCs import PLC
from src.models.Registers import Register
from src.models.Data import DataLog



@pytest.fixture(scope="session")
def app():
    """Cria a aplicação Flask em modo testing (session scope)."""
    app = create_app('testing')

    # Forçar configurações específicas para teste
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "WTF_CSRF_ENABLED": False,
        "LOGIN_DISABLED": False,
        "SECRET_KEY": "test-secret-key",
    })

    # criar contexto da app
    ctx = app.app_context()
    ctx.push()

    yield app

    ctx.pop()


@pytest.fixture(scope="function")
def db(app):
    """Cria todas as tabelas antes do teste e remove depois (function scope)."""
    _db.create_all()
    yield _db
    _db.session.remove()
    _db.drop_all()


@pytest.fixture(scope="function")
def client(app, db):
    """Test client usando a app e DB em memória."""
    return app.test_client()


# Repositories (utilizam db.session por padrão)
@pytest.fixture(scope="function")
def plc_repo(db):
    return PLCRepo(session=_db.session)


@pytest.fixture(scope="function")
def register_repo(db):
    return RegisterRepo(session=_db.session)


@pytest.fixture(scope="function")
def datalog_repo(db):
    return DataLogRepo(session=_db.session)
