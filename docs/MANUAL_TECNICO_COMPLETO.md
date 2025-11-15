# Manual Técnico Completo do Projeto SCADA

Este documento reúne a visão arquitetural, o guia de operação diária e as rotinas de manutenção necessárias para evoluir o código. Todo o conteúdo está em português e pode ser usado como referência para novos integrantes da equipe, operadores e desenvolvedores experientes.

## 1. Visão geral do fluxo da aplicação

1. A aplicação Flask é criada por `create_app`, que inicializa extensões, carrega configurações e registra os blueprints web e de API.【F:src/app/__init__.py†L1-L71】
2. O `GoPollingManager` inicia o runtime Go via subprocesso, estabelece o canal gRPC e encaminha os dados recebidos pelo stream para a fila de ingestão.【F:src/manager/go_polling_manager.py†L21-L140】
3. O `run.py` constrói a configuração inicial dos CLPs, publica-a via RPC `UpdateConfig` e aciona a coleta contínua pelo método `StreamData`, integrando o runtime com o Flask por meio do `PollingRuntime`.【F:run.py†L210-L360】【F:src/services/polling_runtime.py†L1-L68】
4. Os valores lidos são avaliados pelo `AlarmService`, que dispara ou limpa alarmes com base nas definições cadastradas.【F:src/services/Alarms_service.py†L1-L118】【F:src/services/Alarms_service.py†L140-L219】
5. Logs coloridos e padronizados são emitidos por `src/utils/logs`, facilitando o acompanhamento em tempo real.【F:src/utils/logs/logs.py†L1-L79】

## 2. Estrutura de diretórios

| Diretório | Papel principal |
|-----------|-----------------|
| `src/app/` | Interface Flask, rotas web e API, configuração de extensões e templates.【F:src/app/__init__.py†L1-L71】|
| `go/polling/` | Código Go do `PollingService` gRPC e Dockerfile dedicado ao poller de alta performance.【F:go/polling/cmd/poller/main.go†L1-L165】|
| `src/grpc_generated/` | Artefatos `polling_pb2` e `polling_pb2_grpc` gerados a partir do contrato `.proto` para consumo Python.【F:src/grpc_generated/polling_pb2_grpc.py†L1-L30】|
| `src/manager/` | Cliente gRPC e gerenciamento do subprocesso Go responsável pelo polling.【F:src/manager/go_polling_manager.py†L1-L140】|
| `src/models/` | Modelos SQLAlchemy para CLPs, registradores, alarmes, usuários e dados históricos.【F:src/models/PLCs.py†L1-L126】【F:src/models/Registers.py†L1-L43】【F:src/models/Alarms.py†L1-L71】|
| `src/repository/` | Repositórios genéricos e específicos para encapsular operações de banco de dados.【F:src/repository/Base_repository.py†L1-L118】【F:src/repository/PLC_repository.py†L1-L69】【F:src/repository/Registers_repository.py†L1-L65】【F:src/repository/Alarms_repository.py†L1-L48】|
| `src/services/` | Lógica de negócios (ingestão do poller Go, alarmes, envio de e-mails, etc.).【F:src/services/poller_ingest_service.py†L1-L160】【F:src/services/Alarms_service.py†L1-L219】|
| `src/simulations/` | Registro global de simulação e utilitários de simulador S7 para ambientes sem CLPs físicos.【F:src/simulations/runtime.py†L1-L122】【F:src/simulations/s7_simulation.py†L1-L129】|
| `src/jobs/` | Tarefas agendáveis, como limpeza de dados históricos antigos.【F:src/jobs/cleanup_old_data.py†L1-L63】|
| `src/utils/` | Funções auxiliares (logs, constantes, segurança, tags).【F:src/utils/logs/logs.py†L1-L79】|
| `tests/` | Testes automatizados que exercitam especialmente o comportamento das simulações.【F:tests/test_simulations/test_runtime.py†L1-L33】|

## 3. Componentes principais e manutenção

### 3.1 Aplicação Flask (`src/app`)
- A função `create_app` deve ser o ponto de entrada sempre que scripts externos precisarem de contexto Flask. Ela garante a criação do banco e o registro dos blueprints.【F:src/app/__init__.py†L1-L71】
- Para adicionar novos blueprints ou extensões, registre-os dentro de `register_blueprints` ou logo após o bloco de inicialização de extensões.
- Mantenha as configurações em `src/app/config.py` (não exibido aqui) e utilize variáveis de ambiente para distinguir desenvolvimento/produção.

### 3.2 Polling Service em Go (`go/polling`)
- O arquivo `polling.proto` define o contrato gRPC com os RPCs `UpdateConfig` e `StreamData`, ambos operando sobre blobs JSON para manter o serviço desacoplado do domínio Python.【F:go/polling/polling.proto†L1-L33】
- `go/polling/cmd/poller/main.go` implementa o `PollingService`, aplicando `sync.RWMutex` para proteger a configuração, ticker de 2 segundos para leitura contínua e *streaming* de medições resiliente a falhas.【F:go/polling/cmd/poller/main.go†L21-L165】
- Utilize `go build ./cmd/poller` para gerar o binário; o Dockerfile disponível na pasta `go/polling` permite empacotar o serviço separadamente.

### 3.3 Gerenciamento de polling (`src/manager`)
- `GoPollingManager` inicia o processo Go, verifica a disponibilidade do canal gRPC, envia a configuração inicial e mantém *threads* para leitura de `stderr` e consumo do stream.【F:src/manager/go_polling_manager.py†L1-L140】
- O método `update_config` aceita um dicionário Python e serializa para JSON antes de chamar o RPC `UpdateConfig`, permitindo *hot reload* de CLPs sem reiniciar o processo Go.【F:src/manager/go_polling_manager.py†L93-L123】
- `PollingRuntime` armazena a fila compartilhada, *thread* consumidora e sinalizadores para habilitar/desabilitar o polling dentro do contexto Flask.【F:src/services/polling_runtime.py†L1-L68】

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

- O script cria automaticamente cinco CLPs para cada protocolo (`s7-sim` e `opcua-sim`), garantindo dois registradores com alarmes configurados e preenchendo o registro de simulação.【F:run.py†L1-L209】
- `PROTOCOL_CONFIGS` define templates de registradores e alarmes; ajuste-o para alterar setpoints, unidades ou tags sem modificar o restante do código.【F:run.py†L33-L107】
- `setup_single_plc` reaproveita repositórios para inserir ou atualizar CLPs, registrar os pontos e amarrar as definições de alarme.【F:run.py†L139-L205】
- Após configurar os CLPs, o script inicia o poller Go via gRPC e, em seguida, sobe o servidor Flask na porta 5000.【F:run.py†L210-L360】

## 5. Uso do poller Go em ambientes simulados

- O `run.py` continua a utilizar `simulation_registry` para preencher valores iniciais de CLPs e registradores durante o *bootstrap* das demonstrações.【F:run.py†L107-L209】【F:src/simulations/runtime.py†L1-L122】
- O runtime Go gera valores simulados em `readRegister`; adapte essa função para integrar drivers reais ou fontes específicas de dados industriais conforme necessário.【F:go/polling/cmd/poller/main.go†L126-L145】
- Alterações dinâmicas de configuração podem ser propagadas chamando `GoPollingManager.update_config`, permitindo ajustar registradores ou CLPs sem reiniciar o serviço.【F:src/manager/go_polling_manager.py†L93-L123】

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
