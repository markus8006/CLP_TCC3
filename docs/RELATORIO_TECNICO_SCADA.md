# Relatório Técnico do Sistema SCADA Snypse

## 1. Contextualização do Problema na Manufatura Pós-2024

A interrupção não planejada de linhas industriais continua sendo um dos principais centros de custo e risco operacional na manufatura global, mas a escala do problema foi redefinida no cenário pós-2024. Relatórios recentes apontam que o downtime não planejado já consome 11% das receitas anuais das 500 maiores empresas do mundo, representando perdas de aproximadamente US$ 1,4 trilhão por ano — crescimento expressivo frente aos US$ 864 bilhões registrados no período 2019-2020.[1]

### 1.1 A Economia Exponencial do Downtime Não Planejado

O custo médio de uma hora de parada não planejada permanece elevado, com estimativas globais situando a média em US$ 125.000/hora, ainda que esse número oculto grande variabilidade setorial.[2] Em segmentos de alto valor agregado, como o automotivo, uma hora de linha ociosa pode atingir US$ 2,3 milhões, o que equivale a mais de US$ 600 por segundo.[3] A incidência desses eventos também é significativa, acumulando aproximadamente 326 horas de indisponibilidade anuais.[4]

A aceleração dos custos não decorre apenas da inflação, mas da crescente interconexão das operações digitais e da redução de estoques característicos de estratégias *lean*.[5] Em ambientes altamente automatizados, uma única falha pode gerar efeitos em cascata, elevando o custo do downtime de uma relação linear para exponencial. Nessas condições, o monitoramento contínuo deixa de ser desejável e torna-se essencial para a sobrevivência operacional.

### 1.2 A Lacuna de Visibilidade como Risco de Cibersegurança OT/ICS

A perda de visibilidade é um fator crítico em incidentes de segurança, pesquisas recentes reclassificam essa "lacuna de visibilidade" como a principal vulnerabilidade em ambientes de Tecnologia Operacional (OT). A convergência IT/OT ampliou a superfície de ataque e tornou o cenário de ameaças OT/ICS o mais complexo da história recente, com detecção média de incidentes evoluindo de "dias" em 2019 para "horas" em 2024, mas com uma capacidade de resposta ainda limitada.[6]

Mesmo com essa evolução, apenas 56% das organizações possuem um plano de resposta a incidentes específico para ICS, e somente 34% utilizam ferramentas dedicadas para se preparar para ataques em OT.[6] Casos recentes — como os ataques de ransomware à Norsk Hydro e à WestRock — evidenciam o impacto financeiro dessa lacuna de visibilidade, produzindo perdas de US$ 70 milhões e 85.000 toneladas de produto, respectivamente.[7] Em ambos os incidentes, os atacantes exploraram brechas de monitoramento entre as redes de TI e OT.

Nesse contexto, sistemas SCADA como o Synapse extrapolam o papel tradicional de produtividade e atuam como ferramentas de defesa ciberfísica. A capacidade de acompanhar continuamente variáveis de processo e gerar alarmes em tempo real permite detectar anomalias operacionais que podem sinalizar falhas de equipamento ou ataques cibernéticos em progresso.[8]

### 1.3 Fragmentação de Dados e a Barreira da Convergência IT/OT

A heterogeneidade de protocolos de comunicação permanece sendo o obstáculo número um para a transformação digital na indústria.[9] Estimativas recentes revelam que 84% das organizações ainda enfrentam dados inacessíveis ou segregados em silos, bloqueando projetos de inovação baseados em analytics. O desafio surge da lacuna entre sistemas SCADA legados, que operam com protocolos como Modbus ou S7, e plataformas IIoT e de nuvem, que utilizam protocolos modernos como MQTT, resultando em dados fragmentados e difícil escalabilidade.[9][10]

