# 🚀 TUST Cloud Native - Guia de Testes (Homologação Local)

Este documento contém o passo a passo para reiniciar o ambiente e continuar os testes exatamente de onde paramos.

## 🛠️ 1. Preparação do Ambiente (Infra)

Antes de rodar os robôs, precisamos subir a "Nuvem Local":

1.  **Docker Desktop:** Verifique se ele está aberto e rodando.
2.  **Subir o LocalStack:** Em um terminal, navegue até a raiz do projeto e rode:
    ```powershell
    docker-compose up -d
    ```
3.  **Resetar/Criar as Filas e Tabelas:** Rode o script de inicialização para garantir que o SQS, DynamoDB e S3 existam:
    ```powershell
    python init_localstack.py
    ```

---

## ⚡ 2. Iniciando os Serviços (O Coração)

Você precisará de **dois terminais** rodando permanentemente:

### Terminal A - API TUST (O Cérebro)
Este terminal recebe os pedidos e joga na fila.
```powershell
# Certifique-se de estar com a venv ativa
python -m uvicorn api.main:app --port 8001
```

### Terminal B - KEDA Worker (O Músculo)
Este terminal é o "Pod" que fica vigiando a fila e rodando os robôs de fato.
```powershell
python worker/sqs_worker_service.py
```

---

## 🎯 3. Executando os Testes (O Gatilho)

Agora use um **terceiro terminal** para disparar as ordens. O script `test_fim_a_fim.py` foi atualizado com superpoderes:

*   **Testar um Robô específico (pelo ID do banco):**
    ```powershell
    python test_fim_a_fim.py --id 126    # Dispara apenas o ASSU (Base AE/Libra)
    python test_fim_a_fim.py --id 1      # Dispara apenas o CNT
    ```
*   **Testar todos os robôs de uma Base inteira:**
    ```powershell
    python test_fim_a_fim.py --base AE   # Dispara todos da América Energia
    python test_fim_a_fim.py --base DE   # Dispara todos da Diamante
    ```
*   **Testar por tipo de Robô:**
    ```powershell
    python test_fim_a_fim.py --robo ASSU
    ```
*   **Rodar a esteira completa (CUIDADO: Muitos logs!):**
    ```powershell
    python test_fim_a_fim.py
    ```

---

## 🧹 4. Utilidades Importantes

### Limpar Idempotência (Id das notas)
Se você rodou um teste e quer rodar **o mesmo teste de novo** sem que o sistema ignore por achar que "já foi feito", limpe o histórico:
```powershell
python limpar_testes.py
```

### Onde estão meus arquivos?
O sistema está configurado para:
1.  Fazer upload para o **S3 LocalStack** (Nuvem simulada).
2.  Salvar uma cópia para inspeção humana em: `D:\arquivos-s3-teste\downloads\TUST\...`
3.  A hierarquia é: `BASE > ROBÔ > AGENTE > Arquivos`.

---

**Bom descanso, Bruno! Amanhã seguimos com a conversão dos próximos robôs para este novo padrão.** 🚀✨
