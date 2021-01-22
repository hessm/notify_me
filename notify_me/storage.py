import boto3
from dotenv import load_dotenv
import os
import json
from enum import Enum
 
import logging
log = logging.getLogger(__name__)

class StorageType(Enum):
  local = 0
  s3 = 1

storage_default = StorageType.s3.name


class LocalStorage():
  def __init__(self, state_file_path):
    self.state_file_path = f"./{state_file_path}"

  def load(self) -> str:
    with open(self.state_file_path, "r") as f:
      return json.load(f)

  def save(self, state):
    with open(self.state_file_path, "w") as f:
      json.dump(state, f, indent=2)

class S3Storage():
  def __init__(self, aws_token_id, aws_token, s3_bucket_name, state_file_path):
    self.s3_bucket_name = s3_bucket_name
    self.state_file_path = state_file_path

    self.s3 = boto3.resource('s3', aws_access_key_id=aws_token_id, aws_secret_access_key=aws_token)
    self.s3_object = self.s3.Object(s3_bucket_name, state_file_path)

  def load(self):
    log.info("Loading s3 state")
    return json.loads(self.s3_object.get()["Body"].read().decode('utf-8'))

  def save(self, state):
    log.info("saving state to s3")
    self.s3_object.put(Body=(bytes(json.dumps(state).encode('UTF-8'))))

if __name__ == "__main__":
  load_dotenv()

  aws_token_id = os.getenv('AWS_TOKEN_ID')
  aws_token = os.getenv('AWS_TOKEN')
  s3_bucket_name = os.getenv('S3_BUCKET')
  state_file_path = os.getenv('STATE_FILE_PATH')
  kwargs = {"aws_token_id": aws_token_id, "aws_token": aws_token, "s3_bucket_name": s3_bucket_name, "state_file_path": state_file_path}
  storage = S3Storage(**kwargs)
  print(storage.load())
  # storage = S3Storage(aws_token_id, aws_token, s3_bucket_name, state_file_path)
  
  # This will override prod data if you set it incorrectly
  # data = storage.load()
  # data["last_state"]["TEST_FILE"]["link"] = "Hi, I'm a link"
  # storage.save(data)
