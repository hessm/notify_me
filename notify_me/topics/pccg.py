from lxml import html, etree

from typing import List, Dict, Optional, Tuple, Union, Any
import aiohttp
from enum import Enum

import logging
log = logging.getLogger(__name__)

gpu_type = Dict[str, Union[str, int]]

class QueryError(Exception):
  pass


async def run(name: str, config) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
  log.info(f"Running pccg check named {name} against url {config['url']}")
  page = await query(config["url"])
  new_state = parse(page)

  new, changes, removed = diff(config["last_state"], new_state)
  
  if not (new or changes or removed):
    log.info("No changes, update complete")
    return None, None

  message = generate_diff_message(new, changes, removed)
  log.info("Generated message %s", message)
  return message, new_state
    

async def query(url: str) -> str:
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


def generate_diff_message(new: List[gpu_type], changed: List[Tuple[gpu_type, gpu_type]], removed: List[gpu_type]) -> str:
  if not (len(changed) > 0 or len(new) > 0 or len(removed) > 0):
    raise ValueError("Cannot generate a message when there are no changes! Why was this called?!")
  
  message = "PCCG 3080 stock updated!\n\n"
  
  if len(changed) > 0:
    for new_gpu, old_gpu in changed:
      message += f"'{old_gpu['status']}' -> '{new_gpu['status']}' ${new_gpu['price']} {new_gpu['link']}\n"
    message += "\n"

  if len(new) > 0:
    for new_gpu in new:
      message += f"Newly listed: '{new_gpu['status']}' ${new_gpu['price']} {new_gpu['link']}\n"
    message += "\n"
  
  if len(removed) > 0:
    for old_gpu in removed:
      message += f"No longer listed: '{old_gpu['status']}' {old_gpu['name']}\n"

  return message


def current_state(config: Dict[str, Union[Any, Dict[str, gpu_type]]]) -> str:
  state: Dict[str, gpu_type] = config["last_state"]

  message = ""
  # Sort by price then status to get a status, price sorted ordered dict
  for gpu in sorted(sorted(state.values(), key=lambda x: x['price']), key=lambda x: x['status']):
    message += f"'{gpu['status']}' ${gpu['price']} {gpu['link']}\n"

  return message

  
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

  def test_bad_parse_pccg():
    page = "<html></html>"
    results = parse(page)
    print(results)

  def test_generate_current_status_message():
    import json
    with open("test_data/3070_page.html", "r") as f:
      page = f.read()
    state = parse(page)
    print(generate_current_status_message(state))

  # test_parse_pccg()
  test_bad_parse_pccg()
  # test_generate_current_status_message()
  # test_query()
