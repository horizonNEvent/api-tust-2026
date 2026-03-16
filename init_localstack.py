import boto3
import time

endpoint = "http://localhost:4566"
req = {
    "region_name": "us-east-1",
    "endpoint_url": endpoint,
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test"
}

print("Inicializando nuvem local AWS (LocalStack)...")

# 1. Cria Filas SQS
sqs = boto3.client('sqs', **req)
filas = ['TUST-Inbound-Queue', 'TUST-DeadLetter-Queue']
for fila in filas:
    try:
        print(f"Criando Fila SQS: {fila}")
        sqs.create_queue(QueueName=fila)
    except Exception as e:
        print(f"Erro ao criar fila {fila}: {e}")

# 2. Cria Buckets S3
s3 = boto3.client('s3', **req)
from dotenv import load_dotenv
import os
load_dotenv()
target_bucket = os.getenv("S3_BUCKET_NAME", "pollvo.tust")

buckets = ['datalake-raw', target_bucket]
for b in set(buckets):
    try:
        print(f"Criando Bucket S3: {b}")
        s3.create_bucket(Bucket=b)
    except Exception as e:
        print(f"Erro ao criar bucket {b}: {e}")

# 3. Cria Tabela DynamoDB
dynamo = boto3.client('dynamodb', **req)
try:
    print("Criando Tabela DynamoDB: TUST-Idempotency")
    dynamo.create_table(
        TableName='TUST-Idempotency',
        KeySchema=[{'AttributeName': 'IdempotencyKey', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'IdempotencyKey', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST'
    )
except Exception as e:
    print(e)

print("✅ Infraestrutura base da 'GD_Compartilhada' criada instantaneamente via Mock LocalStack!")
