# Relatório Técnico do Sistema SCADA CLP_TCC3

## 1. Contextualização do Problema na Manufatura Pós-2024

A interrupção não planejada de linhas industriais continua sendo um dos principais centros de custo e risco operacional na manufatura global, mas a escala do problema foi redefinida no cenário pós-2024. Relatórios recentes apontam que o downtime não planejado já consome 11% das receitas anuais das 500 maiores empresas do mundo, representando perdas de aproximadamente US$ 1,4 trilhão por ano — crescimento expressivo frente aos US$ 864 bilhões registrados no período 2019-2020.[1]

### 1.1 A Economia Exponencial do Downtime Não Planejado

O custo médio de uma hora de parada não planejada permanece elevado, com estimativas globais situando a média em US$ 125.000/hora, ainda que esse número masque grande variabilidade setorial.[2] Em segmentos de alto valor agregado, como o automotivo, uma hora de linha ociosa pode atingir US$ 2,3 milhões, o que equivale a mais de US$ 600 por segundo.[3] A incidência desses eventos também é significativa: plantas industriais enfrentam em média 25 incidentes de parada não planejada por mês, acumulando aproximadamente 326 horas de indisponibilidade anuais.[4]

A aceleração dos custos não decorre apenas da inflação, mas da crescente interconexão das operações digitais e da redução de estoques característicos de estratégias *lean*.[5] Em ambientes altamente automatizados, uma única falha pode gerar efeitos em cascata, elevando o custo do downtime de uma relação linear para exponencial. Nessas condições, o monitoramento contínuo deixa de ser desejável e torna-se essencial para a sobrevivência operacional.

### 1.2 A Lacuna de Visibilidade como Risco de Cibersegurança OT/ICS

O relatório original já sinalizava a perda de visibilidade como fator crítico em incidentes de segurança. Pesquisas recentes reclassificam essa "lacuna de visibilidade" como a principal vulnerabilidade em ambientes de Tecnologia Operacional (OT). A convergência IT/OT ampliou a superfície de ataque e tornou o cenário de ameaças OT/ICS o mais complexo da história recente, com detecção média de incidentes evoluindo de "dias" em 2019 para "horas" em 2024, mas com uma capacidade de resposta ainda limitada.[6]

Mesmo com essa evolução, apenas 56% das organizações possuem um plano de resposta a incidentes específico para ICS, e somente 34% utilizam ferramentas dedicadas para se preparar para ataques em OT.[6] Casos recentes — como os ataques de ransomware à Norsk Hydro e à WestRock — evidenciam o impacto financeiro dessa lacuna de visibilidade, produzindo perdas de US$ 70 milhões e 85.000 toneladas de produto, respectivamente.[7] Em ambos os incidentes, os atacantes exploraram brechas de monitoramento entre as redes de TI e OT.

Nesse contexto, sistemas SCADA como o CLP_TCC3 extrapolam o papel tradicional de produtividade e atuam como ferramentas de defesa ciberfísica. A capacidade de acompanhar continuamente variáveis de processo e gerar alarmes em tempo real permite detectar anomalias operacionais que podem sinalizar falhas de equipamento ou ataques cibernéticos em progresso.[8]

### 1.3 Fragmentação de Dados e a Barreira da Convergência IT/OT

A heterogeneidade de protocolos de comunicação permanece sendo o obstáculo número um para a transformação digital na indústria.[9] Estimativas recentes revelam que 84% das organizações ainda enfrentam dados inacessíveis ou segregados em silos, bloqueando projetos de inovação baseados em analytics. O desafio surge da lacuna entre sistemas SCADA legados, que operam com protocolos como Modbus ou S7, e plataformas IIoT e de nuvem, que utilizam protocolos modernos como MQTT, resultando em dados fragmentados e difícil escalabilidade.[9][10]

O CLP_TCC3 endereça esse "primeiro quilômetro" da convergência ao centralizar protocolos Modbus TCP, Siemens S7 e OPC UA em uma camada de abstração unificada. Essa agregação transforma dados brutos em uma única fonte de verdade, pré-requisito fundamental para iniciativas de IA, *machine learning* e manutenção preditiva (PdM).[10]

