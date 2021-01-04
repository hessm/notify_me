import os
import sys
import json

from notify_me.bot import NewBot
from dotenv import load_dotenv

import logging
log = logging.getLogger(__name__)

def setup_logging():
  handler = logging.StreamHandler(sys.stdout)
  formatter = logging.Formatter(
    '%(asctime)s %(name)s [%(levelname)s] %(message)s')
  handler.setFormatter(formatter)
  
  logging.getLogger().addHandler(handler)
  logging.getLogger().setLevel(logging.INFO)
  

# Click
# data local / s3
def main():
  setup_logging()
  log.info("Notify me starting")

  load_dotenv()

  discord_token = os.getenv('DISCORD_TOKEN')

  # keys need to match method params in storage.py
  aws_config = {
    "aws_token_id": os.getenv('AWS_TOKEN_ID'),
    "aws_token": os.getenv('AWS_TOKEN'),
    "s3_bucket_name": os.getenv('S3_BUCKET'),
    "s3_state_file_path": os.getenv('S3_STATE_FILE_PATH')
    }

  bot = NewBot(**aws_config)
  
  log.info("Bot starting")
  bot.run(discord_token)


if __name__ == "__main__":
  main()