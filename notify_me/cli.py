import os
import sys
import json

import click

from notify_me.bot import new_bot
from notify_me.storage import StorageType, S3Storage, LocalStorage, storage_default
from dotenv import load_dotenv

import logging
log = logging.getLogger(__name__)

def setup_logging(level):
  handler = logging.StreamHandler(sys.stdout)
  formatter = logging.Formatter(
    '%(asctime)s %(name)s [%(levelname)s] %(message)s')
  handler.setFormatter(formatter)
  
  logging.getLogger().addHandler(handler)
  logging.getLogger().setLevel(level.upper())

@click.command()  
@click.option("--storage-type", type=click.Choice(list(map(lambda x: x.name, StorageType)), case_sensitive=True),  default=storage_default, help="where to load and save our config from and to")
@click.option("--log-level", type=click.Choice(['debug', 'info', 'error'], case_sensitive=False), default="info", help="what log level do we log at?")
@click.option("--suppress-notifications", is_flag=True)
def cli(storage_type, log_level, suppress_notifications):  
  setup_logging(log_level)
  log.info("Notify me starting")

  load_dotenv()

  discord_token = os.getenv('DISCORD_TOKEN')

  # keys need to match method params in bot.py and storage.py
  if StorageType[storage_type] == StorageType.local:
    storage = LocalStorage(os.getenv("LOCAL_STATE_FILE_PATH"))
  elif StorageType[storage_type] == StorageType.s3:
    s3_config = {
      "aws_token_id": os.getenv('AWS_TOKEN_ID'),
      "aws_token": os.getenv('AWS_TOKEN'),
      "s3_bucket_name": os.getenv('S3_BUCKET'),
      "state_file_path": os.getenv('S3_STATE_FILE_PATH')
    }
    storage = S3Storage(**s3_config)
  else:
    log.error(f"Storage type {storage_type} does not exist. Exiting")
    sys.exit(1)

  bot = new_bot(storage, suppress_notifications)
  
  log.info("Bot starting")
  bot.run(discord_token)

def get_string(l):
  return f"this is a test {l}"

if __name__ == "__main__":
  cli()