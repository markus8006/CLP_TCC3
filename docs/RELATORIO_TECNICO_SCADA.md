# Relatório Técnico do Sistema SCADA CLP_TCC3

## 1. Contextualização do Problema

A interrupção não planejada de linhas industriais segue como um dos maiores centros de custo da manufatura avançada. Estudo da Deloitte estimou que paradas imprevistas causam perdas de pelo menos US$ 50 bilhões anuais na manufatura global, com 42% desse impacto ligado diretamente a falhas de ativos em chão de fábrica [1]. Relatório da Aberdeen Strategy & Research indica que plantas industriais enfrentam, em média, 800 horas de indisponibilidade por ano, com custo superior a US$ 260 mil por hora em segmentos discretos de alto valor agregado [2]. Além do impacto financeiro, 82% dos incidentes de segurança industrial analisados pela ARC Advisory Group envolveram perda de visibilidade operacional sobre variáveis críticas de processo [3].

Esses números evidenciam a necessidade de soluções SCADA (Supervisory Control and Data Acquisition) capazes de monitorar múltiplos controladores lógicos programáveis (CLPs), identificar condições anormais em tempo real e acionar equipes antes que as falhas degradem a produção. No entanto, a heterogeneidade de protocolos (Modbus, Siemens S7, OPC UA), a necessidade de coleta resiliente e a rastreabilidade completa de alarmes ainda são desafios significativos na indústria 4.0.

## 2. Objetivos do Projeto

O projeto CLP_TCC3 foi concebido para:

1. **Centralizar a supervisão multi-protocolo**: habilitar leitura contínua de registradores em CLPs Modbus TCP, Siemens S7 e servidores OPC UA, com suporte à simulação para ambientes de testes.【F:run.py†L32-L130】【F:src/adapters/factory.py†L1-L25】
2. **Detectar e gerenciar alarmes operacionais em tempo real**: avaliar leituras contra definições de setpoint, histerese (*deadband*) e faixas, gerando eventos de disparo e normalização com notificação automática.【F:src/services/Alarms_service.py†L16-L137】【F:run.py†L131-L205】
3. **Garantir operação resiliente e escalável**: orquestrar *pollers* assíncronos capazes de reconectar, balancear leituras simultâneas e persistir dados históricos para auditoria.【F:src/manager/client_polling_manager.py†L24-L203】
4. **Facilitar implantação e ensaios**: provisionar CLPs simulados, registradores e alarmes de forma automatizada, acelerando provas de conceito e validações em *testbeds* sem hardware físico.【F:run.py†L107-L209】【F:src/simulations/runtime.py†L1-L122】

## 3. Arquitetura Técnica

### 3.1 Camada de Aplicação

A aplicação Flask é inicializada por `create_app`, que registra *blueprints*, extensões e integrações com banco de dados, servindo como contexto comum para os demais serviços.【F:src/app/__init__.py†L1-L71】 A execução padrão (`run.py`) instancia a aplicação, configura CLPs e inicializa o servidor HTTP na porta 5000, permitindo supervisão via interface web ou APIs REST.【F:run.py†L1-L209】

### 3.2 Orquestração de Polling

O módulo `client_polling_manager` define o `ActivePLCPoller`, responsável por:

- Selecionar dinamicamente o adaptador de protocolo por meio da fábrica `get_adapter`.
- Estabelecer conexões robustas com *backoff* exponencial e marcação de estado on-line/off-line.
- Distribuir leituras de registradores em tarefas assíncronas concorrentes com semáforos para limitar paralelismo.
- Persistir *batches* de dados e acionar a avaliação de alarmes a cada amostra.

Essa lógica garante que a coleta se mantenha estável mesmo diante de perda de conectividade ou aumento de carga.【F:src/manager/client_polling_manager.py†L24-L203】 O `SimpleManager` encapsula o ciclo de vida dos pollers, permitindo habilitar ou desabilitar CLPs dinamicamente no `PollingRuntime`.【F:src/manager/client_polling_manager.py†L205-L271】【F:src/services/polling_runtime.py†L1-L120】

### 3.3 Adapters Multi-Protocolo

Os drivers Modbus, S7 e OPC UA herdam de `BaseAdapter`, padronizando métodos (`connect`, `disconnect`, `read_register`) e convertendo valores brutos em floats utilizáveis pela camada de alarmes.【F:src/adapters/base_adapters.py†L1-L101】【F:src/adapters/modbus_adapter.py†L1-L103】【F:src/adapters/s7_adapter.py†L1-L86】【F:src/adapters/opcua_adapter.py†L1-L69】 Todos suportam modo simulado integrado ao `simulation_registry`, que gera valores determinísticos para testes repetíveis.【F:src/simulations/runtime.py†L1-L122】