**O Synapse endereça esse "primeiro quilômetro" da convergência ao centralizar protocolos Modbus TCP, Siemens S7 e OPC UA em uma camada de abstração unificada. Essa agregação transforma dados brutos em uma única fonte de verdade, pré-requisito fundamental para iniciativas de IA, *machine learning* e manutenção preditiva (PdM).[10]**

## 2. Objetivos Estratégicos do Projeto

O projeto Synapse foi concebido para alcançar objetivos estratégicos diretamente alinhados com o cenário descrito:

1. **Centralizar a supervisão multi-protocolo**: habilitar leitura contínua de registradores em CLPs Modbus TCP, Siemens S7 e servidores OPC UA, com suporte nativo a simulação, agora orquestrados por um serviço Go exposto via gRPC e configurado dinamicamente a partir do Python.【F:run.py†L1-L209】【F:go/polling/cmd/poller/main.go†L1-L165】
2. **Detectar e gerenciar alarmes operacionais em tempo real**: avaliar leituras contra setpoints, faixas e histerese (*deadband*), gerando eventos de disparo e normalização com notificação automática.【F:src/services/Alarms_service.py†L16-L137】【F:run.py†L131-L205】
3. **Garantir operação resiliente e escalável**: manter um loop de polling contínuo e tolerante a falhas através do `PollingService`, que publica medições por *streaming* gRPC para o orquestrador Python, com atualização dinâmica de configuração.【F:go/polling/cmd/poller/main.go†L67-L165】【F:src/manager/go_polling_manager.py†L21-L140】
4. **Facilitar implantação e ensaios**: provisionar CLPs simulados, registradores e alarmes de forma automatizada, acelerando provas de conceito e validações sem hardware físico.【F:run.py†L107-L209】【F:src/simulations/runtime.py†L1-L122】

## 3. Arquitetura Técnica e Alinhamento Estratégico com a Indústria 4.0

### 3.1 Camada de Aplicação (Contexto de Execução Flask)

A aplicação Flask, inicializada por `create_app`, atua como contêiner central, registra *blueprints*, integra banco de dados (SQLAlchemy) e expõe funcionalidades via APIs REST e interfaces web.【F:src/app/__init__.py†L1-L71】 A execução padrão (`run.py`) configura o ambiente, instancia o servidor HTTP na porta 5000 e aciona rotinas de provisão e polling.【F:run.py†L1-L209】 Esse desenho possibilita operação *headless*, servindo dados para dashboards de BI, sistemas MES ou plataformas de nuvem em vez de depender de um HMI monolítico.

### 3.2 Orquestração de Polling (Motor de Resiliência)

A resiliência passa a ser provida por um serviço Go dedicado (`PollingService`) que mantém o estado da configuração em memória, realiza leituras periódicas (ticker de 2s) e publica medições por *streaming* gRPC.【F:go/polling/cmd/poller/main.go†L67-L165】 O cliente Python (`GoPollingManager`) gere o ciclo de vida do processo Go como *subprocess*, estabelece o canal gRPC, aplica atualizações de configuração e encaminha o stream para a fila de ingestão.【F:src/manager/go_polling_manager.py†L21-L140】 O `PollingRuntime` mantém o estado compartilhado (fila, *threads* e sinalizadores) para integração com a aplicação Flask.【F:src/services/polling_runtime.py†L1-L68】

### 3.3 Pipeline de Ingestão e Normalização

O `run.py` centraliza a construção da configuração (função `build_go_poller_config`), serializando CLPs e registradores activos para o formato esperado pelo `PollingService`.【F:run.py†L210-L308】 Cada evento recebido via gRPC é processado pela `process_poller_payload`, que persiste as leituras, actualiza estados on-line/off-line e aciona a lógica de alarmes.【F:run.py†L309-L360】【F:src/services/poller_ingest_service.py†L1-L160】 Esse desenho substitui completamente os adaptadores Python legados, simplificando a manutenção e eliminando a dependência de `stdin/stdout` entre processos.

