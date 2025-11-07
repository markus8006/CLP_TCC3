# 🚀 Manual de Deploy e Produção

## 🌐 Deploy em Produção

### Pré-requisitos para Produção
- **Servidor Linux** (Ubuntu 20.04+ ou CentOS 8+)
- **Python 3.8+**
- **PostgreSQL 12+**
- **Redis 6+**
- **Nginx** (proxy reverso)
- **Supervisor** (gerenciamento de processos)
- **SSL Certificate** (Let's Encrypt recomendado)

### Preparação do Servidor

#### 1. Atualização do Sistema
```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# CentOS/RHEL
sudo yum update -y
```

#### 2. Instalação de Dependências
```bash
# Ubuntu/Debian
sudo apt install -y python3 python3-pip python3-venv nginx postgresql postgresql-contrib redis-server supervisor git

# CentOS/RHEL
sudo yum install -y python3 python3-pip nginx postgresql postgresql-server redis supervisor git
```

#### 3. Configuração do PostgreSQL
```bash
# Inicializar PostgreSQL (CentOS)
sudo postgresql-setup initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Ubuntu (já iniciado automaticamente)
sudo systemctl enable postgresql

# Criar banco e usuários (separando app e migrações)
sudo -u postgres psql <<'EOF'
CREATE DATABASE scada_prod;

-- Usuário utilizado pela aplicação em produção (privilégios mínimos)
CREATE USER scada_app WITH PASSWORD 'TroqueEstaSenha!';
REVOKE ALL ON DATABASE scada_prod FROM PUBLIC;
GRANT CONNECT ON DATABASE scada_prod TO scada_app;

\connect scada_prod
GRANT USAGE ON SCHEMA public TO scada_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO scada_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO scada_app;

-- Usuário opcional para rodar migrações/administração
CREATE USER scada_migrator WITH PASSWORD 'TroqueEstaSenhaMigrator!';
GRANT CONNECT ON DATABASE scada_prod TO scada_migrator;
GRANT ALL PRIVILEGES ON SCHEMA public TO scada_migrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO scada_migrator;
EOF
```

#### 4. Configuração do Redis
```bash
# Iniciar e habilitar Redis
sudo systemctl start redis
sudo systemctl enable redis

# Configurar Redis para produção
sudo cp /etc/redis/redis.conf /etc/redis/redis.conf.backup
sudo sed -i 's/# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
sudo sed -i 's/# maxmemory <bytes>/maxmemory 512mb/' /etc/redis/redis.conf
sudo systemctl restart redis
```

### Deploy da Aplicação

#### 1. Preparação do Usuário de Deploy
```bash
# Criar usuário para a aplicação
sudo useradd -m -s /bin/bash scada
sudo usermod -aG sudo scada  # Se necessário acesso sudo

# Trocar para usuário scada
sudo su - scada
```

#### 2. Clone e Configuração
```bash
# Clonar repositório
git clone https://github.com/seu-usuario/CLP_TCC2.git /opt/scada
cd /opt/scada

# Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependências de produção
pip install --upgrade pip
pip install -r requirements/production.txt
```

#### 3. Configuração de Ambiente
```bash
# Copie o template (apenas para desenvolvimento/local)
cp .env.example .env

# Preencha os segredos manualmente ou via gerenciador
$EDITOR .env

# Variáveis obrigatórias
# SECRET_KEY=...
# DATABASE_URL=...
# PLC_DEFAULT_USERNAME=...
# PLC_DEFAULT_PASSWORD=...
# (Opcional) PLC_SECRET_BACKEND_PATH=vault:secret/data/scada/plc

# Proteja o arquivo localmente
chmod 600 .env
```

> ⚠️ **Produção:** não armazene segredos sensíveis em arquivos de texto. Utilize Vault, AWS SSM Parameter Store, Azure Key Vault ou outra solução gerenciada e injete as variáveis no serviço (systemd, Docker secrets, Kubernetes secrets, etc.).

### 🔐 Gestão de Segredos

- **Carregamento automático:** o módulo `src/app/config.py` utiliza `python-dotenv` para carregar `.env` em desenvolvimento sem sobrepor variáveis já exportadas. Em produção, basta definir as variáveis no ambiente que o Flask irá carregá-las.
- **Segredos obrigatórios:**
  - `SECRET_KEY` — assinatura de sessões Flask.
  - `DATABASE_URL` — string de conexão (utilize a role `scada_app`).
  - `PLC_DEFAULT_USERNAME` / `PLC_DEFAULT_PASSWORD` — credenciais usadas pelos adaptadores de PLC; em produção, armazene-as no secret manager e referencie via `PLC_SECRET_BACKEND_PATH` quando houver integração com Vault/SSM/Key Vault.
  - *(Opcional)* `ENCRYPTION_KEY` — chave usada por `DataEncryption` para persistir senhas de PLC; defina-a para permitir rotação controlada.
- **Rotação de segredos:**
  1. Gere novos valores no secret manager (novo par de credenciais do PLC, senha do banco, etc.).
  2. Atualize o serviço (por exemplo, `systemctl reload`, `kubectl rollout restart`) para carregar as variáveis atualizadas.
  3. Para o banco, troque a senha do usuário `scada_app` e atualize o segredo consumido pela aplicação. Utilize janelas de manutenção para evitar interrupções.
  4. Para `SECRET_KEY`, programe a rotação alinhada ao tempo de expiração de sessões. Avise os usuários de que sessões antigas podem ser invalidadas.
- **Ambientes múltiplos:** mantenha um cofre/namespace por ambiente (`vault://prod/scada`, `vault://staging/scada`, etc.). Os valores podem divergir: use PLCs simulados em staging (`PLC_DEFAULT_*` apontando para mocks) e conexões reais apenas em produção.

#### 4. Inicialização do Banco
```bash
# Inicializar banco de dados
python scripts/init_db.py

# Executar migrações se existirem
flask db upgrade
```

#### 5. Teste da Aplicação
```bash
# Testar se a aplicação inicia
python wsgi.py

# Testar endpoints básicos
curl http://localhost:5000/api/health
```

### Configuração do Nginx

#### 1. Configuração do Site
```bash
sudo tee /etc/nginx/sites-available/scada << 'EOF'
upstream scada_app {
    server 127.0.0.1:5000;
    server 127.0.0.1:5001 backup;
}

server {
    listen 80;
    server_name seu-dominio.com www.seu-dominio.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name seu-dominio.com www.seu-dominio.com;
    
    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/seu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seu-dominio.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
    
    # Logs
    access_log /var/log/nginx/scada_access.log;
    error_log /var/log/nginx/scada_error.log;
    
    # Static files
    location /static/ {
        alias /opt/scada/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    
    # WebSocket support
    location /socket.io/ {
        proxy_pass http://scada_app;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Application
    location / {
        proxy_pass http://scada_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffer settings
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
        proxy_busy_buffers_size 8k;
    }
    
    # Health check
    location /health {
        access_log off;
        proxy_pass http://scada_app;
    }
}
EOF

# Habilitar site
sudo ln -s /etc/nginx/sites-available/scada /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Testar configuração
sudo nginx -t

# Reiniciar Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

#### 2. SSL com Let's Encrypt
```bash
# Instalar Certbot
sudo apt install certbot python3-certbot-nginx

# Obter certificado SSL
sudo certbot --nginx -d seu-dominio.com -d www.seu-dominio.com

# Configurar renovação automática
sudo crontab -e
# Adicionar linha:
0 12 * * * /usr/bin/certbot renew --quiet
```

### Configuração do Supervisor

#### 1. Configuração da Aplicação Principal
```bash
sudo tee /etc/supervisor/conf.d/scada.conf << 'EOF'
[program:scada]
command=/opt/scada/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 4 --worker-class eventlet --worker-connections 1000 --timeout 60 --keepalive 2 --max-requests 1000 --max-requests-jitter 50 wsgi:app
directory=/opt/scada
user=scada
group=scada
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/supervisor/scada.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=PATH="/opt/scada/venv/bin"

[program:scada-worker]
command=/opt/scada/venv/bin/python -m app.services.background_worker
directory=/opt/scada
user=scada
group=scada
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/supervisor/scada-worker.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=PATH="/opt/scada/venv/bin"

[group:scada-app]
programs=scada,scada-worker
priority=999
EOF

# Atualizar Supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start scada-app:*
```

### Configuração de Firewall

#### 1. UFW (Ubuntu)
```bash
# Habilitar UFW
sudo ufw enable

# Permitir SSH
sudo ufw allow ssh

# Permitir HTTP e HTTPS
sudo ufw allow 'Nginx Full'

# Permitir PostgreSQL apenas localmente
sudo ufw allow from 127.0.0.1 to any port 5432

# Status do firewall
sudo ufw status
```

## 🔧 Manutenção e Monitoramento

### Logs do Sistema

#### 1. Configuração de Logs
```bash
# Configurar rotação de logs
sudo tee /etc/logrotate.d/scada << 'EOF'
/opt/scada/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 scada scada
    postrotate
        supervisorctl restart scada-app:*
    endscript
}
EOF
```

#### 2. Monitoramento de Logs
```bash
# Ver logs em tempo real
sudo tail -f /var/log/supervisor/scada.log
sudo tail -f /var/log/nginx/scada_access.log
sudo tail -f /opt/scada/logs/app.log