## 2. Objetivos Estratégicos do Projeto

O projeto CLP_TCC3 foi concebido para alcançar objetivos estratégicos diretamente alinhados com o cenário descrito:

1. **Centralizar a supervisão multi-protocolo**: habilitar leitura contínua de registradores em CLPs Modbus TCP, Siemens S7 e servidores OPC UA, com suporte nativo a simulação.【F:run.py†L32-L130】【F:src/adapters/factory.py†L1-L25】
2. **Detectar e gerenciar alarmes operacionais em tempo real**: avaliar leituras contra setpoints, faixas e histerese (*deadband*), gerando eventos de disparo e normalização com notificação automática.【F:src/services/Alarms_service.py†L16-L137】【F:run.py†L131-L205】
3. **Garantir operação resiliente e escalável**: orquestrar *pollers* assíncronos capazes de reconectar, balancear leituras simultâneas e persistir dados históricos para auditoria.【F:src/manager/client_polling_manager.py†L24-L203】
4. **Facilitar implantação e ensaios**: provisionar CLPs simulados, registradores e alarmes de forma automatizada, acelerando provas de conceito e validações sem hardware físico.【F:run.py†L107-L209】【F:src/simulations/runtime.py†L1-L122】

## 3. Arquitetura Técnica e Alinhamento Estratégico com a Indústria 4.0

### 3.1 Camada de Aplicação (Contexto de Execução Flask)

A aplicação Flask, inicializada por `create_app`, atua como contêiner central, registra *blueprints*, integra banco de dados (SQLAlchemy) e expõe funcionalidades via APIs REST e interfaces web.【F:src/app/__init__.py†L1-L71】 A execução padrão (`run.py`) configura o ambiente, instancia o servidor HTTP na porta 5000 e aciona rotinas de provisão e polling.【F:run.py†L1-L209】 Esse desenho possibilita operação *headless*, servindo dados para dashboards de BI, sistemas MES ou plataformas de nuvem em vez de depender de um HMI monolítico.

### 3.2 Orquestração de Polling (Motor de Resiliência)

O `ActivePLCPoller` é o núcleo da resiliência do sistema. Ele gerencia o ciclo de vida da conexão com cada CLP, aplica *backoff* exponencial para reconexões automáticas e marca estados on-line/off-line no banco.【F:src/manager/client_polling_manager.py†L24-L203】 Para controlar a carga, utiliza `ThreadPoolExecutor` com semáforos, evitando que dispositivos lentos bloqueiem o fluxo de aquisição.【F:src/manager/client_polling_manager.py†L9-L63】 O `SimpleManager` e o `PollingRuntime` orquestram o ciclo desses pollers, permitindo habilitar ou desabilitar CLPs dinamicamente.【F:src/manager/client_polling_manager.py†L205-L271】【F:src/services/polling_runtime.py†L1-L120】

### 3.3 Adapters Multi-Protocolo (Camada de Abstração OT)

A camada de adaptadores resolve o desafio de heterogeneidade de protocolos. Todos os drivers (Modbus, S7, OPC UA) herdam de `BaseAdapter`, que padroniza métodos como `connect`, `disconnect` e `read_register` e converte valores para formatos unificados.【F:src/adapters/base_adapters.py†L1-L101】【F:src/adapters/modbus_adapter.py†L1-L103】【F:src/adapters/s7_adapter.py†L1-L86】【F:src/adapters/opcua_adapter.py†L1-L69】 A fábrica `get_adapter` mantém o `ActivePLCPoller` agnóstico ao protocolo subjacente, permitindo tratamento uniforme das fontes de dados.【F:src/adapters/factory.py†L1-L25】

### 3.4 Gestão de Alarmes e Notificações (Camada de Resposta)

O `AlarmService` avalia continuamente as leituras de registradores contra regras definidas (acima, abaixo, dentro/fora de faixa) e aplica *deadband* para evitar *chattering*. Ao confirmar uma condição de alarme, registra eventos, atualiza estados e dispara notificações conforme perfis autorizados.【F:src/services/Alarms_service.py†L16-L219】 Essa camada conecta a detecção de dados à ação humana, gerando trilha de auditoria para análises forenses e resposta a incidentes.

