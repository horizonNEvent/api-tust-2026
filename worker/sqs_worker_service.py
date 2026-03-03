import os
import boto3
import json
import time
import subprocess
import signal
import sys
from botocore.exceptions import ClientError
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type

# Configurações AWS (Idealmente vindas do .env)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789/TUST-Inbound-Queue")
SQS_DLQ_URL = os.getenv("SQS_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123456789/TUST-DeadLetter-Queue")
DYNAMO_TABLE = os.getenv("DYNAMO_TABLE", "TUST-Idempotency")
DOWNLOADS_ROOT = os.getenv("DOWNLOADS_ROOT_PATH", "./downloads")
ROBOTS_ROOT = os.getenv("ROBOTS_ROOT_PATH", "./Robots")

# Inicializa clientes AWS
sqs_client = boto3.client('sqs', region_name=AWS_REGION)
dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)

class SQSWorkerService:
    def __init__(self):
        self.is_shutting_down = False
        signal.signal(signal.SIGINT, self.graceful_shutdown)
        signal.signal(signal.SIGTERM, self.graceful_shutdown)

    def graceful_shutdown(self, signum, frame):
        """
        Sinal de SIGTERM. Para de puxar novas mensagens e apenas termina a atual.
        O KEDA/Kubernetes percebe e mata o pod pacificamente.
        """
        print("\n\u26A0\uFE0F Sinal SIGTERM recebido do Kubernetes. Desligando o Worker de forma segura...")
        self.is_shutting_down = True

    def check_dynamo_idempotencia(self, chave_unica):
        """
        Idempotência (O Cérebro do KEDA e Escalabilidade).
        Retorna True se o arquivo já foi processado (Economia de custo de Robô).
        """
        try:
            response = dynamodb_client.get_item(
                TableName=DYNAMO_TABLE,
                Key={'IdempotencyKey': {'S': chave_unica}}
            )
            return 'Item' in response
        except ClientError as e:
            # Em caso de erro técnico de tabela, retorna False para tentar baixar de novo por precaução
            print(f"Erro ao consultar DynamoDB (Pode ser ambiente local sem AWS mockado): {e}")
            return False

    def mark_as_processed_dynamo(self, chave_unica):
        """Registra no DynamoDB que o robô já concluiu aquele Mês/Agente."""
        try:
            dynamodb_client.put_item(
                TableName=DYNAMO_TABLE,
                Item={
                    'IdempotencyKey': {'S': chave_unica},
                    'Timestamp': {'S': str(time.time())}
                }
            )
        except ClientError as e:
            print(f"Erro ao salvar no DynamoDB: {e}")

    def send_to_dlq(self, message):
        """Redireciona mensagem falha para a Dead Letter Queue para auditoria."""
        print("\u274C Enviando mensagem para a Dead Letter Queue (Fila Morta)...")
        try:
            sqs_client.send_message(
                QueueUrl=SQS_DLQ_URL,
                MessageBody=message['Body']
            )
        except Exception as e:
            print(f"Falha gravíssima ao enviar para DLQ: {e}")

    def start_polling(self):
        print("\uD83D\uDE80 KEDA Worker Iniciado. Aguardando mensagens do Controlador SQS...")
        while not self.is_shutting_down:
            try:
                # Long Polling: Espera até 20 segundos por uma mensagem, reduz requisições vazias.
                response = sqs_client.receive_message(
                    QueueUrl=SQS_QUEUE_URL,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=20,
                )
                
                messages = response.get('Messages', [])
                if not messages:
                    continue
                
                for message in messages:
                    self.process_message(message)
                    
            except Exception as e:
                print(f"Erro na Fila SQS: {e}")
                time.sleep(5)

    def process_message(self, message):
        """
        O fluxo principal do diagrama de arquitetura:
        1. Lê Msg 
        2. Checa DynamoDB
        3. Roda Robô
        4. S3 Data Lake (Feito pelo robô ou orquestrador posterior)
        """
        receipt_handle = message['ReceiptHandle']
        try:
            body = json.loads(message['Body'])
            robot_type = body.get('robot')
            base = body.get('base')
            agente = body.get('agente')
            competencia = body.get('competencia')
            
            # CHAVE DEFINITIVA DO DYNAMODB: Identificador único da transação
            chave_unica = f"TUST#{base}#{robot_type}#{agente}#{competencia}"

            print(f"\n[\u2192] Processando Ordem SQS: {chave_unica}")
            
            # --- 1. AVALIAÇÃO DE IDEMPOTÊNCIA PREVENTIVA (DYNAMO DB) ---
            if self.check_dynamo_idempotencia(chave_unica):
                print(f"\u23E9 ABORTANDO: Fatura já processada anteriormente segundo DynamoDB ({chave_unica}).")
                # Deleta a mensagem do SQS pois o trabalho já está feito e poupa a máquina (Custo $0).
                sqs_client.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
                return

            print(f"\uD83D\uDD04 Não processado. Iniciando Subprocesso do Robô {robot_type}.py...")
            
            # --- 2. EXECUÇÃO DO ROBÔ RESILIENTE (PYTHON) ---
            script_path = os.path.join(ROBOTS_ROOT, f"{robot_type}.py")
            if not os.path.exists(script_path):
                raise ValueError(f"Script de Robô não encontrado: {script_path}")

            output_dir = os.path.join(DOWNLOADS_ROOT, f"{chave_unica}")
            cmd = ["python", script_path, "--output_dir", output_dir, "--agente", agente, "--empresa", base]
            
            # Adiciona credenciais se existirem no payload
            username = body.get('username')
            password = body.get('password')
            if username:
                cmd.extend(["--user", username])
            if password:
                cmd.extend(["--password", password])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"\u274C Robô Falhou: {result.stderr}")
                raise Exception("Erro interno do Robô")

            print("\u2705 Robô finalizou o download local. Iniciando transferência para S3 Data Lake (Raw)...")

            # --- 3. EXTRACAO DE METADADOS E UPLOAD PARA S3 DATA LAKE ---
            from core.s3_service import s3_service
            from core.xml_utils import extract_xml_data
            
            s3_keys_uploaded = []
            if os.path.exists(output_dir):
                for root, _, files in os.walk(output_dir):
                    for file in files:
                        local_file_path = os.path.join(root, file)
                        
                        # Extrai metadados antes de subir
                        metadados = extract_xml_data(local_file_path)
                        
                        # Upload para S3 Event-Driven Path
                        # Formato: bucket/Transmissora/Base/Agente/NFe.xml
                        transmissora = metadados.get('transmissora', 'Desconhecida')
                        agent_name = metadados.get('agent_name', str(agente))
                        
                        s3_url = s3_service.upload_file(
                            local_path=local_file_path,
                            competence=competencia,
                            agent_name=agent_name,
                            transmissora_name=transmissora,
                            filename=file
                        )
                        if s3_url:
                            s3_keys_uploaded.append(s3_url)
                            # Limpeza Local
                            os.remove(local_file_path)

            print(f"\u2705 {len(s3_keys_uploaded)} Arquivos salvos na Raw/S3 com Sucesso!")

            # --- 4. MARCAR COMO LIDO NO DYNAMODB ---
            self.mark_as_processed_dynamo(chave_unica)

            # --- 4. EXCLUIR DA FILA PRINCIPAL ---
            sqs_client.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
            print("\u2705 Mensagem processada e removida do SQS Worker Kubernetes.")

        except Exception as e:
            print(f"Erro no processamento da Mensagem: {e}")
            self.send_to_dlq(message)
            # Ao ir para a DLQ, também a deletamos da fila principal para não ficar em Loop Infinito
            try:
                sqs_client.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt_handle)
            except Exception:
                pass

if __name__ == "__main__":
    # Quando em AWS real, não falhará por causa das env vars falsas. 
    # Para testes locais offline usando docker-compose ou localstack, descomente a chamada de boto3 e configure localstack.
    worker = SQSWorkerService()
    # worker.start_polling() # <-- Comentado temporariamente só para não tentar conectar na AWS enquanto escrevemos o código.
    print("""
    \u2705 WORKER PRONTO (Apenas Mock Estrutural).
    A arquitetura SQS + DynamoDB Idempotency + KEDA Sigterm está configurada!
    Para rodar online, garanta as credenciais de AWS.
    """)
