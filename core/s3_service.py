import boto3
import os
from dotenv import load_dotenv

load_dotenv(override=True)

class S3Service:
    def __init__(self):
        self.access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip().replace('"', '').replace("'", "")
        self.secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip().replace('"', '').replace("'", "")
        self.region = os.getenv("AWS_REGION", "us-east-1").strip().replace('"', '').replace("'", "")
        self.bucket_name = os.getenv("S3_BUCKET_NAME", "").strip().replace('"', '').replace("'", "")

        self.s3 = boto3.client(
            's3',
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region
        )

    def upload_file(self, local_path, competence, agent_name, transmissora_name, filename):
        """
        Faz o upload de um arquivo para o S3 seguindo a estrutura:
        [Competência] / [Agente] / [Pasta Transmissora] / [Arquivo]
        """
        s3_key = f"{competence}/{agent_name}/{transmissora_name}/{filename}"
        try:
            self.s3.upload_file(local_path, self.bucket_name, s3_key)
            return f"s3://{self.bucket_name}/{s3_key}"
        except Exception as e:
            print(f"Erro ao fazer upload para o S3: {e}")
            return None

s3_service = S3Service()
