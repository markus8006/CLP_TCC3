# 👨‍💻 Guia de Desenvolvimento

## 🏗️ Arquitetura do Sistema

### Padrões Arquiteturais
- **Application Factory Pattern**: Flask app criado via função factory
- **Blueprint Pattern**: Modularização por funcionalidades
- **Repository Pattern**: Abstração de acesso a dados
- **Adapter Pattern**: Comunicação com diferentes protocolos
- **Service Layer**: Lógica de negócios separada da apresentação

### Estrutura de Camadas
```
┌─────────────────────────────────────────────┐
│                 Presentation Layer          │
│  (Templates, Static Files, Web Routes)     │
├─────────────────────────────────────────────┤
│                 API Layer                   │
│       (REST Endpoints, Serialization)      │
├─────────────────────────────────────────────┤
│                Service Layer                │
│  (Business Logic, Polling, Alarms, etc.)   │
├─────────────────────────────────────────────┤
│               Repository Layer              │
│        (Data Access, ORM, Queries)         │
├─────────────────────────────────────────────┤
│                 Model Layer                 │
│      (SQLAlchemy Models, Validation)       │
├─────────────────────────────────────────────┤
│                Adapter Layer                │
│    (Protocol Adapters: Modbus, S7, etc.)   │
└─────────────────────────────────────────────┘
```

## 🚀 Setup de Desenvolvimento

### Pré-requisitos
```bash
# Python 3.8+
python --version

# Git
git --version

# Editor de código (recomendado: VS Code)
code --version
```

### Configuração do Ambiente
```bash
# 1. Clonar repositório
git clone https://github.com/seu-usuario/CLP_TCC2.git
cd CLP_TCC2

# 2. Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou
.venv\Scripts\activate     # Windows

# 3. Instalar dependências de desenvolvimento
pip install -r requirements/development.txt

# 4. Configurar ambiente de desenvolvimento
cp .env.example .env
# Editar .env com configurações de desenvolvimento

# 5. Instalar hooks de pre-commit
pre-commit install

# 6. Inicializar banco de desenvolvimento
python scripts/init_db.py

# 7. Executar testes
python -m pytest

# 8. Executar aplicação
python run.py
```

### Configuração do VS Code
Criar `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./.venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.sortImports.args": ["--profile", "black"],
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    }
}
```

## 📝 Padrões de Código

### Estilo de Código
- **PEP 8**: Padrão oficial Python
- **Black**: Formatação automática
- **isort**: Ordenação de imports
- **Type Hints**: Sempre usar quando possível

### Exemplo de Classe de Serviço
```python
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.extensions import db
from app.models.plc import PLC
from app.models.data_log import DataLog

class DataService:
    """Serviço para manipulação de dados históricos"""
    
    def __init__(self):
        self.db = db
    
    def get_historical_data(
        self, 
        plc_id: int, 
        start_date: datetime, 
        end_date: datetime,
        register_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca dados históricos com filtros
        
        Args:
            plc_id: ID do PLC
            start_date: Data inicial
            end_date: Data final  
            register_ids: Lista de IDs dos registradores (opcional)
        
        Returns:
            Lista de dados históricos
            
        Raises:
            ValueError: Se as datas são inválidas
        """
        if start_date >= end_date:
            raise ValueError("Data inicial deve ser menor que data final")
            
        query = DataLog.query.filter(
            DataLog.plc_id == plc_id,
            DataLog.timestamp.between(start_date, end_date)
        )
        
        if register_ids:
            query = query.filter(DataLog.register_id.in_(register_ids))
            
        return [log.to_dict() for log in query.all()]
```

### Exemplo de Blueprint
```python
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from app.auth.decorators import require_permission
from app.services.data_service import DataService

# Criar blueprint
data_bp = Blueprint('data', __name__, url_prefix='/data')

# Instanciar serviço
data_service = DataService()

@data_bp.route('/history/<int:plc_id>')
@login_required
@require_permission('read_data')
def get_history(plc_id: int):
    """Endpoint para dados históricos"""
    try:
        # Validar parâmetros
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({'error': 'Datas são obrigatórias'}), 400
            
        # Chamar serviço
        data = data_service.get_historical_data(plc_id, start_date, end_date)
        
        return jsonify({
            'success': True,
            'data': data,
            'total': len(data)
        })
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Erro ao buscar dados: {e}")
        return jsonify({'error': 'Erro interno'}), 500
```