# Pesquisar erros
sudo grep -i error /var/log/supervisor/scada.log
sudo grep -i "5[0-9][0-9]" /var/log/nginx/scada_access.log
```

### Backup Automatizado

#### 1. Script de Backup
```bash
sudo tee /opt/scada/scripts/backup.sh << 'EOF'
#!/bin/bash

# Configurações
BACKUP_DIR="/opt/backups/scada"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Criar diretório de backup
mkdir -p $BACKUP_DIR

# Backup do banco de dados
export PGPASSWORD="SuaSenhaForteAqui123!"
pg_dump -h localhost -U scada_user -d scada_prod > $BACKUP_DIR/database_$DATE.sql

# Backup dos arquivos da aplicação
tar -czf $BACKUP_DIR/application_$DATE.tar.gz -C /opt scada --exclude=scada/venv --exclude=scada/.git

# Backup das configurações
cp /opt/scada/.env $BACKUP_DIR/env_$DATE
cp /etc/nginx/sites-available/scada $BACKUP_DIR/nginx_$DATE.conf
cp /etc/supervisor/conf.d/scada.conf $BACKUP_DIR/supervisor_$DATE.conf

# Limpar backups antigos
find $BACKUP_DIR -name "*.sql" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup realizado: $DATE"
EOF

chmod +x /opt/scada/scripts/backup.sh