### 3.5 Persistência e Auditoria (Camada de Histórico)

A camada de repositórios baseada em SQLAlchemy (`BaseRepo`, `PlcRepo`, `RegRepo`, `AlarmRepo`) garante persistência transacional de leituras, estados de CLP e eventos de alarme.【F:src/repository/Base_repository.py†L1-L118】【F:src/repository/PLC_repository.py†L1-L69】【F:src/repository/Alarms_repository.py†L1-L48】 Esse histórico transforma o CLP_TCC3 em um *process historian*, permitindo análises de tendência e habilitando manutenção preditiva. O job `cleanup_old_data` gerencia o ciclo de vida dessas informações.【F:src/jobs/cleanup_old_data.py†L1-L63】

### 3.6 Análise Estratégica de Protocolos e Convergência IT/OT

O suporte simultâneo a Modbus TCP, Siemens S7 e OPC UA posiciona o CLP_TCC3 como plataforma de agregação de dados brownfield, enquanto prepara a expansão para padrões de interoperabilidade exigidos pela Indústria 4.0.[11][12][13] As pesquisas mais recentes indicam que a arquitetura vencedora é a combinação OPC UA sobre MQTT, unindo modelo de dados semântico ao transporte *publish-subscribe* escalável.[14] Como o CLP_TCC3 já unifica dados e alarmes internamente, a evolução natural consiste em adicionar um serviço de publicação (ex.: `MqttPublisherService`) para enviar eventos de processo e alarmes a *brokers* de nuvem, completando a ponte IT/OT.

**Tabela 3.6.1 — Análise Estratégica de Protocolos na Arquitetura CLP_TCC3**

| Protocolo    | Domínio Principal                       | Papel Semântico                           | Papel no CLP_TCC3                          | Próximo Passo (Convergência IT/OT)                |
|--------------|-----------------------------------------|-------------------------------------------|--------------------------------------------|--------------------------------------------------|
| Modbus TCP   | OT legada (sensores, atuadores)         | Baixo — leitura de registradores brutos   | Compatibilidade *brownfield*               | Agregação/tradução de dados pelo CLP_TCC3        |
| Siemens S7   | Controle de máquina (CLPs)              | Médio — *data blocks* estruturados        | Coleta primária de controle                | Agregação/tradução de dados pelo CLP_TCC3        |
| OPC UA       | Comunicação M2M interoperável          | Alto — modelo de informação semântica     | Padrão da Indústria 4.0                    | Espelhamento e enriquecimento do modelo de dados |
| MQTT (expansão) | Edge-to-cloud (IIoT)                 | N/A (transporte de mensagens)             | Não implementado                           | Publicação de dados e alarmes para a nuvem       |

## 4. Fluxo Operacional

1. **Provisionamento automático**: `setup_all_plcs` gera CLPs por protocolo, cria registradores, associa alarmes e pré-carrega valores simulados, garantindo ambiente funcional imediato.【F:run.py†L131-L209】
2. **Início do polling**: `run_async_polling` registra o `PollingRuntime`, identifica CLPs ativos e injeta cada um no `SimpleManager`, iniciando a coleta contínua.【F:src/services/client_polling_service.py†L1-L24】
3. **Monitoramento e alarmes**: cada leitura passa pelo `AlarmService`, que avalia condições, dispara notificações e atualiza estados on-line/off-line no banco, habilitando dashboards em tempo real.【F:src/manager/client_polling_manager.py†L90-L203】【F:src/services/Alarms_service.py†L88-L219】
4. **Interação operacional**: usuários acessam a interface Flask para visualizar estados, históricos e administrar definições de CLP/alarme na camada `src/app`.【F:src/app/__init__.py†L1-L71】

## 5. Configurações Relevantes e Pontos de Otimização

