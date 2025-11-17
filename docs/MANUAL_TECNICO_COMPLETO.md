# Manual Técnico Completo do Projeto SCADA

Este documento reúne a visão arquitetural, o guia de operação diária e as rotinas de manutenção necessárias para evoluir o código. Todo o conteúdo está em português e pode ser usado como referência para novos integrantes da equipe, operadores e desenvolvedores experientes.

## 1. Visão geral do fluxo da aplicação

1. A aplicação Flask é criada por `create_app`, que inicializa extensões, carrega configurações e registra os blueprints web e de API.【F:src/app/__init__.py†L1-L71】
2. O `PollingService` é registrado como extensão Flask e cria automaticamente uma *thread* `CLPWorker` para cada CLP salvo no banco.【F:src/app/__init__.py†L1-L74】【F:src/services/polling/polling_service.py†L23-L73】
3. Cada `CLPWorker` usa o driver correspondente (Modbus, S7 ou OPC UA), lê todos os registradores e salva as medições em `data_log` via `DataRepo`.【F:src/services/polling/clp_worker.py†L15-L73】【F:src/repository/Data_repository.py†L64-L104】
4. Os valores lidos são avaliados pelo `AlarmService`, que dispara ou limpa alarmes com base nas definições cadastradas.【F:src/services/Alarms_service.py†L1-L118】【F:src/services/Alarms_service.py†L140-L219】
5. Logs coloridos e padronizados são emitidos por `src/utils/logs`, facilitando o acompanhamento em tempo real.【F:src/utils/logs/logs.py†L1-L79】

## 2. Estrutura de diretórios

| Diretório | Papel principal |
|-----------|-----------------|
| `src/app/` | Interface Flask, rotas web e API, configuração de extensões e templates.【F:src/app/__init__.py†L1-L71】|
| `src/services/polling/` | Serviço de polling Python com uma thread por CLP e workers simples.【F:src/services/polling/polling_service.py†L1-L85】【F:src/services/polling/clp_worker.py†L1-L73】|
| `src/services/drivers/` | Drivers didáticos para Modbus, S7 e OPC UA com API `conectar/ler/desconectar`.【F:src/services/drivers/modbus_driver.py†L1-L36】【F:src/services/drivers/s7_driver.py†L1-L36】【F:src/services/drivers/opcua_driver.py†L1-L36】|
| `src/models/` | Modelos SQLAlchemy para CLPs, registradores, alarmes, usuários e dados históricos.【F:src/models/PLCs.py†L1-L126】【F:src/models/Registers.py†L1-L43】【F:src/models/Alarms.py†L1-L71】|
| `src/repository/` | Repositórios genéricos e específicos para encapsular operações de banco de dados.【F:src/repository/Base_repository.py†L1-L118】【F:src/repository/PLC_repository.py†L1-L69】【F:src/repository/Registers_repository.py†L1-L65】【F:src/repository/Alarms_repository.py†L1-L48】|
| `src/services/` | Lógica de negócios (polling Python, alarmes, envio de e-mails, etc.).【F:src/services/polling/polling_service.py†L1-L85】【F:src/services/Alarms_service.py†L1-L219】|
| `src/simulations/` | Registro global de simulação e utilitários de simulador S7 para ambientes sem CLPs físicos.【F:src/simulations/runtime.py†L1-L122】【F:src/simulations/s7_simulation.py†L1-L129】|
| `src/jobs/` | Tarefas agendáveis, como limpeza de dados históricos antigos.【F:src/jobs/cleanup_old_data.py†L1-L63】|
| `src/utils/` | Funções auxiliares (logs, constantes, segurança, tags).【F:src/utils/logs/logs.py†L1-L79】|
| `tests/` | Testes automatizados que exercitam especialmente o comportamento das simulações.【F:tests/test_simulations/test_runtime.py†L1-L33】|

## 3. Componentes principais e manutenção

### 3.1 Aplicação Flask (`src/app`)
- A função `create_app` deve ser o ponto de entrada sempre que scripts externos precisarem de contexto Flask. Ela garante a criação do banco e o registro dos blueprints.【F:src/app/__init__.py†L1-L71】
- Para adicionar novos blueprints ou extensões, registre-os dentro de `register_blueprints` ou logo após o bloco de inicialização de extensões.
- Mantenha as configurações em `src/app/config.py` (não exibido aqui) e utilize variáveis de ambiente para distinguir desenvolvimento/produção.

### 3.2 Polling Service em Python (`src/services/polling`)
- `PollingService` é registrado automaticamente em `create_app`, carrega todos os CLPs do banco e cria uma *thread* `CLPWorker` por controlador.【F:src/services/polling/polling_service.py†L23-L73】
- Cada `CLPWorker` seleciona o driver correto via `get_driver`, lê todos os registradores ativos e salva as leituras via `DataRepo.registrar_leitura`, mantendo logs claros e resilientes.【F:src/services/polling/clp_worker.py†L15-L73】【F:src/services/drivers/factory.py†L1-L20】
- Não há dependência de Go ou gRPC; todo o ciclo roda dentro do processo Flask.

### 3.3 Serviços relacionados (`src/services`)
- `DataRepo.registrar_leitura` insere as leituras no `data_log` e atualiza metadados do registrador.【F:src/repository/Data_repository.py†L64-L104】
- `AlarmService` continua responsável pela lógica de avaliação e notificação de alarmes; utilize seus métodos para qualquer nova rotina que manipule alarmes manualmente.【F:src/services/Alarms_service.py†L1-L219】

