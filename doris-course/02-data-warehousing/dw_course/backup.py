"""Course-owned object storage for a real repository BACKUP/RESTORE drill."""

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

from .sidecars import start_service

ENDPOINT = 'http://127.0.0.1:51910'
BUCKET = 'course-backups'
ACCESS_KEY = 'course_backup'
SECRET_KEY = 'course_backup_local_only'


def prepare_backup_storage(lab, *, start=False):
    start_service(lab, 'backup', start=start)
    client = boto3.client('s3', endpoint_url=ENDPOINT, region_name='us-east-1',
                          aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
                          config=Config(s3={'addressing_style': 'path'}))
    try:
        client.head_bucket(Bucket=BUCKET)
    except ClientError as error:
        if error.response['Error']['Code'] != '404':
            raise
        client.create_bucket(Bucket=BUCKET)
    return client
