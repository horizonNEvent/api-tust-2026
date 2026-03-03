import boto3
import os
from dotenv import load_dotenv

load_dotenv()

def test_s3():
    print(f"Testing AWS_ACCESS_KEY_ID: {os.getenv('AWS_ACCESS_KEY_ID')}")
    print(f"Testing AWS_REGION: {os.getenv('AWS_REGION')}")
    print(f"Testing S3_BUCKET_NAME: {os.getenv('S3_BUCKET_NAME')}")
    
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION")
        )
        response = s3.list_buckets()
        print("Successfully connected! Buckets found:")
        for bucket in response['Buckets']:
            print(f" - {bucket['Name']}")
            
        # Try to put a small test file
        s3.put_object(Bucket=os.getenv("S3_BUCKET_NAME"), Key="test_connection.txt", Body="Connection Test")
        print(f"Successfully uploaded test_connection.txt to {os.getenv('S3_BUCKET_NAME')}")
        
    except Exception as e:
        print(f"Failed to connect or upload: {e}")

if __name__ == "__main__":
    test_s3()