## 🧪 Testes

### Estrutura de Testes
```
tests/
├── conftest.py          # Configurações globais
├── fixtures/            # Dados de teste
│   └── sample_data.py
├── unit/               # Testes unitários
│   ├── test_models.py
│   ├── test_services.py
│   └── test_utils.py
├── integration/        # Testes de integração
│   ├── test_api.py
│   └── test_polling.py
└── e2e/               # Testes end-to-end
    └── test_workflows.py
```

### Configuração de Testes (conftest.py)
```python
import pytest
from app import create_app
from app.extensions import db
from app.models.user import User, Role

@pytest.fixture
def app():
    """Fixture da aplicação Flask"""
    app = create_app('testing')
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    """Fixture do cliente de teste"""
    return app.test_client()

@pytest.fixture
def admin_user(app):
    """Fixture de usuário admin"""
    with app.app_context():
        role = Role(name='ADMIN', description='Administrator')
        db.session.add(role)
        db.session.flush()
        
        user = User(
            username='test_admin',
            email='admin@test.com',
            first_name='Test',
            last_name='Admin',
            role_id=role.id
        )
        user.set_password('testpass')
        db.session.add(user)
        db.session.commit()
        
        return user
```

### Exemplo de Teste Unitário
```python
import pytest
from app.services.data_service import DataService
from app.models.plc import PLC
from datetime import datetime, timedelta

class TestDataService:
    """Testes para DataService"""
    
    def test_get_historical_data_success(self, app, admin_user):
        """Teste busca de dados históricos com sucesso"""
        with app.app_context():
            # Arrange
            service = DataService()
            plc = PLC(name='Test PLC', ip_address='127.0.0.1', protocol='modbus')
            db.session.add(plc)
            db.session.commit()
            
            start_date = datetime.now() - timedelta(hours=1)
            end_date = datetime.now()
            
            # Act
            result = service.get_historical_data(plc.id, start_date, end_date)
            
            # Assert
            assert isinstance(result, list)
    
    def test_get_historical_data_invalid_dates(self, app):
        """Teste com datas inválidas"""
        with app.app_context():
            service = DataService()
            start_date = datetime.now()
            end_date = start_date - timedelta(hours=1)
            
            with pytest.raises(ValueError):
                service.get_historical_data(1, start_date, end_date)
```

### Exemplo de Teste de API
```python
import json

class TestPLCAPI:
    """Testes para API de PLCs"""
    
    def test_create_plc_success(self, client, admin_user):
        """Teste criação de PLC via API"""
        # Login
        response = client.post('/api/auth/login', json={
            'username': 'test_admin',
            'password': 'testpass'
        })
        token = response.json['access_token']
        
        # Criar PLC
        response = client.post('/api/plcs', 
            headers={'Authorization': f'Bearer {token}'},
            json={
                'name': 'Test PLC',
                'ip_address': '192.168.1.100',
                'protocol': 'modbus',
                'port': 502
            }
        )
        
        assert response.status_code == 201
        data = response.json
        assert data['name'] == 'Test PLC'
        assert data['ip_address'] == '192.168.1.100'
    
    def test_create_plc_unauthorized(self, client):
        """Teste criação sem autenticação"""
        response = client.post('/api/plcs', json={
            'name': 'Test PLC',
            'ip_address': '192.168.1.100'
        })
        
        assert response.status_code == 401
```

### Executando Testes
```bash
# Todos os testes
python -m pytest

# Testes com coverage
python -m pytest --cov=app

# Testes específicos
python -m pytest tests/unit/test_models.py

# Testes com output detalhado
python -m pytest -v -s

# Testes em paralelo
python -m pytest -n auto
```