### 3.4 Gestão de Alarmes e Notificações (Camada de Resposta)

O `AlarmService` avalia continuamente as leituras de registradores contra regras definidas (acima, abaixo, dentro/fora de faixa) e aplica *deadband* para evitar *chattering*. Ao confirmar uma condição de alarme, registra eventos, atualiza estados e dispara notificações conforme perfis autorizados.【F:src/services/Alarms_service.py†L16-L219】 Essa camada conecta a detecção de dados à ação humana, gerando trilha de auditoria para análises forenses e resposta a incidentes.

### 3.5 Persistência e Auditoria (Camada de Histórico)

A camada de repositórios baseada em SQLAlchemy (`BaseRepo`, `PlcRepo`, `RegRepo`, `AlarmRepo`) garante persistência transacional de leituras, estados de CLP e eventos de alarme.【F:src/repository/Base_repository.py†L1-L118】【F:src/repository/PLC_repository.py†L1-L69】【F:src/repository/Alarms_repository.py†L1-L48】 Esse histórico transforma o Synapse em um *process historian*, permitindo análises de tendência e habilitando manutenção preditiva. O job `cleanup_old_data` gerencia o ciclo de vida dessas informações.【F:src/jobs/cleanup_old_data.py†L1-L63】

### 3.6 Análise Estratégica de Protocolos e Convergência IT/OT

O suporte simultâneo a Modbus TCP, Siemens S7 e OPC UA posiciona o Synapse como plataforma de agregação de dados brownfield, enquanto prepara a expansão para padrões de interoperabilidade exigidos pela Indústria 4.0.[11][12][13] As pesquisas mais recentes indicam que a arquitetura vencedora é a combinação OPC UA sobre MQTT, unindo modelo de dados semântico ao transporte *publish-subscribe* escalável.[14] Como o Synapse já unifica dados e alarmes internamente, a evolução natural consiste em adicionar um serviço de publicação (ex.: `MqttPublisherService`) para enviar eventos de processo e alarmes a *brokers* de nuvem, completando a ponte IT/OT.

**Tabela 3.6.1 — Análise Estratégica de Protocolos na Arquitetura Synapse**

| Protocolo       | Domínio Principal               | Papel Semântico                         | Papel no Synapse             | Próximo Passo (Convergência IT/OT)               |
| --------------- | ------------------------------- | --------------------------------------- | ---------------------------- | ------------------------------------------------ |
| Modbus TCP      | OT legada (sensores, atuadores) | Baixo — leitura de registradores brutos | Compatibilidade *brownfield* | Agregação/tradução de dados pelo Synapse         |
| Siemens S7      | Controle de máquina (CLPs)      | Médio — *data blocks* estruturados      | Coleta primária de controle  | Agregação/tradução de dados pelo Synapse         |
| OPC UA          | Comunicação M2M interoperável   | Alto — modelo de informação semântica   | Padrão da Indústria 4.0      | Espelhamento e enriquecimento do modelo de dados |
| MQTT (expansão) | Edge-to-cloud (IIoT)            | N/A (transporte de mensagens)           | Não implementado             | Publicação de dados e alarmes para a nuvem       |

## 4. Fluxo Operacional

1. **Provisionamento automático**: `setup_all_plcs` gera CLPs por protocolo, cria registradores, associa alarmes e pré-carrega valores simulados, garantindo ambiente funcional imediato.【F:run.py†L131-L209】
2. **Início do polling**: `run.py` instancia o `GoPollingManager`, publica a configuração inicial via gRPC (`UpdateConfig`) e inicia o consumo contínuo do `StreamData`, registrando o runtime para controle operacional.【F:run.py†L309-L360】【F:src/manager/go_polling_manager.py†L21-L140】
3. **Monitoramento e alarmes**: cada leitura recebida via gRPC é processada por `process_poller_payload`, que valida os dados, persiste no histórico e aciona a avaliação de alarmes pelo `AlarmService`.【F:run.py†L309-L360】【F:src/services/poller_ingest_service.py†L1-L160】【F:src/services/Alarms_service.py†L88-L219】
4. **Interação operacional**: usuários acessam a interface Flask para visualizar estados, históricos e administrar definições de CLP/alarme na camada `src/app`.【F:src/app/__init__.py†L1-L71】

