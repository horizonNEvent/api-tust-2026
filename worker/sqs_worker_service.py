import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
import json
import time
import subprocess
import signal
import argparse
from botocore.exceptions import ClientError
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type

from core.s3_service import s3_service
from core.xml_utils import extract_xml_data
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789/TUST-Inbound-Queue")
SQS_DLQ_URL = os.getenv("SQS_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123456789/TUST-DeadLetter-Queue")
DYNAMO_TABLE = os.getenv("DYNAMO_TABLE", "TUST-Idempotency")
DOWNLOADS_ROOT = os.getenv("DOWNLOADS_ROOT_PATH", "./downloads")
ROBOTS_ROOT = os.getenv("ROBOTS_ROOT_PATH", "./Robots")

# Definicoes Mocks do LocalStack
LOCALSTACK_URL = "http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000"
LOCALSTACK_INBOUND = f"{LOCALSTACK_URL}/TUST-Inbound-Queue"
LOCALSTACK_DLQ = f"{LOCALSTACK_URL}/TUST-DeadLetter-Queue"

# Inicializa clientes AWS (Apontando pro docker localstack em testes na sua máquina)
# Em produção AWS, essas envvars AWS vars já cuidam disso.
endpoint_url = "http://localhost:4566" if os.getenv("USE_LOCALSTACK", "true").lower() == "true" else None
req_args = {
    "region_name": AWS_REGION,
    "endpoint_url": endpoint_url,
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test"
}

sqs_client = boto3.client('sqs', **req_args)
dynamodb_client = boto3.client('dynamodb', **req_args)

