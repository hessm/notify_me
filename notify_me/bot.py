from discord.ext import commands, tasks
import discord
import json
import asyncio
import copy

from notify_me import pccg
from notify_me.storage import S3Storage

from typing import Union

import logging
log = logging.getLogger(__name__)

def NewBot(**kwargs):
  """
  Intents
  - Messages: Required to send messages to users when their subscription triggers
  - Members: Required to lookup users, since we store users as an ID we require this to message them
  - Guilds: Required entirely to get the default help message to work, otherwise unnecessary
  """
  bot = commands.Bot(command_prefix='!', intents=discord.Intents(messages=True, members=True, guilds=True))
  bot.add_cog(NotificationCog(bot, **kwargs))
  return bot

class NotificationCog(commands.Cog):
  def __init__(self, bot, **kwargs):
    self.metrics = {"connected": 0, "disconnected": 0, "resumed": 0, "ready": 0}
    self.state = None
    self.bot = bot
    self.storage = S3Storage(**kwargs)
    self.query_running = False
    self.connected = False
    #TODO: Account for being disconnected when we find state changes. Don't write state back to storage until notifications sent


  @commands.Cog.listener()
  async def on_ready(self):
    log.info("Bot ready. starting poll for subscriptions")
    
    self.connected = True

    self.state = self.storage.load()
    
    # on_ready can be called more than once, make sure we don't start the poll while it's already running
    if not self.query_running:
      self.poll_for_changes.start()

    self.metrics["ready"] += 1


  @commands.Cog.listener()
  async def on_connected(self):
    log.info("Bot connected again!")
    self.connected = True
    self.metrics["connected"] += 1


  @commands.Cog.listener()
  async def on_disconnect(self):
    log.info("Bot disconnected! Cancelling poll for subscriptions")
    self.connected = False
    self.metrics["disconnected"] += 1


  @commands.Cog.listener()
  async def on_resumed(self):
    log.info("Bot resumed")
    self.connected = True
    self.metrics["resumed"] += 1


  @commands.command(brief="send a test notification to yourself")
  async def test(self, ctx):
    log.info(f"sending test notification to {ctx.author}")
    await self.send(ctx.author, "This is a test notification")


  @commands.command(brief="Send yourself the internal state of the bot for debuging purposes")
  async def debug(self, ctx):
    log.info("sending debug message to %s", ctx.author)
    internal_state = copy.deepcopy(self.state)
    internal_state["connected"] = self.connected
    internal_state["query_running"] = self.query_running
    internal_state["metrics"] = self.metrics
    await self.send(ctx.author, json.dumps(internal_state, indent=2))
    

  @commands.command(brief="send a notification to all subscribers")
  async def send_update(self, ctx, message: str):
    log.info("%s wants to say %s", ctx.author, message)

    if ctx.author.id != "207076915935313920":
      await self.send(ctx.author, f"I can't let you do that {ctx.author}. You're not 207076915935313920")
      return

    for subscriber_id in self.state["subscribers"]:
      user = await self.bot.get_user(subscriber_id)
      await self.send(user, message)


  @commands.command(brief="subscribe to notifications on pccg 3080 stock changes")
  async def subscribe(self, ctx):
    log.info(f"received subscribe notification from {ctx.author} {ctx.author.id}")

    if ctx.author.id in self.state["subscribers"]:
      await self.send(ctx.author, "you were already subscribed! and you're still subscribed now")
      return

    self.state["subscribers"].append(ctx.author.id)
    self.storage.save(self.state)
    await self.send(ctx.author, "You're subscribed to pccg 3080 stock notifications, I'll let you know here if anything changes.")


  @commands.command(brief="sends you a message telling you if you're subscribed or not")
  async def am_i_subscribed(self, ctx):
    log.info(f"received subscribe notification from {ctx.author.id}")
    if ctx.author.id in self.state["subscribers"]:
      answer = "yes"
    else:
      answer = "no"
    await self.send(ctx.author, answer)

  
  @commands.command(brief="unsubscribe to notifications on pccg 3080 stock changes")
  async def unsubscribe(self, ctx):
    self.state["subscribers"] = [subscriber for subscriber in self.state["subscribers"] if subscriber != ctx.author.id]
    self.storage.save(self.state)
    await self.send(ctx.author, "You've successfully unsubscribed from pccg 3080 notifications")
    log.info(f"received unsubscribe notification from {ctx.author.id}")


  @commands.command(brief="Message privately all current 3080s with their stock status and price")
  async def current_status(self, ctx):
    log.info("%s requested current status", ctx.author)
    message = pccg.generate_current_status_message(self.state["last_state"])
    await self.send(ctx.author, message)


  @tasks.loop(minutes=1, reconnect=True)
  async def poll_for_changes(self):
    if self.query_running:
      log.warn("Loop already running, refusing to run again")
      return

    self.query_running = True

    try:
      page = await pccg.query("https://www.pccasegear.com/category/193_2126/graphics-cards/geforce-rtx-3080")
      new_state = pccg.parse(page)

    except Exception as e:
      log.exception("Failed to query and parse the PCCG url") 
      self.query_running = False
      return

    new, changes, removed = pccg.diff(self.state["last_state"], new_state)
    
    if not (new or changes or removed):
      log.info("No changes, update complete")
      self.query_running = False
      return

    message = pccg.generate_diff_message(new, changes, removed)
    log.info("Generated message %s", message)
    
    try:
      log.info("About to try notify the following subscribers %s", self.state["subscribers"])
      for subscriber_id in self.state["subscribers"]:
        user = self.bot.get_user(subscriber_id)
        await self.send(user, message)
        
    except Exception as e:
      log.exception("Failed to send one or more notifications. Refusing to save state, may send duplicate notifications in future")
      self.query_running = False
      return

    self.state["last_state"] = new_state
    self.storage.save(self.state)

    self.query_running = False
    log.info("Finished update")


  async def send(self, messageable: discord.abc.Messageable, message: str):
    log.info("Sending to %s message of length %s", messageable, len(message))

    offset = 0
    # Chunk each message into < 2000 sized sends to avoid discord max message size limits.
    # Each chunk should end with a new line to avoid splitting a line into multiple messages (would look bad)
    while offset < len(message):
      chunk = message[offset:offset+2000]
      reversed_chunk = chunk[::-1]
      length = reversed_chunk.find("\n")
      chunk = chunk[:2000 - length]
      offset += 2000 - length
      sent_message = await messageable.send(chunk)
      await sent_message.edit(suppress=True)