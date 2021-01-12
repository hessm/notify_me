from lxml import html, etree

from typing import List, Dict, Optional, Tuple, Union
import aiohttp
from enum import Enum

import logging
log = logging.getLogger(__name__)

gpu_type = Dict[str, Union[str, int]]

class QueryError(Exception):
  pass

class Messages():
  discord_max_message_length = 2000
  def __init__(self):
    self.messages = [""]

  def add(self, chunk: str) -> None:
    if len(self.messages[-1]) + len(chunk) < Messages.discord_max_message_length:
      self.messages[-1] += chunk
    else:
      self.messages.append(chunk)

  def newline(self) -> None:
    self.add("\n")


async def query(url: str) -> Optional[str]:
  async with aiohttp.ClientSession() as session:
    async with session.get(url) as resp:
      status = resp.status
      page = await resp.text()

    log.info("query result %s length: %s", status, len(page))
  
  if status != 200:
    raise QueryError(f"Failed to query {url}. status was {status}")

  return page


def parse(page: str) -> Dict[str, gpu_type]:
  tree = html.fromstring(page)
  cards = tree.xpath('//ul[@class="media-list"]/li')
  state: Dict[str, gpu_type] = {}

  for card in cards:
    name = "".join(card.xpath('.//a/text()')).strip()
    link = card.xpath('.//a/@href')[0].strip()
    status = "".join(card.xpath('.//button/text()')).strip()

    try:
      # Price looks like "$100". [1:] drops the dollar sign so we can int it
      price = int(card.xpath('.//h3/text()')[0][1:])
    except Exception as e:
      log.exception("Price for card %s was not an int. Price was %s. Defaulting to -1", name, price)
      price = -1

    if not (status.lower() == "in stock" or status.lower() == "sold out"):
      log.error("Unknown status for card %s. Status found was %s", name, status)

    state[name] = {"name": name, "link": link, "status": status, "price": price}

    if len(state) == 0:
      raise Exception("No content parsed from pccg site, something is wrong")

  return state


def diff(old_state: Dict[str, gpu_type], new_state: Dict[str, gpu_type]) -> Tuple[List[gpu_type], List[Tuple[gpu_type, gpu_type]], List[gpu_type]]:
  new: List[gpu_type] = []
  changed: List[Tuple[gpu_type, gpu_type]] = []
  removed: List[gpu_type] = []

  # added, changed
  for name in new_state:
    if name not in old_state:
      new.append(new_state[name])
      continue

    if new_state[name]["status"] != old_state[name]["status"]:
      changed.append((new_state[name], old_state[name]))

  # removed
  for name in old_state:
    if name not in new_state:
      removed.append(old_state[name])

  return new, changed, removed


def generate_diff_messages(new: List[gpu_type], changed: List[Tuple[gpu_type, gpu_type]], removed: List[gpu_type]) -> List[str]:
  if not (len(changed) > 0 or len(new) > 0 or len(removed) > 0):
    raise ValueError("Cannot generate a message when there are no changes! Why was this called?!")
  
  messages = Messages()
  messages.add("PCCG 3080 stock updated!\n\n")
  
  if len(changed) > 0:
    for new_gpu, old_gpu in changed:
      messages.add(f"'{old_gpu['status']}' -> '{new_gpu['status']}' ${new_gpu['price']} {new_gpu['link']}\n")
    messages.newline()

  if len(new) > 0:
    for new_gpu in new:
      messages.add(f"Newly listed: '{new_gpu['status']}' ${new_gpu['price']} {new_gpu['link']}\n")
    messages.newline()
  
  if len(removed) > 0:
    for old_gpu in removed:
      messages.add(f"No longer listed: '{old_gpu['status']}' {old_gpu['name']}\n")

  return messages.messages


def generate_current_status_messages(state: Dict[str, gpu_type]) -> List[str]:
  messages = Messages()
  # Sort by price then status to get a status, price sorted ordered dict
  for gpu in sorted(sorted(state.values(), key=lambda x: x['price']), key=lambda x: x['status']):
    messages.add(f"'{gpu['status']}' ${gpu['price']} {gpu['link']}\n")

  return messages.messages


  
if __name__ == "__main__":
  import sys
  handler = logging.StreamHandler(sys.stdout)
  formatter = logging.Formatter(
    '%(asctime)s %(name)s [%(levelname)s] %(message)s')
  handler.setFormatter(formatter)
  
  logging.getLogger().addHandler(handler)
  logging.getLogger().setLevel(logging.INFO)

  from asgiref.sync import async_to_sync

  def test_query():
    page = async_to_sync(query)("https://www.pccasegear.com/category/193_2126/graphics-cards/geforce-rtx-3080")

  def test_generate_message():
    new: List[gpu_type] = [{"name": "fancy 3080 name", "link": "fancy 3080 link", "status": "out of stock"},{"name": "old crappy 3080 name", "link": "old crappy 3080 link", "status": "out of stock"}]
    changed: List[Tuple[gpu_type, gpu_type]] = [({"name": "standard 3080 name", "link": "standard 3080 link", "status": "1 million dollars"}, {"name": "standard 3080 name", "link": "standard 3080 link", "status": "out of stock"})]
    removed: List[gpu_type] = [{"name": "old crappy 3080 name", "link": "old crappy 3080 link", "status": "out of stock"}]
    print(generate_diff_message(new, changed, removed))

    generate_message([], [], [])
  
  def test_parse_pccg():
    import json
    with open("test_data/3070_page.html", "r") as f:
      page = f.read()
    results = parse(page)
    print(json.dumps(results, indent=2))

  def test_generate_current_status_message():
    import json
    with open("test_data/3070_page.html", "r") as f:
      page = f.read()
    state = parse(page)
    print(generate_current_status_message(state))

  def test_messages_class():
    messages = Messages()
    # Message 1
    messages.add("!this is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character comment...")
    messages.add("!this is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character comment...")
    messages.add("!this is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character comment...")
    messages.add("this is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character comment...")
  
    # Message 2
    messages.add("this is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character commentthis is a 500 character comment...")
    
    print(len(messages.messages))
    for message in messages.messages:
      print(len(message))

  # test_parse_pccg()
  # test_generate_current_status_message()
  # test_messages_class()
  test_query()
