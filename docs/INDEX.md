# 📚 Documentação Completa - Índice Principal

## 📖 Sistema SCADA Industrial - Documentação Completa

### 🗂️ Estrutura da Documentação

Esta documentação está organizada nos seguintes arquivos:

1. **[README.md](README.md)** - Documentação principal com visão geral, instalação básica, manual do usuário e API
2. **[DEVELOPMENT.md](DEVELOPMENT.md)** - Guia completo de desenvolvimento, arquitetura e padrões de código
3. **[DEPLOYMENT.md](DEPLOYMENT.md)** - Manual de deploy em produção, configuração de servidor e manutenção
4. **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Solução de problemas comuns e debug

---

## 🚀 Para Começar Rapidamente

### 🏃‍♂️ Instalação Rápida
```bash
# 1. Usar o script de migração automática
python migrate_project.py

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar ambiente
cp .env.example .env

# 4. Inicializar banco
python scripts/init_db.py

# 5. Executar
python run.py
```

### 🌐 Acesso
- **URL**: http://localhost:5000
- **Login**: admin / admin123

---

## 📋 Documentação por Perfil

### 👨‍💼 Para Administradores
- **[Manual de Instalação](README.md#manual-de-instalação)** - Setup inicial
- **[Manual do Usuário](README.md#manual-do-usuário)** - Como usar o sistema
- **[Deploy em Produção](DEPLOYMENT.md)** - Configuração de servidor
- **[Troubleshooting](TROUBLESHOOTING.md)** - Solução de problemas

### 👨‍💻 Para Desenvolvedores
- **[Arquitetura do Sistema](DEVELOPMENT.md#arquitetura-do-sistema)** - Padrões e estrutura
- **[Setup de Desenvolvimento](DEVELOPMENT.md#setup-de-desenvolvimento)** - Ambiente de dev
- **[Padrões de Código](DEVELOPMENT.md#padrões-de-código)** - Estilo e boas práticas
- **[Testes](DEVELOPMENT.md#testes)** - Como escrever e executar testes
- **[Debug Tools](TROUBLESHOOTING.md#debug-tools-e-comandos-úteis)** - Ferramentas de debug

### 🔧 Para DevOps
- **[Deploy em Produção](DEPLOYMENT.md)** - Setup completo de servidor
- **[Monitoramento](DEPLOYMENT.md#monitoramento-e-performance)** - Logs e métricas
- **[Backup e Manutenção](DEPLOYMENT.md#backup-automatizado)** - Processos automatizados
- **[Segurança](DEPLOYMENT.md#configuração-de-ssltls)** - Configurações de segurança

### 🔌 Para Integradores
- **[Documentação da API](README.md#documentação-da-api)** - Endpoints REST
- **[Adapters de Protocolo](DEVELOPMENT.md#criando-novos-adapters)** - Como criar novos adapters
- **[Exemplos de Integração](README.md#exemplos-de-integração)** - Python, JavaScript, curl

---

## 📁 Arquivos de Configuração e Scripts

### 📄 Arquivos de Configuração
- **`.env.example`** - Template de configuração
- **`requirements.txt`** - Dependências Python
- **`docker-compose.yml`** - Configuração Docker
- **`migrate_project.py`** - Script de migração automática

### 🔧 Scripts Utilitários
- **`scripts/init_db.py`** - Inicialização do banco de dados
- **`scripts/backup.sh`** - Script de backup (produção)
- **`scripts/deploy.sh`** - Script de deploy (produção)
- **`scripts/health_check.sh`** - Verificação de saúde do sistema

---

## 🏗️ Estrutura Técnica Resumida

### Tecnologias Principais
- **Backend**: Flask, SQLAlchemy, Flask-SocketIO
- **Frontend**: Bootstrap 5, Chart.js, WebSockets
- **Protocolos**: Modbus TCP/RTU, Siemens S7
- **Banco**: SQLite (dev), PostgreSQL (prod)
- **Cache**: Redis
- **Deploy**: Nginx, Supervisor, Docker

### Módulos Principais
```
app/
├── auth/           # Autenticação e autorização
├── models/         # Modelos de dados (SQLAlchemy)
├── services/       # Lógica de negócios
│   ├── polling_service.py    # Coleta de dados
│   ├── alarm_service.py      # Sistema de alarmes
│   ├── security_service.py   # Segurança
│   └── backup_service.py     # Backup automático
├── api/            # API REST
├── web/            # Interface web
├── adapters/       # Drivers de comunicação
└── utils/          # Utilitários
```

---

## 🔗 Links Rápidos

### 📖 Documentação
- [Visão Geral do Sistema](README.md#sistema-scada-industrial)
- [Instalação Passo a Passo](README.md#instalação-detalhada)
- [Configuração de PLCs](README.md#gerenciamento-de-plcs)
- [Sistema de Alarmes](README.md#sistema-de-alarmes)
- [API REST Completa](README.md#documentação-da-api)

### 🛠️ Desenvolvimento
- [Arquitetura e Padrões](DEVELOPMENT.md#arquitetura-do-sistema)
- [Setup de Desenvolvimento](DEVELOPMENT.md#setup-de-desenvolvimento)
- [Criando Testes](DEVELOPMENT.md#testes)
- [Novos Adapters](DEVELOPMENT.md#criando-novos-adapters)

### 🚀 Produção
- [Deploy Completo](DEPLOYMENT.md#deploy-em-produção)
- [Configuração Nginx](DEPLOYMENT.md#configuração-do-nginx)
- [Monitoramento](DEPLOYMENT.md#monitoramento-de-performance)
- [Backup Automático](DEPLOYMENT.md#backup-automatizado)

### 🔧 Troubleshooting
- [Problemas Comuns](TROUBLESHOOTING.md#problemas-comuns-e-soluções)
- [Debug de Comunicação](TROUBLESHOOTING.md#problemas-de-comunicação-com-plcs)
- [Performance Issues](TROUBLESHOOTING.md#problemas-de-performance)
- [Scripts de Debug](TROUBLESHOOTING.md#debug-de-protocolos)

---

## 🆘 Suporte e Contribuição

### 📞 Canais de Suporte
- **GitHub Issues**: Para bugs e feature requests
- **Email**: suporte@scada.local
- **Wiki**: Documentação adicional

### 🤝 Como Contribuir
1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/NovaFuncionalidade`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/NovaFuncionalidade`)
5. Abra um Pull Request

### 📝 Reportar Problemas
Use o [template de issue](TROUBLESHOOTING.md#template-para-reportar-problemas) para reportar problemas.

---

## 📊 Status do Projeto

### ✅ Funcionalidades Implementadas
- [x] Sistema de autenticação com roles
- [x] Interface web moderna e responsiva
- [x] Polling de dados em tempo real
- [x] Sistema de alarmes completo
- [x] Suporte a Modbus TCP/RTU
- [x] Suporte a Siemens S7
- [x] API REST completa
- [x] Sistema de relatórios
- [x] Backup automático
- [x] Auditoria de segurança

### 🔄 Em Desenvolvimento
- [ ] Suporte a EtherNet/IP
- [ ] Suporte a OPC UA
- [ ] Dashboard customizável
- [ ] Integração com MES/ERP
- [ ] App mobile

### 📈 Roadmap
- **v2.1**: Suporte a OPC UA e EtherNet/IP
- **v2.2**: Dashboard customizável e widgets
- **v2.3**: Integração com sistemas MES/ERP
- **v3.0**: Aplicativo mobile nativo

---

## 📄 Licença

Este projeto está licenciado sob a MIT License - veja o arquivo [LICENSE](LICENSE) para detalhes.

---

## 🙏 Agradecimentos

- **Flask Community** - Framework web excepcional
- **PyModbus Team** - Biblioteca Modbus robusta  
- **Python-snap7** - Interface S7 confiável
- **Bootstrap Team** - Framework CSS moderno
- **Chart.js** - Gráficos interativos

---

**Sistema SCADA Industrial v2.0**  
*Desenvolvido com ❤️ para a indústria brasileira*