# Agendar backup diário
sudo crontab -e
# Adicionar linha:
0 2 * * * /opt/scada/scripts/backup.sh >> /var/log/scada_backup.log 2>&1
```

### Monitoramento de Performance

#### 1. Monitoramento com htop
```bash
# Instalar htop
sudo apt install htop

# Monitorar processos
htop
```

#### 2. Monitoramento de Disco
```bash
# Espaço em disco
df -h

# Uso por diretório
du -sh /opt/scada/*
du -sh /var/log/*
```

#### 3. Monitoramento do PostgreSQL
```bash
# Status do PostgreSQL
sudo systemctl status postgresql

# Conexões ativas
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Tamanho do banco
sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('scada_prod'));"
```

### Atualização da Aplicação

#### 1. Script de Deploy
```bash
sudo tee /opt/scada/scripts/deploy.sh << 'EOF'
#!/bin/bash

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Iniciando deploy...${NC}"

# Backup antes do deploy
echo -e "${YELLOW}Fazendo backup...${NC}"
/opt/scada/scripts/backup.sh

# Atualizar código
echo -e "${YELLOW}Atualizando código...${NC}"
cd /opt/scada
git fetch origin
git reset --hard origin/main

# Ativar ambiente virtual
source venv/bin/activate

# Atualizar dependências
echo -e "${YELLOW}Atualizando dependências...${NC}"
pip install -r requirements/production.txt

# Executar migrações
echo -e "${YELLOW}Executando migrações...${NC}"
python -c "
from app import create_app
from app.extensions import db
app = create_app('production')
with app.app_context():
    db.create_all()
"

# Coletar arquivos estáticos
echo -e "${YELLOW}Coletando arquivos estáticos...${NC}"
# Se você tiver assets build process, executar aqui

# Reiniciar aplicação
echo -e "${YELLOW}Reiniciando aplicação...${NC}"
sudo supervisorctl restart scada-app:*

# Verificar se aplicação está rodando
sleep 5
if curl -f http://localhost:5000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}Deploy realizado com sucesso!${NC}"
else
    echo -e "${RED}Erro no deploy! Aplicação não responde.${NC}"
    exit 1
fi
EOF

chmod +x /opt/scada/scripts/deploy.sh
```

### Health Check e Alertas

#### 1. Script de Health Check
```bash
sudo tee /opt/scada/scripts/health_check.sh << 'EOF'
#!/bin/bash

# Função para enviar alerta
send_alert() {
    local message=$1
    echo "$(date): $message" >> /var/log/scada_health.log
    
    # Enviar email (configurar sendmail ou usar API)
    # curl -X POST "https://api.sendgrid.com/v3/mail/send" \
    #   -H "Authorization: Bearer YOUR_API_KEY" \
    #   -H "Content-Type: application/json" \
    #   -d '{...}'
}

# Verificar se aplicação responde
if ! curl -f http://localhost:5000/api/health > /dev/null 2>&1; then
    send_alert "CRÍTICO: Aplicação não responde"
fi

# Verificar PostgreSQL
if ! pg_isready -h localhost -U scada_user > /dev/null 2>&1; then
    send_alert "CRÍTICO: PostgreSQL não responde"
fi

# Verificar Redis
if ! redis-cli ping > /dev/null 2>&1; then
    send_alert "CRÍTICO: Redis não responde"
fi

# Verificar espaço em disco
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    send_alert "ALERTA: Disco com ${DISK_USAGE}% de uso"
fi

# Verificar memória
MEM_USAGE=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
if [ $MEM_USAGE -gt 90 ]; then
    send_alert "ALERTA: Memória com ${MEM_USAGE}% de uso"
fi
EOF

chmod +x /opt/scada/scripts/health_check.sh

# Executar a cada 5 minutos
sudo crontab -e
# Adicionar linha:
*/5 * * * * /opt/scada/scripts/health_check.sh
```

## 📊 Métricas e Observabilidade

### Prometheus e Grafana (Opcional)

#### 1. Instalação do Prometheus
```bash
# Baixar e instalar Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.40.0/prometheus-2.40.0.linux-amd64.tar.gz
tar xzf prometheus-2.40.0.linux-amd64.tar.gz
sudo mv prometheus-2.40.0.linux-amd64 /opt/prometheus
sudo useradd --no-create-home --shell /bin/false prometheus
sudo chown -R prometheus:prometheus /opt/prometheus

