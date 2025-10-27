# Manual Técnico Completo do Projeto SCADA

Este documento reúne a visão arquitetural, o guia de operação diária e as rotinas de manutenção necessárias para evoluir o código. Todo o conteúdo está em português e pode ser usado como referência para novos integrantes da equipe, operadores e desenvolvedores experientes.

## 1. Visão geral do fluxo da aplicação

1. A aplicação Flask é criada por `create_app`, que inicializa extensões, carrega configurações e registra os blueprints web e de API.【F:src/app/__init__.py†L1-L71】
2. O gerenciador `SimpleManager` cria e mantém *pollers* assíncronos (`ActivePLCPoller`) para cada CLP ativo, coordenando o acesso concorrente aos adaptadores de protocolo.【F:src/manager/client_polling_manager.py†L24-L219】【F:src/manager/client_polling_manager.py†L223-L271】
3. O serviço `run_async_polling` descobre os CLPs ativos e injeta cada um no gerenciador, garantindo a leitura contínua de registradores.【F:src/services/client_polling_service.py†L1-L24】
4. Os valores lidos são avaliados pelo `AlarmService`, que dispara ou limpa alarmes com base nas definições cadastradas.【F:src/services/Alarms_service.py†L1-L118】【F:src/services/Alarms_service.py†L140-L219】
5. Logs coloridos e padronizados são emitidos por `src/utils/logs`, facilitando o acompanhamento em tempo real.【F:src/utils/logs/logs.py†L1-L79】

## 2. Estrutura de diretórios

| Diretório | Papel principal |
|-----------|-----------------|
| `src/app/` | Interface Flask, rotas web e API, configuração de extensões e templates.【F:src/app/__init__.py†L1-L71】|
| `src/adapters/` | Drivers de comunicação para Modbus, S7 e OPC UA, além da fábrica que decide qual adapter instanciar.【F:src/adapters/base_adapters.py†L1-L101】【F:src/adapters/modbus_adapter.py†L1-L115】【F:src/adapters/s7_adapter.py†L1-L115】【F:src/adapters/opcua_adapter.py†L1-L78】|
| `src/manager/` | Coordena o ciclo de vida dos pollers e a leitura assíncrona dos registradores.【F:src/manager/client_polling_manager.py†L24-L271】|
| `src/models/` | Modelos SQLAlchemy para CLPs, registradores, alarmes, usuários e dados históricos.【F:src/models/PLCs.py†L1-L126】【F:src/models/Registers.py†L1-L43】【F:src/models/Alarms.py†L1-L71】|
| `src/repository/` | Repositórios genéricos e específicos para encapsular operações de banco de dados.【F:src/repository/Base_repository.py†L1-L118】【F:src/repository/PLC_repository.py†L1-L69】【F:src/repository/Registers_repository.py†L1-L65】【F:src/repository/Alarms_repository.py†L1-L48】|
| `src/services/` | Lógica de negócios (polling, alarmes, envio de e-mails, etc.).【F:src/services/client_polling_service.py†L1-L24】【F:src/services/Alarms_service.py†L1-L219】|
| `src/simulations/` | Registro global de simulação e utilitários de simulador S7 para ambientes sem CLPs físicos.【F:src/simulations/runtime.py†L1-L122】【F:src/simulations/s7_simulation.py†L1-L129】|
| `src/jobs/` | Tarefas agendáveis, como limpeza de dados históricos antigos.【F:src/jobs/cleanup_old_data.py†L1-L63】|
| `src/utils/` | Funções auxiliares (logs, constantes, segurança, tags).【F:src/utils/logs/logs.py†L1-L79】|
| `tests/` | Testes automatizados que exercitam especialmente o comportamento das simulações.【F:tests/test_simulations/test_runtime.py†L1-L33】|

## 3. Componentes principais e manutenção