class SQSWorkerService:
    def __init__(self, target_queue):
        self.is_shutting_down = False
        self.queue_url = target_queue
        
        # Conserta a URL da Fila se for LocalStack
        if endpoint_url:
            self.queue_url = LOCALSTACK_INBOUND
            global SQS_DLQ_URL
            SQS_DLQ_URL = LOCALSTACK_DLQ
            
        signal.signal(signal.SIGINT, self.graceful_shutdown)
        signal.signal(signal.SIGTERM, self.graceful_shutdown)

    def graceful_shutdown(self, signum, frame):
        """
        Sinal de SIGTERM. Para de puxar novas mensagens e apenas termina a atual.
        O KEDA/Kubernetes percebe e mata o pod pacificamente.
        """
        print("\n[AVISO] Sinal SIGTERM recebido do Kubernetes. Desligando o Worker de forma segura...")
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
        print("[ERRO] Enviando mensagem para a Dead Letter Queue (Fila Morta)...")
        try:
            sqs_client.send_message(
                QueueUrl=SQS_DLQ_URL,
                MessageBody=message['Body']
            )
        except Exception as e:
            print(f"Falha gravíssima ao enviar para DLQ: {e}")

    def start_polling(self):
        print("[INFO] KEDA Worker Iniciado. Aguardando mensagens do Controlador SQS...")
        while not self.is_shutting_down:
            try:
                # Long Polling: Espera até 20 segundos por uma mensagem, reduz requisições vazias.
                response = sqs_client.receive_message(
                    QueueUrl=self.queue_url,
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

            print(f"\n[[->]] Processando Ordem SQS: {chave_unica}")
            
            # --- 1. AVALIAÇÃO DE IDEMPOTÊNCIA PREVENTIVA (DYNAMO DB) ---
            if self.check_dynamo_idempotencia(chave_unica):
                print(f"[SKIP] ABORTANDO: Fatura já processada anteriormente segundo DynamoDB ({chave_unica}).")
                # Deleta a mensagem do SQS pois o trabalho já está feito e poupa a máquina (Custo $0).
                sqs_client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
                return

            print(f"[RUN] Não processado. Iniciando Subprocesso do Robô {robot_type}.py...")
            
            # --- 2. EXECUÇÃO DO ROBÔ RESILIENTE (PYTHON) ---
            script_path = os.path.join(ROBOTS_ROOT, f"{robot_type}.py")
            if not os.path.exists(script_path):
                raise ValueError(f"Script de Robô não encontrado: {script_path}")

            output_dir = os.path.join(DOWNLOADS_ROOT, f"{chave_unica}")
            
            # Limpeza preventiva: se houver lixo de uma tentativa anterior que falhou no upload, apaga tudo.
            if os.path.exists(output_dir):
                import shutil
                shutil.rmtree(output_dir)
            os.makedirs(output_dir, exist_ok=True) # Garantimos que a pasta base exista
            
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
                print(f"[ERRO] Robô Falhou: {result.stderr}")
                raise Exception("Erro interno do Robô")

            print("[OK] Robô finalizou o download local. Iniciando transferência para S3 Data Lake (Raw)...")

            # --- 3. EXTRACAO DE METADADOS E UPLOAD PARA S3 DATA LAKE ---
            s3_keys_uploaded = []
            if os.path.exists(output_dir):
                for root, _, files in os.walk(output_dir):
                    for file in files:
                        local_file_path = os.path.join(root, file)
                        
                        # Extrai metadados apenas de XML
                        metadados = {}
                        if file.lower().endswith('.xml'):
                            metadados = extract_xml_data(local_file_path)
                        
                        # Hierarquia Dinâmica do Robô: Calcula exatamente as subpastas que o robô escolheu criar 
                        # Ex: 'DE/3748/arquivo.xml' ou 'EQUATORIAL/SP01/arquivo.pdf'
                        relative_path = os.path.relpath(local_file_path, output_dir)
                        # Garante forward slashes para o S3
                        s3_rel_path = relative_path.replace('\\', '/')
                        
                        # Constrói a chave bruta final: TUST / [NOME_DO_ROBO] / [Estrutura do Robô]
                        s3_key = f"TUST/{str(robot_type).upper()}/{s3_rel_path}"
                        
                        s3_url = s3_service.upload_file(
                            local_path=local_file_path,
                            s3_key=s3_key
                        )
                        if s3_url:
                            s3_keys_uploaded.append(s3_url)
                            
                            # --- CÓPIA PARA PASTA DE HOMOLOGAÇÃO LOCAL (VISUALIZAÇÃO DO USUÁRIO) ---
                            import shutil
                            homolog_file_path = os.path.join(r"D:\arquivos-s3-teste\downloads\TUST", str(robot_type).upper(), relative_path)
                            os.makedirs(os.path.dirname(homolog_file_path), exist_ok=True)
                            shutil.copy2(local_file_path, homolog_file_path)
                            # -------------------------------------------------------------------------
                            
                            # Limpeza Local
                            os.remove(local_file_path)

            print(f"[OK] {len(s3_keys_uploaded)} Arquivos salvos na Raw/S3 com Sucesso!")

            # --- 4. MARCAR COMO LIDO NO DYNAMODB ---
            self.mark_as_processed_dynamo(chave_unica)

            # --- 4. EXCLUIR DA FILA PRINCIPAL ---
            sqs_client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
            print("[OK] Mensagem processada e removida do SQS Worker Kubernetes.")

        except Exception as e:
            print(f"Erro no processamento da Mensagem: {e}")
            self.send_to_dlq(message)
            # Ao ir para a DLQ, também a deletamos da fila principal para não ficar em Loop Infinito
            try:
                sqs_client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
            except Exception:
                pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Worker KEDA para TUST')
    parser.add_argument('--queue', type=str, default='TUST-Inbound-Queue', help='Nome da Fila SQS Alvo')
    args = parser.parse_args()

    worker = SQSWorkerService(target_queue=args.queue)
    print(f"""
    [OK] WORKER PRONTO E CONECTADO NO LOCALSTACK.
    ---------------------------------------------------
    🎯 TIPO DE MÁQUINA: OUVINDO FILA: {args.queue}
    ---------------------------------------------------
    Aguardando mensagens da Nuvem...
    """)
    worker.start_polling()
