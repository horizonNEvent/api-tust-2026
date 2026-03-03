# Documento de Arquitetura e Proposta Técnica - API Tust 2026

Este documento detalha a estratégia de implementação, deploy em nuvem e gestão da nova API centralizadora de robôs, endereçando formalmente os pontos levantados pela gestão.

## 1. Visão Geral da Solução
A API Tust 2026 atuará como o "Cérebro" (Orquestrador) dos robôs Selenium. Ela gerencia o ciclo de vida completo: **Agendamento -> Execução -> Extração de Dados -> Armazenamento em Nuvem**.

## 2. Proposta de Infraestrutura AWS (Otimização de Custos)

Para evitar os custos de manter um servidor ligado 24/7, propomos uma arquitetura **On-Demand Agendada**:

| Serviço AWS | Função | Estratégia de Custo |
| :--- | :--- | :--- |
| **AWS EC2 (Spot)** | Servidor de execução (Python/Selenium). | Uso de instâncias **Spot** (t3.medium). Redução de até 90% no custo de computação. |
| **AWS EventBridge** | Gatilho de horário (02:00 AM). | Serviço gratuito. Liga a máquina no horário e a API a desliga ao fim das tarefas. |
| **Amazon S3** | Data Lake organizado por Base/Agente. | Custos mínimos (centavos por GB). Armazenamento durável e seguro. |
| **Amazon RDS (Opcional)** | Banco de Dados Gerenciado. | Iniciaremos com SQLite para zero custo, com migração futura para RDS se houver alta concorrência. |

**Estimativa Mensal Total: ~$6.00 a $10.00 USD** (rodando 3-5h por dia).

## 3. Arquitetura Multi-Tenant (Escalabilidade)

Para suportar as 4 bases atuais (**AETE, DE, RE, AE**) e as futuras:
- **Banco Único:** Centralização de manutenção. Isolamento lógico via campo `base_id` em todas as tabelas.
- **Isolamento de Credenciais:** Cada configuração de robô possui seu próprio conjunto de credenciais e lista de empresas (Agentes), garantindo que os dados nunca se misturem.
- **Escalabilidade:** Para adicionar uma nova base ou transmissora, não é necessário código novo, apenas um cadastro via endpoint na API existente.

## 4. Gestão de Logs e Erros
- **Logs Persistentes:** Cada execução gera um ID único. O `stdout` e o `stderr` do robô são capturados em tempo real e gravados no banco de dados.
- **Status da Execução:** Estados monitoráveis: `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`.
- **Rastreabilidade:** No caso de falha, o sistema indica exatamente qual parâmetro causou o erro e o log técnico do script.

## 5. Protocolo de Comunicação API <-> Robô

### O que o Robô Recebe da API:
- `--output_dir`: Caminho local temporário para salvar os downloads.
- `--user / --password`: Credenciais dinâmicas do portal alvo.
- `--agente`: Lista de códigos ONS que o robô deve processar naquela rodada.

### O que o Robô Entrega para a API:
- Arquivos (PDF/XML) na pasta de saída.
- Saída de console padronizada para monitoramento.

## 6. Riscos e Dificuldades Mapeadas
1. **Mudanças nos Portais (UI):** Selenium depende da interface dos sites. Dificuldade: Manutenção periódica dos seletores.
2. **Concorrência:** Rodar muitos robôs pesados ao mesmo tempo pode estourar a memória RAM da instância. *Mitigação: Fila de execução (Celery).*
3. **Captchas:** Alguns portais podem exigir intervenção ou serviços de bypass.
4. **Validação de XML:** Dependência da integridade dos arquivos baixados para extração correta dos metadados.

## 7. Estimativa de Esforço (Baseline Para 4 Bases)
- **Setup Infra AWS & CI/CD:** 6h
- **Adaptação dos Scripts Core:** 8h
- **Implementação do Orquestrador & S3:** 12h
- **Testes de Integração & Validação:** 10h
- **Total Estimado:** **36h - 44h**

---
Este plano garante um sistema profissional, auditável e, acesso fácil para a gestão acompanhar os resultados.
