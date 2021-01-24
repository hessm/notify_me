import asyncio
import copy
import json
import logging
from typing import Optional, Union

import discord
from discord.ext import commands, tasks

from notify_me.topics import pccg


log = logging.getLogger(__name__)


def new_bot(*args):
    bot = commands.Bot(
        command_prefix="!",
        intents=discord.Intents(messages=True, members=True, guilds=True),
    )
    bot.add_cog(NotificationCog(bot, *args))
    return bot


class NotificationCog(commands.Cog):
    """
    Intents
    - Messages: Required to send messages to users when their subscription triggers
    - Members: Required to lookup users, since we store users as an ID we require this to message them
    - Guilds: Required entirely to get the default help message to work, otherwise unnecessary

    Listeners
    - on_ready(): Called the first time the bot is ready. Should only be called once.
    - on_disconnect(): Called every time the bot disconnects from discord. Calls should match on_resumed unless we're currently disconnected
    - on_resumed(): Called every time the bot re-connects to discord.

    - not used on_connected(), This was once added as I thought it'd be used but it was never called by the bot. Either on ready or on resumed was called instread

    Commands
    am_i_subscribed sends you a message telling you if you're subscribed or not
    current_status  Message privately all current 3080s with their stock status...
    debug           Send yourself the internal state of the bot for debuging pu...
    send_update     send a notification to all subscribers
    subscribe       subscribe to notifications on pccg 3080 stock changes
    test            send a test notification to yourself
    unsubscribe     unsubscribe to notifications on pccg 3080 stock changes
    help            Shows this message

    Type !help command for more info on a command.
    You can also type !help category for more info on a category.

    """

    def __init__(self, bot, storage, suppress_notifications):
        """
        topics will be a dict that looks like...
        {
          "name": {"type": "pccg", "last_state": {}, "subscribers": [], "topic_specific_key": "topic_specific_value",
          for example pccg will look like
          "pccg_3080": {"type": "pccg", "last_state": {...}, "subscribers": [], "url": "http://3080url"}
        }
        """
        self.suppress_notifications = suppress_notifications
        self.admins = None
        self.topics = None
        self.bot = bot
        self.storage = storage
        self.query_running = False
        self.connected = False
        self.metrics = {"disconnected": 0, "resumed": 0, "ready": 0}

    def save(self):
        self.storage.save({"topics": self.topics, "admins": self.admins})

    def load(self):
        config = self.storage.load()
        self.topics = config["topics"]
        self.admins = config["admins"]

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        try:
            # Is there a better way of doing this?
            raise error
        except discord.ext.commands.errors.MissingRequiredArgument as e:
            log.info(
                "User %s did not provide all required arguments to command %s",
                ctx.author,
                ctx.command,
            )
            await self.send(
                ctx.author,
                f"{ctx.command}: {e}. Use !help {ctx.command} for more information",
            )

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Bot ready. starting poll for subscriptions")

        self.connected = True

        self.load()
        for name, config in self.topics.items():
            topic_type = config["type"]
            if not hasattr(globals()[topic_type], "run"):
                raise ValueError(
                    f"Topic {name} has type {topic_type} that does not support the run() method"
                )

            if not hasattr(globals()[topic_type], "current_state"):
                raise ValueError(
                    f"Topic {name} has type {topic_type} that does not support the current_state() method"
                )

        # Despite me saying on_ready shouldn't be called twice I swear it was one time. Guard this so we don't run two at once by accident
        if not self.query_running:
            self.poll_for_changes.start()

        self.metrics["ready"] += 1

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
        log.info(f"sending test notification to {ctx.author} with id {ctx.author.id}")
        await self.send(ctx.author, "This is a test notification")

    @commands.command(
        brief="Send yourself the internal state of the bot for debuging purposes"
    )
    async def debug(self, ctx):
        log.info("sending debug message to %s", ctx.author)
        internal_state = copy.deepcopy(self.topics)
        internal_state["connected"] = self.connected
        internal_state["query_running"] = self.query_running
        internal_state["metrics"] = self.metrics
        await self.send(ctx.author, json.dumps(internal_state, indent=2))

    @commands.command(brief="send a notification to all subscribers")
    async def send_update(self, ctx, message: str):
        log.info("%s wants to say %s", ctx.author, message)

        if ctx.author.id != 207076915935313920:
            await self.send(
                ctx.author,
                f"I can't let you do that {ctx.author}. You're not 207076915935313920",
            )
            return

        all_subscribers = set()
        for config in self.topics.values():
            for subscriber in config["subscribers"]:
                all_subscribers.add(subscriber)

        for subscriber_id in all_subscribers:
            user = await self.bot.get_user(subscriber_id)
            await self.send(user, message)

    @commands.command(brief="subscribe to notifications on the given topic")
    async def subscribe(self, ctx, topic: str):
        log.info(f"received subscribe notification from {ctx.author} {ctx.author.id}")

        if topic not in self.topics:
            await self.send(
                ctx.author,
                f"Topic {topic} does not exist. Available topics are {self.topics.keys()}",
            )
            return

        if ctx.author.id in self.topics[topic]["subscribers"]:
            await self.send(
                ctx.author,
                "you were already subscribed! and you're still subscribed now",
            )
            return

        self.topics[topic]["subscribers"].append(ctx.author.id)
        self.save()
        await self.send(
            ctx.author,
            f"You're subscribed to {topic} stock notifications, I'll let you know here if anything changes.",
        )

    @commands.command(brief="sends you a message telling you what you're subscribed to")
    async def what_am_i_subscribed_to(self, ctx):
        log.info("received subscribe notification from %s", ctx.author)

        subscribed_topics = []
        for name, config in self.topics.items():
            if ctx.author.id in config["subscribers"]:
                subscribed_topics.append(name)

        if len(subscribed_topics) > 0:
            topic_string = ", ".join(subscribed_topics)
            await self.send(ctx.author, f"You are subscribed to topics {topic_string}")

        else:
            await self.send(
                ctx.author,
                f"You are not subscribed to anything! use !subscribe <topic> to subscribe, options currently are {self.topics.keys()}",
            )

    @commands.command(brief="unsubscribe to notifications on the given topic")
    async def unsubscribe(self, ctx, topic: str):
        log.info(f"received unsubscribe notification from {ctx.author}")

        if topic not in self.topics:
            await self.send(
                ctx.author,
                f"Topic {topic} does not exist. Available topics are {self.topics.keys()}",
            )
            return

        if ctx.author.id not in self.topics[topic]["subscribers"]:
            await self.send(
                ctx.author,
                f"You are not subscribed to {topic}. I cannot unsubscribe you =/",
            )
            return

        self.topics[topic]["subscribers"] = [
            subscriber
            for subscriber in self.topics[topic]["subscribers"]
            if subscriber != ctx.author.id
        ]
        self.save()
        await self.send(
            ctx.author, f"You've successfully unsubscribed from {topic} notifications"
        )

    @commands.command(brief="Message privately the current state of a given topic")
    async def current_status(self, ctx, topic: str):
        log.info("%s requested current status", ctx.author)

        if topic not in self.topics:
            await self.send(
                ctx.author,
                f"Topic {topic} does not exist. Available topics are {self.topics.keys()}",
            )
            return

        config = self.topics[topic]
        topic_type = config["type"]

        current_state_method = getattr(globals()[topic_type], "current_state")
        message = current_state_method(config)

        await self.send(ctx.author, message)

    @commands.command(brief="What is my userid?")
    async def user_id(self, ctx):
        log.info("Giving %s their user id of %s", ctx.author, ctx.author.id)

        await self.send(
            ctx.author,
            f"Your username is {ctx.author} and your user id is {ctx.author.id}",
        )

    @commands.command(brief="Who's user id is this?")
    async def id_lookup(self, ctx, user_id: int):
        user = self.bot.get_user(user_id)

        if user is None:
            await self.send(
                ctx.author, f"Lookup failed for user id {user_id}, is that ID correct?"
            )
            return

        await self.send(ctx.author, f"User {user_id} is {user}")

    @tasks.loop(minutes=1, reconnect=True)
    async def poll_for_changes(self):
        if self.query_running:
            log.warn("Loop already running, refusing to run again")
            return

        self.query_running = True

        try:
            # We check for the existence of these in on_ready to fail early. Safe to just assume they exist here.
            for name in self.topics:
                topic_type = self.topics[name]["type"]
                run = getattr(globals()[topic_type], "run")
                message, new_state = await run(name, self.topics[name])

                if message:
                    log.info(
                        "About to try notify the following subscribers %s",
                        self.topics[name]["subscribers"],
                    )

                    for subscriber_id in self.topics[name]["subscribers"]:
                        if self.suppress_notifications:
                            log.info("Suppressing notifications")
                            continue

                        user = self.bot.get_user(subscriber_id)

                        # User IDs changed one time. I think I fucked them up somehow but they *might* have changed on discords end.
                        # For posterity I have recorded them here.
                        # What I had         Actual ID          User Tag
                        # 164645063840759800 164645063840759810 Mak#4811
                        # 146919847773732860 146919847773732864 Althalus#8960

                        if user is None:
                            self.notify_admins(
                                f"Failed to lookup user id {subscriber_id}. Not sending message to them. Message: {message}"
                            )
                            log.error(
                                "Failed to lookup user id %s. Continuing with other users.",
                                subscriber_id,
                            )
                            continue

                        await self.send(user, message)

                    self.topics[name]["last_state"] = new_state
                    self.save()

        except Exception as e:
            log.exception(
                "Failed to send one or more notifications. Refusing to save state, may send duplicate notifications in future"
            )
            self.query_running = False
            return

        self.query_running = False
        log.info("Finished update")

    async def notify_does_topic_exist(self, author, topic: str):
        if topic not in self.topics:
            self.send(
                author,
                f"Topic {topic} does not exist. Available topics are {self.topics.keys()}",
            )
            return False
        return True

    def find_user(name: str, discriminator: str) -> Optional[discord.abc.User]:
        return discord.utils.find(
            lambda u: u.name == name and u.discriminator == discriminator
        )

    async def notify_admins(self, message: str):
        log.info("Notifying admins about: %s", message)
        # What happens if we can't notify admins?
        for admin_id in self.topics["Admins"]:
            admin = self.bot.get_user(admin_id)
            if not admin:
                log.error(
                    "Cannot lookup admin while trying to notify of an error. This is bad. Admin id was %s",
                    admin_id,
                )
                continue

            self.send(admin, message)

    async def send(self, messageable: discord.abc.Messageable, message: str):
        log.info("Sending to %s message of length %s", messageable, len(message))

        offset = 0
        # Chunk each message into < 2000 sized sends to avoid discord max message size limits.
        # Each chunk should end with a new line to avoid splitting a line into multiple messages (would look bad)
        while offset < len(message):
            chunk = message[offset : offset + 2000]
            reversed_chunk = chunk[::-1]
            length = reversed_chunk.find("\n")
            chunk = chunk[: 2000 - length]
            offset += 2000 - length
            sent_message = await messageable.send(chunk)
            await sent_message.edit(suppress=True)
