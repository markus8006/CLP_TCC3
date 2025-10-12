# 🔧 Troubleshooting - Solução de Problemas

## 🚨 Problemas Comuns e Soluções

### Problemas de Instalação

#### Python/Pip Issues
**Problema:** `pip install` falha com erros de compilação
```bash
# Solução: Instalar dependências de desenvolvimento
# Ubuntu/Debian
sudo apt-get install python3-dev build-essential libffi-dev libssl-dev

# CentOS/RHEL
sudo yum groupinstall "Development Tools"
sudo yum install python3-devel libffi-devel openssl-devel
```

**Problema:** Erro de permissão no pip
```bash
# Solução: Usar usuário virtual environment
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

#### Dependências Snap7
**Problema:** `ImportError: snap7.dll not found` (Windows)
```bash
# Solução: 
1. Baixar snap7 library de https://snap7.sourceforge.net/
2. Extrair snap7.dll para uma pasta no PATH
3. Ou colocar na pasta do projeto
```

**Problema:** `libsnap7.so not found` (Linux)
```bash
# Ubuntu/Debian
sudo apt-get install libsnap7-1 libsnap7-dev

# Ou instalar manualmente:
wget https://github.com/gijzelaerr/python-snap7/files/2432652/snap7-full-1.4.2.tar.gz
tar -xzf snap7-full-1.4.2.tar.gz
cd snap7-full-1.4.2/build/unix
make -f x86_64_linux.mk
sudo cp ../bin/x86_64-linux/libsnap7.so /usr/lib/
```

### Problemas de Banco de Dados

#### SQLite Locked
**Problema:** `database is locked`
```python
# Solução: Verificar conexões pendentes
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    db.session.close()
    db.engine.dispose()
```

#### PostgreSQL Connection Issues
**Problema:** `FATAL: password authentication failed`
```bash
# Verificar configurações
sudo -u postgres psql
\l  # Listar bancos
\du # Listar usuários

# Recriar usuário se necessário
DROP USER IF EXISTS scada_user;
CREATE USER scada_user WITH PASSWORD 'nova_senha';
GRANT ALL PRIVILEGES ON DATABASE scada TO scada_user;
```

**Problema:** `could not connect to server`
```bash
# Verificar se PostgreSQL está rodando
sudo systemctl status postgresql
sudo systemctl start postgresql

# Verificar configuração de rede
sudo grep -n "listen_addresses" /etc/postgresql/*/main/postgresql.conf
sudo grep -n "port" /etc/postgresql/*/main/postgresql.conf
```

### Problemas de Comunicação com PLCs

#### Modbus TCP Issues
**Problema:** `ConnectionException: Modbus Error: [Connection] Failed to connect`
```python
# Debug step-by-step
import socket

def test_tcp_connection(host, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"✅ Conexão TCP OK para {host}:{port}")
            return True
        else:
            print(f"❌ Não foi possível conectar em {host}:{port}")
            return False
    except Exception as e:
        print(f"❌ Erro na conexão: {e}")
        return False

# Testar conectividade
test_tcp_connection('192.168.1.100', 502)
```

**Problema:** `ModbusIOException: Modbus Error: [Invalid Message]`
```python
# Verificar configurações do Modbus
from pymodbus.client.sync import ModbusTcpClient

client = ModbusTcpClient('192.168.1.100', port=502)
client.connect()

# Testar leitura simples
try:
    result = client.read_holding_registers(0, 1, unit=1)
    if result.isError():
        print(f"Erro Modbus: {result}")
    else:
        print(f"Valor lido: {result.registers[0]}")
except Exception as e:
    print(f"Erro na leitura: {e}")
finally:
    client.close()
```

#### Siemens S7 Issues
**Problema:** `S7 Communication Error`
```python
# Debug S7 connection
import snap7
from snap7.util import *

def test_s7_connection(ip, rack=0, slot=1):
    plc = snap7.client.Client()
    
    try:
        plc.connect(ip, rack, slot)
        print(f"✅ Conectado ao S7 PLC em {ip}")
        
        # Testar leitura de DB
        data = plc.db_read(1, 0, 2)  # DB1, offset 0, 2 bytes
        value = get_int(data, 0)
        print(f"Valor lido do DB1: {value}")
        
        return True
    except Exception as e:
        print(f"❌ Erro S7: {e}")
        return False
    finally:
        plc.disconnect()

# Testar
test_s7_connection('192.168.1.100')
```

### Problemas de Polling

#### Polling Not Starting
**Problema:** Polling não inicia ou para inesperadamente
```python
# Debug no PollingManager
import logging
logging.basicConfig(level=logging.DEBUG)