- **Número padrão de CLPs simulados**: `CLPS_POR_PROTOCOLO = 5`, ajustável conforme demandas de teste.【F:run.py†L22-L24】
- **Tempos de polling e timeout**: definidos em `ProtocolConfig`, incluindo `polling_interval` (ms) e `timeout` (ms) para leituras resilientes.【F:run.py†L32-L130】
- **Template de registradores**: `RegisterTemplate` consolida endereço, tipo, unidade e alarme associado, garantindo consistência na replicação de pontos.【F:run.py†L26-L130】
- **Gerenciamento de threads**: o `ActivePLCPoller` usa `ThreadPoolExecutor` com `max_workers` proporcional aos núcleos disponíveis, equilibrando desempenho e consumo de recursos.【F:src/manager/client_polling_manager.py†L9-L63】
- **Simulações**: o `simulation_registry` permite `set_static_value`, `next_value` e `clear` para testes determinísticos sem hardware real.【F:src/simulations/runtime.py†L17-L109】

## 6. Análise de Impacto e Geração de Valor

### 6.1 Redução Direta de Downtime e Aumento de OEE

O CLP_TCC3 contribui diretamente para reduzir custos de downtime. Com médias globais de US$ 125.000 por hora e picos de US$ 2,3 milhões em setores automotivos, cada minuto de indisponibilidade evitado gera retorno expressivo.[2][3] A detecção em tempo real de condições de alarme pelo `AlarmService` reduz o Tempo Médio de Reparo (MTTR) e aumenta o OEE, com estudos apontando saltos de 75% para 85% em linhas de montagem após integrações IIoT semelhantes.[16][18]

Uma redução de apenas dez minutos de downtime mensal em uma planta automotiva representa economia potencial de mais de US$ 380.000, considerando métricas atuais de custo de parada.[3][20] Em muitos cenários, o sistema se paga no primeiro incidente relevante que ajuda a prevenir ou encurtar.

### 6.2 Fortalecimento da Postura de Cibersegurança Operacional

O CLP_TCC3 funciona como ferramenta de segurança passiva ao cobrir a lacuna de visibilidade identificada pelas pesquisas de ICS/OT. Ao manter um baseline dos processos, qualquer ataque que altere setpoints ou manipule leituras pode ser detectado como desvio operacional, mesmo que ferramentas de TI não sinalizem tráfego malicioso.[6][7] A trilha de auditoria mantida em `AlarmRepo` é valiosa para análise de causa raiz após incidentes e colabora com requisitos de conformidade em setores regulados.[19]

### 6.3 Habilitação Estratégica da Manutenção Preditiva (PdM)

A manutenção preditiva depende de dados históricos consistentes e acessíveis. Ao unificar a coleta multi-protocolo e garantir persistência, o CLP_TCC3 fornece a camada OT necessária para projetos de PdM e analytics avançado.[10][15] Estimativas apontam que a adoção ampla de monitoramento de condição e PdM pode gerar economias de até US$ 233 bilhões anuais apenas entre empresas Fortune 500.[17] Dessa forma, o sistema deixa de ser apenas um SCADA e torna-se alicerce para a migração de modelos de manutenção reativos para preditivos.

## 7. Referências (Atualizadas 2023-2025)

1. Siemens AG. (2024). *The True Cost of Downtime 2024*.
2. ABB. (2023). *Pesquisa global realizada pela ABB destaca... custo de US$ 125.000 por hora*.
3. Siemens Blog. (2024). *The True Cost of an Hour's Downtime: An Industry Analysis*.
4. L2L. (2025). *2025 Report: Manufacturing Downtime*.
5. MaintainX / Siemens. (2024). *The 2025 State of Industrial Maintenance / True Cost of Downtime 2024*.
6. SANS Institute. (2024). *The 2024 State of ICS/OT Cybersecurity*.
7. ARC Advisory Group. (2024). *Insights from the 28th Annual ARC Industry Leadership Forum*.
8. Carmel Tecnologia. (2024). *SCADA vs. IIoT: Qual é melhor para suas operações?*.
9. IIoT World & NetApp. (2024). *Data-Driven Manufacturing: From Challenges to Scalable Solutions*.
10. LNS Research. (2024). *Manufacturing Trends & Future-Proof Operations*.
11. Zenith Industrial Cloud. (2024). *OPC UA vs. Modbus vs. MQTT: IIoT Protocols*.
12. i-flow. (2024). *OPC UA vs. MQTT: A comparison of the most important features*.
13. OPC Foundation. (2022). *Leading IoT vendors commit to OPC UA adoption*.
14. EMQ. (2024). *OPC UA over MQTT: The Future of IT and OT Convergence*.
15. IoT Analytics. (2023). *Predictive Maintenance and Asset Performance Market Report 2023–2028*.
16. MDPI. (2024). *Leveraging IIoT solutions in an industrial setting... increased OEE from 75% to 85%*.
17. Infraspeak Blog. (2024). *Manutenção: Estatísticas, Desafios e Tendências*.
18. Probool. (2024). *OEE: O que é, como calcular e importância*.
19. Dragos. (2025). *2025 OT Cybersecurity Report, Year in Review*.
20. Erwood Group. (2024). *The True Costs of Downtime in 2025*.