### 3.1 Aplicação Flask (`src/app`)
- A função `create_app` deve ser o ponto de entrada sempre que scripts externos precisarem de contexto Flask. Ela garante a criação do banco e o registro dos blueprints.【F:src/app/__init__.py†L1-L71】
- Para adicionar novos blueprints ou extensões, registre-os dentro de `register_blueprints` ou logo após o bloco de inicialização de extensões.
- Mantenha as configurações em `src/app/config.py` (não exibido aqui) e utilize variáveis de ambiente para distinguir desenvolvimento/produção.

### 3.2 Adaptadores de protocolo (`src/adapters`)
- `BaseAdapter` fornece a interface assíncrona comum, padronizando o retorno das leituras e a verificação de alarmes vinculados.【F:src/adapters/base_adapters.py†L1-L101】 Mantenha novos adaptadores compatíveis com esses métodos (`connect`, `disconnect`, `read_register`).
- `ModbusAdapter`, `S7Adapter` e `OpcUaAdapter` herdados implementam as particularidades de cada protocolo, inclusive modos de simulação baseados no registro global de valores.【F:src/adapters/modbus_adapter.py†L1-L103】【F:src/adapters/s7_adapter.py†L1-L86】【F:src/adapters/opcua_adapter.py†L1-L69】
- A fábrica `get_adapter` seleciona o driver correto, portanto sempre cadastre novos protocolos nela.【F:src/adapters/factory.py†L1-L25】

### 3.3 Gerenciamento de polling (`src/manager`)
- `ActivePLCPoller` controla a leitura concorrente de registradores, com limites de paralelismo configurados e integração direta com `AlarmService` e o repositório de dados históricos.【F:src/manager/client_polling_manager.py†L24-L219】
- `SimpleManager` adiciona ou remove pollers de forma thread-safe. Use-o sempre que precisar ativar/desativar CLPs dinamicamente.【F:src/manager/client_polling_manager.py†L223-L271】
- Para manutenção, revise os limites de threads (`max_workers`) e ajustes de *backoff* antes de aumentar o número de CLPs monitorados.

### 3.4 Serviços (`src/services`)
- `run_async_polling` organiza o *bootstrap* de polling e pode ser reutilizado em scripts customizados.【F:src/services/client_polling_service.py†L1-L24】
- `AlarmService` implementa toda a lógica de avaliação e notificação de alarmes; utilize seus métodos para qualquer nova rotina que manipule alarmes manualmente.【F:src/services/Alarms_service.py†L1-L219】

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
- Após configurar os CLPs, o script liga o serviço de polling assíncrono e sobe o servidor Flask na porta 5000.【F:run.py†L207-L209】

## 5. Uso dos simuladores S7 e OPC UA

### 5.1 Siemens S7
1. Instale `python-snap7` no ambiente virtual.
2. Invoque `S7Simulator`, registre os DBs necessários via `register_db` e, se quiser valores iniciais, use `initialize_s7_test_dbs` ou `add_db_test_value`.【F:src/simulations/s7_simulation.py†L1-L129】
3. Execute `sim.start()` para iniciar o servidor em background. O modo `s7-sim` dos adaptadores utilizará automaticamente o `simulation_registry`, mas você pode apontar um CLP para o servidor snap7 real mudando o protocolo para `s7` e ajustando IP/porta.

### 5.2 OPC UA
1. O `OpcUaAdapter` suporta modo simulado quando `asyncua` não está disponível; nesse caso ele consome os valores do `simulation_registry` (mesma infraestrutura dos demais simuladores).【F:src/adapters/opcua_adapter.py†L1-L78】【F:src/simulations/runtime.py†L1-L122】
2. Para testar contra um servidor OPC UA real, instale `asyncua`, ajuste o protocolo do CLP para `opcua` e configure `ip_address`/`port`. O adaptador fará a leitura assíncrona dos *nodes* configurados.【F:src/adapters/opcua_adapter.py†L25-L75】
3. Se quiser simular manualmente sem servidor, defina valores fixos com `simulation_registry.set_static_value("opcua", identificador, valor)` durante o bootstrap dos testes.【F:src/simulations/runtime.py†L53-L82】

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