# Verificar logs específicos
tail -f logs/polling.log | grep ERROR

# Verificar se PLC está configurado corretamente
from app import create_app
from app.models.plc import PLC
from app.models.register import Register

app = create_app()
with app.app_context():
    plc = PLC.query.filter_by(ip_address='192.168.1.100').first()
    if plc:
        print(f"PLC encontrado: {plc.name}")
        print(f"Protocolo: {plc.protocol}")
        print(f"Registradores ativos: {len([r for r in plc.registers if r.is_active])}")
    else:
        print("PLC não encontrado no banco de dados")
```

#### High CPU Usage in Polling
**Problema:** CPU alto durante polling
```python
# Ajustar intervalos e timeouts
# Em app/config.py
class Config:
    POLLING_DEFAULT_INTERVAL = 2000  # Aumentar de 1000ms para 2000ms
    POLLING_TIMEOUT = 10  # Aumentar timeout
    
# Verificar número de registradores por polling
# Dividir em múltiplos jobs se necessário
```

### Problemas de Performance

#### Slow Database Queries
**Problema:** Queries lentas
```sql
-- Verificar queries lentas no PostgreSQL
SELECT query, mean_time, calls 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;

-- Verificar índices
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes 
WHERE tablename IN ('data_log', 'alarm', 'register');
```

**Solução:** Adicionar índices
```python
# Em migrations ou manualmente
CREATE INDEX idx_data_log_timestamp_plc ON data_log(timestamp, plc_id);
CREATE INDEX idx_data_log_register_time ON data_log(register_id, timestamp);
CREATE INDEX idx_alarm_state_priority ON alarm(state, priority);
```

#### Memory Leaks
**Problema:** Uso crescente de memória
```python
# Debug memory usage
import psutil
import os

def log_memory_usage():
    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss / 1024 / 1024
    print(f"Uso de memória: {memory_mb:.2f} MB")

# Adicionar ao polling loop
log_memory_usage()
```

**Solução:** Gerenciar conexões de banco
```python
# Em app/services/polling_service.py
class DataProcessor:
    def _process_data(self):
        while self.running:
            try:
                # Processar dados
                pass
            finally:
                # Importante: fechar sessões
                db.session.remove()
```

### Problemas de Segurança

#### CSRF Token Missing
**Problema:** `The CSRF token is missing`
```html
<!-- Adicionar em todos os formulários -->
<form method="POST">
    {{ csrf_token() }}
    <!-- ou -->
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
</form>
```

#### Session Issues
**Problema:** Usuário deslogado constantemente
```python
# Verificar configurações de sessão
# Em app/config.py
class Config:
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = False  # True apenas em HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
```

### Problemas de Deploy

#### Nginx 502 Bad Gateway
**Problema:** Erro 502 no Nginx
```bash
# Verificar se aplicação está rodando
curl http://localhost:5000/api/health

# Verificar logs do Nginx
sudo tail -f /var/log/nginx/error.log

# Verificar logs da aplicação
sudo tail -f /var/log/supervisor/scada.log

# Reiniciar serviços
sudo supervisorctl restart scada
sudo systemctl restart nginx
```

#### Permission Denied Issues
**Problema:** Permissões incorretas em produção
```bash
# Corrigir propriedade dos arquivos
sudo chown -R scada:scada /opt/scada
sudo chmod -R 755 /opt/scada
sudo chmod 600 /opt/scada/.env

# Verificar logs de permissão
sudo tail -f /var/log/auth.log | grep scada
```

## 🔍 Debug Tools e Comandos Úteis

### Verificação de Sistema
```bash
# Status geral dos serviços
systemctl status nginx postgresql redis supervisor

# Uso de recursos
top -u scada
htop
df -h
free -h

# Conexões de rede
netstat -tulpn | grep :5000
netstat -tulpn | grep :5432
ss -tulpn | grep scada
```

### Debug de Aplicação
```python
# Debug mode no Flask
# Em .env
FLASK_ENV=development
FLASK_DEBUG=1

# Debug de SQL queries
# Em app/config.py
SQLALCHEMY_ECHO = True

# Debug logging personalizado
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(name)s %(levelname)s: %(message)s'
)
```

### Comandos de Banco de Dados
```bash
# PostgreSQL
sudo -u postgres psql scada_prod

# Verificar tamanho das tabelas
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Verificar conexões ativas
SELECT * FROM pg_stat_activity WHERE datname = 'scada_prod';

