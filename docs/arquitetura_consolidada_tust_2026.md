# Documentação Técnica: Arquitetura Consolidada TUST 2026

## 1. Visão Geral
O projeto **TUST 2026** foi redesenhado para uma arquitetura de microserviços orientada a eventos, focada em alta disponibilidade e escalabilidade automática (KEDA). Toda a inteligência de extração foi consolidada em uma **Imagem Única (All-in-One)** para facilitar a manutenção e o deploy.

---

## 2. Componentes e Funções

### 🚀 API (FastAPI)
*   **Função:** Cérebro e Triador.
*   **Papel:** Recebe as solicitações de execução (via Painel Admin ou Scheduler), consulta as configurações no banco de dados e despacha ordens de serviço.
*   **Ação:** Ela NÃO executa o robô. Ela apenas cria um "envelope" (JSON) e o posta na fila SQS. Isso permite que a API responda instantaneamente, sem travar enquanto o robô trabalha.

### 📨 AWS SQS (A Fila de Tarefas)
*   **Função:** Mensageria e Buffer.
*   **Fila Principal:** `TUST-Inbound-Queue`.
*   **Papel:** Funciona como um acumulador de tarefas. Se você disparar 100 robôs ao mesmo tempo, o SQS segura todas essas ordens de forma segura.
*   **Importância:** Garante que nenhuma tarefa se perca. Se um Worker cair, a mensagem volta para a fila após um tempo (Visibility Timeout) para ser processada por outro.

### 🤖 Worker Service (SQS Worker)
*   **Função:** O Operário.
*   **Papel:** Fica em loop (Long Polling) ouvindo a fila SQS. Ao capturar uma mensagem, ele identifica qual script de robô deve rodar, prepara o ambiente localmente e inicia a extração.
*   **Escalabilidade (KEDA):** Na produção, o KEDA monitora o tamanho da fila SQS. Se a fila crescer, o KEDA sobe automaticamente dezenas de instâncias deste Worker para limpar a fila rapidamente.

### 🛑 AWS DynamoDB (Tabela de Idempotência)
*   **Função:** Controle Duplicidade e Auditoria.
*   **Tabela:** `TUST-Idempotency`.
*   **Papel:** Antes de rodar qualquer robô, o Worker gera uma chave única (Ex: `TUST#AE#ASSU#3748#202603`). Ele pergunta ao DynamoDB: "Isso já foi feito?".
*   **Importância:** Proteção financeira e operacional. Evita que o robô baixe a mesma fatura duas vezes caso alguém clique repetidamente no botão "Play" ou ocorra um reprocessamento de fila.

### 🪣 AWS S3 (Bucket de Produção)
*   **Função:** Data Lake (Armazenamento Final).
*   **Bucket:** `pollvo.tust` (ou conforme configurado).
*   **Papel:** Todos os arquivos baixados (XML/PDF) são imediatamente enviados para o S3 em uma estrutura hierárquica organizada por robô e agente. 
*   **Pós-Upload:** Após o sucesso do upload, o Worker limpa o disco local do container, mantendo a infraestrutura leve e sem arquivos temporários acumulados.

---

## 3. O Fluxo de Execução (Passo a Passo)

1.  **Trigger:** Usuário clica em "🚀 Run" no Painel Admin.
2.  **Dispatch:** API gera UUID único e posta o JSON na fila `TUST-Inbound-Queue`.
3.  **Scale:** KEDA percebe a mensagem e sobe um container do **Worker**.
4.  **Check:** Worker lê a mensagem e consulta **Idempotência no DynamoDB**.
5.  **Execution (Python):** Se liberado, o Worker executa o Script Specialist (ex: `tropicalia.py`) dentro do ambiente Docker que já possui Chromium/OCR instalados.
6.  **Storage:** O robô salva o arquivo na pasta `/downloads`.
7.  **Upload:** O Worker detecta o arquivo, faz o **Upload para S3** e registra a conclusão no DynamoDB.
8.  **Cleanup:** O arquivo local é deletado e a mensagem é removida do SQS.

---

## 4. Requisitos para Produção (Checklist de Infra)

Para migrar do LocalStack (testes) para a AWS Real, o time de Infraestrutura precisará:

1.  **SQS:** Criar a fila `TUST-Inbound-Queue` e sua respectiva `DLQ` (Dead Letter Queue).
2.  **DynamoDB:** Criar a tabela `TUST-Idempotency` com a Partition Key `IdempotencyKey` (String).
3.  **S3:** Garantir que o bucket `pollvo.tust` exista.
4.  **Variáveis de Ambiente (.env):**
    *   `USE_LOCALSTACK=false`
    *   `SQS_QUEUE_URL=[URL_REAL_DA_AWS]`
    *   `DYNAMO_TABLE=TUST-Idempotency`
    *   `S3_BUCKET_NAME=pollvo.tust`
5.  **Permissões (IAM):** O usuário/role que rodar o Kubernetes precisa de permissão de `Read/Write` nos 3 serviços acima.

---

## 5. Estrutura de Imagem (Dockerfile Consolidado)
*   **Base:** `mcr.microsoft.com/playwright:v1.45.0-jammy`
*   **Incluso:** Python 3.12, Chromium (Playwright/Selenium), OpenCV, PaddleOCR, wkhtmltopdf.
*   **Vantagem:** Uma única pipeline de CI/CD para todo o projeto.