## 5. Configurações Relevantes e Pontos de Otimização

- **Número padrão de CLPs simulados**: `CLPS_POR_PROTOCOLO = 5`, ajustável conforme demandas de teste.【F:run.py†L22-L24】
- **Tempos de polling e timeout**: definidos em `ProtocolConfig`, incluindo `polling_interval` (ms) e `timeout` (ms) para leituras resilientes.【F:run.py†L32-L130】
- **Template de registradores**: `RegisterTemplate` consolida endereço, tipo, unidade e alarme associado, garantindo consistência na replicação de pontos.【F:run.py†L26-L130】
- **Consumo assíncrono do stream**: a *thread* `go-poller-consumer` processa o stream gRPC em tempo real, garantindo persistência e avaliação de alarmes sem bloquear o loop principal do Flask.【F:run.py†L309-L360】
- **Simulações**: o `simulation_registry` permite `set_static_value`, `next_value` e `clear` para testes determinísticos sem hardware real.【F:src/simulations/runtime.py†L17-L109】

## 6. Análise de Impacto e Geração de Valor

### 6.1 Redução Direta de Downtime e Aumento de OEE

O Synapse contribui diretamente para reduzir custos de downtime. Com médias globais de US$ 125.000 por hora e picos de US$ 2,3 milhões em setores automotivos, cada minuto de indisponibilidade evitado gera retorno expressivo.[2][3] A detecção em tempo real de condições de alarme pelo `AlarmService` reduz o Tempo Médio de Reparo (MTTR) e aumenta o OEE, com estudos apontando saltos de 75% para 85% em linhas de montagem após integrações IIoT semelhantes.[16][18]

Uma redução de apenas dez minutos de downtime mensal em uma planta automotiva representa economia potencial de mais de US$ 380.000, considerando métricas atuais de custo de parada.[3][20] Em muitos cenários, o sistema se paga no primeiro incidente relevante que ajuda a prevenir ou encurtar.

### 6.2 Fortalecimento da Postura de Cibersegurança Operacional

O Synapse funciona como ferramenta de segurança passiva ao cobrir a lacuna de visibilidade identificada pelas pesquisas de ICS/OT. Ao manter um baseline dos processos, qualquer ataque que altere setpoints ou manipule leituras pode ser detectado como desvio operacional, mesmo que ferramentas de TI não sinalizem tráfego malicioso.[6][7] A trilha de auditoria mantida em `AlarmRepo` é valiosa para análise de causa raiz após incidentes e colabora com requisitos de conformidade em setores regulados.[19]

### 6.3 Habilitação Estratégica da Manutenção Preditiva (PdM)

A manutenção preditiva depende de dados históricos consistentes e acessíveis. Ao unificar a coleta multi-protocolo e garantir persistência, o Synapse fornece a camada OT necessária para projetos de PdM e analytics avançado.[10][15] Estimativas apontam que a adoção ampla de monitoramento de condição e PdM pode gerar economias de até US$ 233 bilhões anuais apenas entre empresas Fortune 500.[17] Dessa forma, o sistema deixa de ser apenas um SCADA e torna-se alicerce para a migração de modelos de manutenção reativos para preditivos.

## 7. Referências (Atualizadas 2023-2025)

