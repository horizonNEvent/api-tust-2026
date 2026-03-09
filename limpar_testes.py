import boto3
import os

endpoint_url = "http://localhost:4566" if os.getenv("USE_LOCALSTACK", "true").lower() == "true" else None
req_args = {
    "region_name": "us-east-1",
    "endpoint_url": endpoint_url,
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test"
}

dynamo = boto3.client('dynamodb', **req_args)
TABLE_NAME = "TUST-Idempotency"

def limpar_tabela():
    print("⏳ Escaneando a Tabela DynamoDB para apagar históricos...")
    try:
        response = dynamo.scan(TableName=TABLE_NAME)
        items = response.get('Items', [])
        
        if not items:
            print("✅ A tabela já está limpa. Nenhum registro de Idempotência achado.")
            return

        for item in items:
            chave = item['IdempotencyKey']['S']
            dynamo.delete_item(
                TableName=TABLE_NAME,
                Key={'IdempotencyKey': {'S': chave}}
            )
            print(f"🗑️ Deletado registro de Idempotência: {chave}")
            
        print(f"✅ Limpeza concluída! Foram apagados {len(items)} registros de execuções passadas.")
        print("🚀 Você já pode rodar 'python test_fim_a_fim.py' novamente e os robôs irão baixar tudo de novo!")
        
    except Exception as e:
        print(f"❌ Erro ao limpar a tabela: {e}")

if __name__ == "__main__":
    limpar_tabela()
