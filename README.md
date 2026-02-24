# API TUST 2026 🤖📂

API especializada no orquestramento, agendamento e execução de robôs automatizados para coleta e processamento de dados diários.

## 🚀 Objetivo do Projeto
O sistema tem como finalidade centralizar a gestão de robôs (crawlers/scrapers), permitindo o agendamento de tarefas recorrentes e a integração direta com a **AWS**.

## 🛠️ Funcionalidades Principais (Iniciais)
- **Gerenciamento de Robôs**: Interface para chamar e executar diferentes automações.
- **Agendamento Inteligente**: Automação de downloads diários.
- **Integração AWS S3**: Envio automático dos documentos coletados pelos robôs para buckets no S3.
- **Escalabilidade**: Estrutura preparada para evolução e adição de novos robôs e serviços.

## 🏗️ Arquitetura
- **Cloud**: AWS (S3, Lambda/EC2/ECS para execução).
- **Dados**: Documentos processados e armazenados via S3.

---
*Este projeto está em fase inicial de desenvolvimento e evolução constante.*