### 3.4 Serviços (`src/services`)
- `poller_ingest_service.process_poller_payload` valida, persiste e integra as medições recebidas do Go, incluindo avaliação de alarmes e atualização dos estados dos CLPs.【F:src/services/poller_ingest_service.py†L1-L160】
- `AlarmService` continua responsável pela lógica de avaliação e notificação de alarmes; utilize seus métodos para qualquer nova rotina que manipule alarmes manualmente.【F:src/services/Alarms_service.py†L1-L219】

### 3.5 Repositórios e modelos (`src/repository`, `src/models`)
- `BaseRepo` centraliza operações CRUD, garantindo consistência de logs e transações.【F:src/repository/Base_repository.py†L1-L118】
- Repositórios especializados (`Plcrepo`, `RegRepo`, `AlarmRepo`) adicionam regras de negócios e validações antes de persistir os objetos.【F:src/repository/PLC_repository.py†L1-L69】【F:src/repository/Registers_repository.py†L1-L65】【F:src/repository/Alarms_repository.py†L1-L48】
- Os modelos `PLC`, `Register` e `AlarmDefinition` armazenam metadados essenciais (endereço, tipo de dado, setpoints). Familiarize-se com os campos ao criar migrações ou novos recursos.【F:src/models/PLCs.py†L1-L126】【F:src/models/Registers.py†L1-L43】【F:src/models/Alarms.py†L1-L71】

### 3.6 Simulações (`src/simulations`)
- `simulation_registry` gera valores determinísticos para qualquer protocolo em modo simulado; use `set_static_value` para forçar leituras fixas em testes.【F:src/simulations/runtime.py†L1-L122】
- `S7Simulator` encapsula um servidor snap7 em memória, permitindo registrar DBs e manipular bytes diretamente, ideal para testes de integração sem hardware.【F:src/simulations/s7_simulation.py†L1-L129】

### 3.7 Utilitários e tarefas agendadas
- `setup_logger` cria um logger colorido, silenciando dependências barulhentas e expondo o método customizado `process`. Ajuste os níveis aqui para mudar o volume de logs.【F:src/utils/logs/logs.py†L1-L79】
- O job `cleanup_old_data` remove históricos antigos em lotes; agende-o via cron para controlar o tamanho do banco.【F:src/jobs/cleanup_old_data.py†L1-L63】

## 4. Execução e automação com `run.py`

- O script simplesmente instancia o Flask via `create_app` e sobe o servidor HTTP; o `PollingService` é iniciado como extensão durante a criação do app.【F:run.py†L1-L8】【F:src/app/__init__.py†L1-L74】
- CLPs e registradores são carregados do banco, sem etapas de configuração dinâmica ou processos externos.

## 5. Uso do polling Python em ambientes simulados

- Para cenários sem hardware, os drivers retornam valores simulados baseados no endereço e no identificador do CLP, garantindo demonstrações consistentes.【F:src/services/drivers/modbus_driver.py†L17-L30】【F:src/services/drivers/s7_driver.py†L17-L30】
- Novos protocolos podem ser adicionados implementando um driver com a assinatura `conectar/ler/desconectar` e registrando-o na `factory` quando necessário.【F:src/services/drivers/factory.py†L1-L20】

## 6. Rotinas de manutenção

- **Adicionar novo CLP em produção:** utilize `Plcrepo.upsert_by_ip` ou siga o padrão de `setup_single_plc`, garantindo descrição, protocolo correto e tags atualizadas.【F:run.py†L139-L197】【F:src/repository/PLC_repository.py†L20-L55】
- **Cadastrar registradores:** use `RegRepo.add` com endereço, tipo e dados do novo ponto. Aproveite `ensure_register` como referência para os campos mínimos obrigatórios.【F:run.py†L109-L137】【F:src/repository/Registers_repository.py†L12-L34】
- **Criar alarmes:** recorra a `AlarmDefinitionRepo` para vincular setpoints aos registradores. `ensure_alarm` demonstra como preencher `condition_type`, `setpoint` e severidade.【F:run.py†L109-L205】【F:src/models/Alarms.py†L8-L43】
- **Limpeza de dados históricos:** agende `python -m src.jobs.cleanup_old_data` (ex.: cron diário) para manter apenas os últimos N valores por registrador.【F:src/jobs/cleanup_old_data.py†L1-L63】
- **Atualização de dependências:** mantenha `requirements.txt` sincronizado e execute testes automatizados após qualquer alteração de driver ou biblioteca.

## 7. Testes e verificação

- Execute `pytest` para validar as simulações, incluindo a produção determinística de valores pelo `simulation_registry`.【F:tests/test_simulations/test_runtime.py†L1-L33】
- Monitore os logs via console (graças ao `ColorFormatter`) para identificar falhas de conexão ou de leitura rapidamente.【F:src/utils/logs/logs.py†L14-L49】
- Antes de mudanças relevantes em protocolos, use `run.py` para gerar CLPs simulados e validar as leituras/alarmes em ambiente local.【F:run.py†L1-L209】

## 8. Boas práticas

- Use ambientes virtuais separados para desenvolvimento, testes e produção.
- Centralize alterações estruturais em migrations (via Flask-Migrate) e garanta compatibilidade com SQLite e PostgreSQL.【F:src/app/__init__.py†L13-L45】
- Prefira configurar novos recursos por meio dos repositórios para manter logs consistentes e evitar duplicidades.
- Documente alterações relevantes atualizando este manual e o índice principal da pasta `docs`.

Com este guia, é possível compreender o papel de cada módulo, executar o projeto em modo simulado com CLPs S7 e OPC UA e manter a base de código de forma segura.
