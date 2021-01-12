from discord.ext import commands, tasks
import discord

import asyncio

from notify_me import pccg
from notify_me.storage import S3Storage

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
    self.state = None
    self.bot = bot
    self.storage = S3Storage(**kwargs)
    self.query_running = False
    self.connected = False   
    #TODO: Account for being disconnected when we find state changes. Don't write state back to storage until notifications sent


  @commands.Cog.listener()
  async def on_ready(self):
    log.info("Bot ready. starting poll for subscriptions")
    self.state = self.storage.load()
    self.poll_for_changes.start()


  @commands.Cog.listener()
  async def on_connected(self):
    log.info("Bot connected again!")
    self.connected = True


  @commands.Cog.listener()
  async def on_disconnect(self):
    log.info("Bot disconnected! Cancelling poll for subscriptions")
    self.connected = False

  @commands.Cog.listener()
  async def on_resumed(self):
    log.info("Bot resumed")
    self.connected = True

  @commands.command(brief="send a test notification to yourself")
  async def test(self, ctx):
    log.info(f"sending test notification to {ctx.author}")
    await self.send_notification_by_user(ctx.author, "This is a test notification")


  @commands.command(brief="subscribe to notifications on pccg 3080 stock changes")
  async def subscribe(self, ctx):
    log.info(f"received subscribe notification from {ctx.author.id}")

    if ctx.author.id in self.state["subscribers"]:
      await self.send_notification_by_user(ctx.author, "you were already subscribed! and you're still subscribed now")
      return
    
    self.state["subscribers"].append(ctx.author.id)
    self.storage.save(self.state)
    await self.send_notification_by_user(ctx.author, "You're subscribed to pccg 3080 stock notifications, I'll let you know here if anything changes.")
    

  @commands.command(brief="sends you a message telling you if you're subscribed or not")
  async def am_i_subscribed(self, ctx):
    log.info(f"received subscribe notification from {ctx.author.id}")
    if ctx.author.id in self.state["subscribers"]:
      answer = "yes"
    else:
      answer = "no"
    await self.send_notification_by_user(ctx.author, answer)

  
  @commands.command(brief="unsubscribe to notifications on pccg 3080 stock changes")
  async def unsubscribe(self, ctx):
    self.state["subscribers"] = [subscriber for subscriber in self.state["subscribers"] if subscriber != ctx.author.id]
    self.storage.save(self.state)
    await self.send_notification_by_user(ctx.author, "You've successfully unsubscribed from pccg 3080 notifications")
    log.info(f"received unsubscribe notification from {ctx.author.id}")


  @commands.command(brief="Message privately all current 3080s with their stock status and price")
  async def current_status(self, ctx):
    log.info("%s requested current status", ctx.author)
    messages = pccg.generate_current_status_messages(self.state["last_state"])
    for message in messages:
      message = await ctx.author.send(message)
      await message.edit(suppress=True)


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

    messages = pccg.generate_diff_messages(new, changes, removed)
    log.info("Generated messages %s", messages)
    
    try:
      log.info("About to try notify the following subscribers %s", self.state["subscribers"])
      for subscriber_id in self.state["subscribers"]:
        for message in messages:
          await self.send_notification_by_id(int(subscriber_id), message)
        
    except Exception as e:
      log.exception("Failed to send one or more notifications. Refusing to save state, may send duplicate notifications in future")
      self.query_running = False
      return

    self.state["last_state"] = new_state
    if self.connected:
      self.storage.save(self.state)
    else:
      log.warn("Refusing to save state changes while discord client is disconnected")

    self.query_running = False
    log.info("Finished update")


  async def send_notification_by_id(self, user_id: int, content: str) -> discord.Message:
    log.info(f"looking up user {user_id}")
    user = self.bot.get_user(user_id)
    message = await self.send_notification_by_user(user, content)

    return message


  async def send_notification_by_user(self, user: discord.User, content: str) -> discord.Message:
    log.info(f"sending to user {user} message len {len(content)} {content[:50]}")
    message = await user.send(content, embed=None)
    await message.edit(suppress=True)