### Referências citadas (links de acesso)

- The Monthly Metric: Unscheduled Downtime - Institute for Supply Management. Disponível em: https://www.ismworld.org/supply-management-news-and-reports/news-publications/inside-supply-management-magazine/blog/2024/2024-08/the-monthly-metric-unscheduled-downtime/
- The True Cost of Downtime 2024 - Siemens. Disponível em: https://assets.new.siemens.com/siemens/assets/api/uuid:1b43afb5-2d07-47f7-9eb7-893fe7d0bc59/TCOD-2024_original.pdf
- Pesquisa ABB sobre downtime - https://new.abb.com/news/pt-br/detail/107660/pesquisa-feita-pela-abb-revela-que-o-tempo-da-inatividade-nao-planejada-custa-us-125000-por-hora
- The True Cost of an Hour's Downtime - https://blog.siemens.com/2024/07/the-true-cost-of-an-hours-downtime-an-industry-analysis/
- 2025 Report: Manufacturing Downtime - https://www.l2l.com/blog/2025-report-manufacturing-downtime
- The 2025 State of Industrial Maintenance - https://www.getmaintainx.com/blog/maintenance-stats-trends-and-insights
- Manufacturing Trends & Future-Proof Operations - https://blog.lnsresearch.com/the-future-of-manufacturing-transformation-rethink-2024-highlights
- The 2024 State of ICS/OT Cybersecurity - https://www.sans.org/blog/the-2024-state-of-ics-ot-cybersecurity-our-past-and-our-future
- ARC Forum 2024 - https://www.ptc.com/en/blogs/iiot/arc-forum-2024
- SCADA vs. IIoT - https://www.carmeltecnologia.com.br/post/scada-vs-iiot-qual-e-melhor-para-suas-operacoes
- Data-Driven Manufacturing - https://www.tudosobreiot.com.br/blog/16537-iiot-na-manufatura-de-desafios-as-solucoes-escalaveis
- OPC UA vs. Modbus vs. MQTT - https://zenithindustrialcloud.com/en/resources/opcua-vs-modbus-vs-mqtt-iiot-protocols/
- OPC UA vs. MQTT (i-flow) - https://i-flow.io/en/ressources/opc-ua-vs-mqtt-a-comparison-of-the-most-important-features/
- Leading IoT Vendors Commit to OPC UA Adoption - https://opcconnect.opcfoundation.org/2022/03/leading-iot-vendors-commit-to-opc-ua-adoption/
- OPC UA over MQTT - https://www.emqx.com/en/blog/opc-ua-over-mqtt-the-future-of-it-and-ot-convergence
- Predictive Maintenance Market - https://iot-analytics.com/predictive-maintenance-market/
- Leveraging IIoT solutions - https://www.mdpi.com/2227-9717/12/11/2611
- Manutenção: Estatísticas, Desafios e Tendências - https://blog.infraspeak.com/pt-br/manutencao-estatisticas-desafios-tendencias/
- OEE: O que é, como calcular e importância - https://www.probool.com/?p=1624
- 2025 OT Cybersecurity Report - https://www.dragos.com/ot-cybersecurity-year-in-review
- The True Costs of Downtime in 2025 - https://www.erwoodgroup.com/blog/the-true-costs-of-downtime-in-2025-a-deep-dive-by-business-size-and-industry/