### 3.4 Gestão de Alarmes e Notificações

O `AlarmService` centraliza a avaliação de condições (*above*, *below*, *inside/outside range*), aplica *deadband* para evitar *chattering*, cria eventos de disparo/normalização e dispara e-mails conforme o perfil mínimo autorizado (`UserRole`).【F:src/services/Alarms_service.py†L16-L219】 As definições de alarmes são persistidas em `AlarmDefinitionRepo`, permitindo rastreabilidade completa das regras aplicadas.【F:src/repository/Alarms_repository.py†L1-L48】

### 3.5 Persistência e Auditoria

A camada de repositórios (`BaseRepo`, `Plcrepo`, `RegRepo`, `AlarmRepo`) encapsula operações SQLAlchemy, garantindo consistência transacional e logs. O job `cleanup_old_data` pode ser agendado para controlar crescimento do histórico.【F:src/repository/Base_repository.py†L1-L118】【F:src/repository/PLC_repository.py†L1-L69】【F:src/jobs/cleanup_old_data.py†L1-L63】

## 4. Fluxo Operacional

1. **Provisionamento automático**: `setup_all_plcs` gera CLPs por protocolo, cria registradores, associa alarmes e pré-carrega valores simulados, garantindo ambiente funcional imediato.【F:run.py†L131-L209】
2. **Início do polling**: `run_async_polling` registra o `PollingRuntime`, descobre CLPs ativos e injeta cada um no `SimpleManager`, dando início à coleta contínua.【F:src/services/client_polling_service.py†L1-L24】
3. **Monitoramento e alarmes**: cada leitura passa pelo `AlarmService`, que dispara notificações e atualiza estados on-line/off-line no banco, permitindo dashboards em tempo real.【F:src/manager/client_polling_manager.py†L90-L203】【F:src/services/Alarms_service.py†L88-L219】
4. **Interação operacional**: usuários acessam a interface Flask para visualizar estados, históricos e administrar definições de CLP/alarme (camadas implementadas em `src/app`).【F:src/app/__init__.py†L1-L71】

## 5. Configurações Relevantes

- **Número padrão de CLPs simulados**: `CLPS_POR_PROTOCOLO = 5`, podendo ser ajustado conforme demanda de testes.【F:run.py†L22-L24】
- **Tempos de polling e timeout**: definidos em cada `ProtocolConfig`, incluindo `polling_interval` (ms) e `timeout` (ms) para leituras robustas.【F:run.py†L32-L130】
- **Template de registradores**: `RegisterTemplate` consolida endereço, tipo, unidade e alarme associado, garantindo consistência ao replicar pontos de medição.【F:run.py†L26-L130】
- **Gerenciamento de threads**: `ActivePLCPoller` utiliza `ThreadPoolExecutor` com `max_workers` proporcional aos núcleos disponíveis, equilibrando desempenho e consumo de recursos.【F:src/manager/client_polling_manager.py†L9-L63】
- **Simulações**: `simulation_registry` permite `set_static_value`, `next_value` e `clear` para controlar testes determinísticos sem hardware real.【F:src/simulations/runtime.py†L17-L109】

## 6. Benefícios para a Indústria

Ao combinar orquestração multi-protocolo, avaliação de alarmes com histerese e provisionamento automatizado de ambientes, o CLP_TCC3 reduz o tempo de resposta a anomalias, melhora a disponibilidade e fornece trilha de auditoria completa para conformidade. Em contextos onde o custo por hora de parada ultrapassa US$ 260 mil [2], reduzir minutos de indisponibilidade gera retorno significativo. Além disso, a visibilidade unificada mitiga riscos de segurança operacional, aspecto crítico diante do aumento de incidentes ligados a perda de monitoramento [3].

## 7. Referências

[1] Deloitte. *Predictive maintenance and the smart factory*. 2017. Disponível em: https://www2.deloitte.com/us/en/pages/manufacturing/articles/smart-factory-predictive-maintenance.html

[2] Aberdeen Strategy & Research. *The Impact of Unplanned Downtime*. 2016. Disponível em: https://www.aberdeen.com/opspro-essentials/impact-unplanned-downtime/

[3] ARC Advisory Group. *How Industrial Cybersecurity Affects Safety, Productivity, and Quality*. 2020. Disponível em: https://www.arcweb.com/blog/how-industrial-cybersecurity-affects-safety-productivity-quality