# SQLite (desenvolvimento)
sqlite3 instance/scada.db
.tables
.schema user
SELECT COUNT(*) FROM data_log;
```

### Debug de Protocolos
```python
# Test script para Modbus
#!/usr/bin/env python3
import sys
from pymodbus.client.sync import ModbusTcpClient

def test_modbus(host, port=502):
    client = ModbusTcpClient(host, port=port)
    
    if client.connect():
        print(f"✅ Conectado ao Modbus em {host}:{port}")
        
        # Testar diferentes tipos de registradores
        tests = [
            ("Holding Registers", lambda: client.read_holding_registers(0, 10, unit=1)),
            ("Input Registers", lambda: client.read_input_registers(0, 10, unit=1)),
            ("Coils", lambda: client.read_coils(0, 10, unit=1)),
            ("Discrete Inputs", lambda: client.read_discrete_inputs(0, 10, unit=1)),
        ]
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                if not result.isError():
                    print(f"✅ {test_name}: OK")
                else:
                    print(f"❌ {test_name}: {result}")
            except Exception as e:
                print(f"❌ {test_name}: {e}")
        
        client.close()
    else:
        print(f"❌ Não foi possível conectar ao Modbus em {host}:{port}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python test_modbus.py <IP_DO_PLC>")
        sys.exit(1)
    
    test_modbus(sys.argv[1])
```

```python
# Test script para S7
#!/usr/bin/env python3
import sys
import snap7

def test_s7(host, rack=0, slot=1):
    plc = snap7.client.Client()
    
    try:
        plc.connect(host, rack, slot)
        print(f"✅ Conectado ao S7 PLC em {host}")
        
        # Informações do PLC
        cpu_info = plc.get_cpu_info()
        print(f"CPU: {cpu_info}")
        
        # Testar leitura de diferentes áreas
        tests = [
            ("DB1 (2 bytes)", lambda: plc.db_read(1, 0, 2)),
            ("Inputs (1 byte)", lambda: plc.read_area(snap7.types.S7AreaPE, 0, 0, 1)),
            ("Outputs (1 byte)", lambda: plc.read_area(snap7.types.S7AreaPA, 0, 0, 1)),
            ("Merkers (1 byte)", lambda: plc.read_area(snap7.types.S7AreaMK, 0, 0, 1)),
        ]
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                print(f"✅ {test_name}: {len(result)} bytes lidos")
            except Exception as e:
                print(f"❌ {test_name}: {e}")
        
    except Exception as e:
        print(f"❌ Erro S7: {e}")
    finally:
        plc.disconnect()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python test_s7.py <IP_DO_PLC>")
        sys.exit(1)
    
    test_s7(sys.argv[1])
```

## 📞 Quando Pedir Ajuda

### Informações a Coletar
Antes de reportar um problema, colete estas informações:

1. **Versão do Sistema**
```bash
python --version
pip list | grep -E "(Flask|SQLAlchemy|pymodbus|snap7)"
cat /etc/os-release
```

2. **Logs Relevantes**
```bash
# Últimas 100 linhas de cada log
tail -n 100 logs/app.log
tail -n 100 /var/log/supervisor/scada.log
tail -n 100 /var/log/nginx/error.log
```

3. **Configuração**
```bash
# Configuração sanitizada (sem senhas)
grep -v "PASSWORD\|SECRET\|KEY" .env
```

4. **Status dos Serviços**
```bash
systemctl status nginx postgresql redis supervisor
supervisorctl status
```

### Canais de Suporte
- **Issues no GitHub**: Para bugs e feature requests
- **Email**: suporte@scada.local
- **Documentação**: https://github.com/seu-usuario/CLP_TCC2/wiki

### Template para Reportar Problemas
```markdown
## Descrição do Problema
[Descreva o problema detalhadamente]

## Passos para Reproduzir
1. [Primeiro passo]
2. [Segundo passo]
3. [Terceiro passo]

## Comportamento Esperado
[O que deveria acontecer]

## Comportamento Atual
[O que está acontecendo]

## Ambiente
- OS: [Ubuntu 20.04, CentOS 8, etc.]
- Python: [3.8.10]
- Flask: [2.3.3]
- Browser: [Chrome 115, Firefox 116, etc.]

## Logs
```
[Cole os logs relevantes aqui]
```

## Screenshots
[Se aplicável, adicione screenshots]
```

Este guia de troubleshooting deve cobrir a maioria dos problemas comuns que você pode encontrar. Mantenha-o atualizado conforme novos problemas e soluções surgirem!