1. Siemens AG. (2024). *The True Cost of Downtime 2024*. ###
2. ABB. (2023). *Pesquisa global realizada pela ABB destaca... custo de US$ 125.000 por hora*. ###
3. Siemens Blog. (2024). *The True Cost of an Hour's Downtime: An Industry Analysis*. ###
4. L2L. (2025). *2025 Report: Manufacturing Downtime*. ###
5. MaintainX / Siemens. (2024). *The 2025 State of Industrial Maintenance / True Cost of Downtime 2024*. ###
6. SANS Institute. (2024). *The 2024 State of ICS/OT Cybersecurity*. ###
7. ARC Advisory Group. (2024). *Insights from the 28th Annual ARC Industry Leadership Forum*. ###
8. Carmel Tecnologia. (2024). *SCADA vs. IIoT: Qual é melhor para suas operações?*. ###
9. IIoT World & NetApp. (2024). *Data-Driven Manufacturing: From Challenges to Scalable Solutions*. ###
10. LNS Research. (2024). *Manufacturing Trends & Future-Proof Operations*. ###
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


- The True Cost of Downtime 2024 - Siemens. Disponível em: https://assets.new.siemens.com/siemens/assets/api/uuid:1b43afb5-2d07-47f7-9eb7-893fe7d0bc59/TCOD-2024_original.pdf
- Pesquisa ABB sobre downtime - https://new.abb.com/news/pt-br/detail/107660/pesquisa-feita-pela-abb-revela-que-o-tempo-da-inatividade-nao-planejada-custa-us-125000-por-hora
- The True Cost of an Hour's Downtime - https://blog.siemens.com/2024/07/the-true-cost-of-an-hours-downtime-an-industry-analysis/
- 2025 Report: Manufacturing Downtime - https://www.l2l.com/blog/2025-report-manufacturing-downtime
- The 2025 State of Industrial Maintenance - https://www.getmaintainx.com/blog/maintenance-stats-trends-and-insights
- The 2024 State of ICS/OT Cybersecurity - https://www.sans.org/blog/the-2024-state-of-ics-ot-cybersecurity-our-past-and-our-future
- ARC Forum 2024 - https://www.ptc.com/en/blogs/iiot/arc-forum-2024
- SCADA vs. IIoT - https://www.carmeltecnologia.com.br/post/scada-vs-iiot-qual-e-melhor-para-suas-operacoes
- Data-Driven Manufacturing - https://www.tudosobreiot.com.br/blog/16537-iiot-na-manufatura-de-desafios-as-solucoes-escalaveis
- Manufacturing Trends & Future-Proof Operations - https://blog.lnsresearch.com/the-future-of-manufacturing-transformation-rethink-2024-highlights
- OPC UA vs. Modbus vs. MQTT - https://zenithindustrialcloud.com/en/resources/opcua-vs-modbus-vs-mqtt-iiot-protocols/
- OPC UA vs. MQTT (i-flow) - https://i-flow.io/en/ressources/opc-ua-vs-mqtt-a-comparison-of-the-most-important-features/
- Leading IoT Vendors Commit to OPC UA Adoption - https://opcconnect.opcfoundation.org/2022/03/leading-iot-vendors-commit-to-opc-ua-adoption/
- OPC UA over MQTT - https://www.emqx.com/en/blog/opc-ua-over-mqtt-the-future-of-it-and-ot-convergence
- Predictive Maintenance Market - https://iot-analytics.com/predictive-maintenance-market/
- Leveraging IIoT solutions - https://www.mdpi.com/2227-9717/12/11/2611
- Manutenção: Estatísticas, Desafios e Tendências - https://blog.infraspeak.com/pt-br/manutencao-estatisticas-desafios-tendencias/
- OEE: O que é, como calcular e importância - https://www.probool.com/?p=1624
- 2025 OT Cybersecurity Report - https://www.dragos.com/ot-cybersecurity-year-in-review
- - The True Costs of Downtime in 2025 - https://www.erwoodgroup.com/blog/the-true-costs-of-downtime-in-2025-a-deep-dive-by-business-size-and-industry/
