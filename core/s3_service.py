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

        endpoint_url = "http://localhost:4566" if os.getenv("USE_LOCALSTACK", "true").lower() == "true" else None
        
        req_args = {
            "region_name": self.region,
            "endpoint_url": endpoint_url,
            "aws_access_key_id": "test",
            "aws_secret_access_key": "test"
        }
        self.s3_client = boto3.client('s3', **req_args)

    def upload_file(self, local_path, s3_key):
        """
        Faz o upload de um arquivo para o S3 seguindo a exata estrutura gerada pelo Robô.
        """
        try:
            buck = "datalake-raw" if self.bucket_name == "" else self.bucket_name
            self.s3_client.upload_file(local_path, buck, s3_key)
            return f"s3://{buck}/{s3_key}"
        except Exception as e:
            print(f"Erro ao fazer upload para o S3: {e}")
            return None

s3_service = S3Service()