# Configurar como serviço
sudo tee /etc/systemd/system/prometheus.service << 'EOF'
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/opt/prometheus/prometheus \
  --config.file=/opt/prometheus/prometheus.yml \
  --storage.tsdb.path=/opt/prometheus/data \
  --web.console.templates=/opt/prometheus/consoles \
  --web.console.libraries=/opt/prometheus/console_libraries

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl start prometheus
sudo systemctl enable prometheus
```

### Configuração de SSL/TLS

#### 1. SSL Hardening
```bash
# Gerar DH params
sudo openssl dhparam -out /etc/nginx/dhparam.pem 2048

# Atualizar configuração do Nginx
sudo tee -a /etc/nginx/sites-available/scada << 'EOF'
    ssl_dhparam /etc/nginx/dhparam.pem;
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;
EOF

sudo nginx -t && sudo systemctl reload nginx
```

### Troubleshooting de Produção

#### 1. Comandos Úteis
```bash
# Status dos serviços
sudo systemctl status nginx
sudo systemctl status postgresql
sudo systemctl status redis
sudo supervisorctl status

# Logs de erro
sudo journalctl -u nginx -f
sudo journalctl -u postgresql -f
sudo tail -f /var/log/supervisor/scada.log

# Processos da aplicação
ps aux | grep scada
netstat -tulpn | grep :5000

# Conexões do banco
sudo -u postgres psql -c "SELECT * FROM pg_stat_activity WHERE datname='scada_prod';"

# Cache do Redis
redis-cli info memory
redis-cli keys "*"
```

#### 2. Restart de Emergência
```bash
# Restart completo
sudo supervisorctl stop scada-app:*
sudo systemctl restart postgresql
sudo systemctl restart redis
sudo systemctl restart nginx
sudo supervisorctl start scada-app:*

# Verificar status
curl -I http://localhost:5000/api/health
```