## 🔧 Ferramentas de Desenvolvimento

### Linting e Formatação
```bash
# Black (formatação)
black app/ tests/

# isort (organizar imports)
isort app/ tests/

# flake8 (linting)
flake8 app/ tests/

# pylint (análise de código)
pylint app/

# mypy (verificação de tipos)
mypy app/
```

### Pre-commit Hooks
Arquivo `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 22.3.0
    hooks:
      - id: black

  - repo: https://github.com/PyCQA/isort
    rev: 5.10.1
    hooks:
      - id: isort
        args: ["--profile", "black"]

  - repo: https://github.com/PyCQA/flake8
    rev: 4.0.1
    hooks:
      - id: flake8

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v0.950
    hooks:
      - id: mypy
```

### Debugging
```python
# Usando pdb
import pdb; pdb.set_trace()

# Usando Flask debug toolbar (desenvolvimento)
from flask_debugtoolbar import DebugToolbarExtension
toolbar = DebugToolbarExtension(app)

# Logs detalhados
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📊 Monitoramento e Profiling

### Profiling de Performance
```python
from flask import g
import time

@app.before_request
def before_request():
    g.start_time = time.time()

@app.after_request
def after_request(response):
    duration = time.time() - g.start_time
    if duration > 0.5:  # Log requests lentas
        app.logger.warning(f"Slow request: {request.path} took {duration:.2f}s")
    return response
```

### Métricas Customizadas
```python
from prometheus_client import Counter, Histogram, generate_latest

# Métricas
REQUEST_COUNT = Counter('requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_DURATION = Histogram('request_duration_seconds', 'Request duration')

@app.route('/metrics')
def metrics():
    return generate_latest()
```

## 🔌 Polling Python

- O polling agora vive em `src/services/polling/polling_service.py` e é iniciado automaticamente em `create_app`. Cada CLP recebe uma *thread* dedicada (`CLPWorker`).
- Os drivers são simples (`ModbusDriver`, `S7Driver`, `OPCUADriver`) e expõem apenas três métodos (`conectar`, `ler`, `desconectar`). Qualquer protocolo adicional pode seguir o mesmo formato dentro de `src/services/drivers`.
- Leituras são gravadas diretamente via `DataRepo.registrar_leitura`, eliminando filas JSON, gRPC e binários externos.

## 📦 Build e Deploy

### Build da Aplicação
```bash
# Instalar dependências de build
pip install build

# Criar pacote
python -m build

# Instalar localmente
pip install dist/scada-2.0.0-py3-none-any.whl
```

### Docker
```dockerfile
# Dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wsgi:app"]
```

### CI/CD Pipeline (GitHub Actions)
```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    
    - name: Install dependencies
      run: |
        pip install -r requirements/testing.txt
    
    - name: Run tests
      run: |
        python -m pytest --cov=app
    
    - name: Upload coverage
      uses: codecov/codecov-action@v1
```

## 🐛 Debug e Troubleshooting

### Logs Estruturados
```python
import structlog

logger = structlog.get_logger()

# Log com contexto
logger.info("PLC connected", plc_id=1, ip="192.168.1.100")
logger.error("Connection failed", plc_id=1, error="timeout")
```

### Debugging de Polling
```python
# Adicionar logs detalhados no PollingManager
def _polling_worker(self, plc_id, job, stop_event):
    logger.info("Starting polling worker", plc_id=plc_id)
    
    while not stop_event.is_set():
        try:
            start_time = time.time()
            # ... lógica de polling
            elapsed = time.time() - start_time
            logger.debug("Polling cycle completed", 
                        plc_id=plc_id, 
                        elapsed=elapsed,
                        registers_read=len(readings))
        except Exception as e:
            logger.error("Polling error", plc_id=plc_id, error=str(e))
```

### Performance Monitoring
```python
# Decorator para monitorar performance
def monitor_performance(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        
        logger.info("Function executed", 
                   function=func.__name__,
                   duration=duration)
        return result
    return wrapper
```