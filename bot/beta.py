# Standard library imports
import os
import re
import asyncio
from asyncio import Task, create_task, sleep
from typing import List
import queue
import argparse
import datetime
from datetime import datetime, timezone, timedelta
import logging
import subprocess
import websockets
import json
import time
import random
import base64

# Third-party imports
import aiohttp
import requests
import sqlite3
from translate import Translator
from googletrans import Translator, LANGUAGES
import twitchio
from twitchio.ext import commands, pubsub
import streamlink
import pyowm
import pytz

# Parse command-line arguments
parser = argparse.ArgumentParser(description="BotOfTheSpecter Chat Bot")
parser.add_argument("-channel", dest="target_channel", required=True, help="Target Twitch channel name")
parser.add_argument("-channelid", dest="channel_id", required=True, help="Twitch user ID")
parser.add_argument("-token", dest="channel_auth_token", required=True, help="Auth Token for authentication")
parser.add_argument("-refresh", dest="refresh_token", required=True, help="Refresh Token for authentication")
args = parser.parse_args()

# Twitch bot settings
CHANNEL_NAME = args.target_channel
CHANNEL_ID = args.channel_id
CHANNEL_AUTH = args.channel_auth_token
REFRESH_TOKEN = args.refresh_token
BOT_USERNAME = "botofthespecter"
VERSION = "4.0"
WEBHOOK_SECRET = ""  # CHANGE TO MAKE THIS WORK
CALLBACK_URL = ""  # CHANGE TO MAKE THIS WORK
OAUTH_TOKEN = ""  # CHANGE TO MAKE THIS WORK
CLIENT_ID = ""  # CHANGE TO MAKE THIS WORK
CLIENT_SECRET = ""  # CHANGE TO MAKE THIS WORK
TWITCH_API_AUTH = ""  # CHANGE TO MAKE THIS WORK
TWITCH_GQL = ""  # CHANGE TO MAKE THIS WORK
SHAZAM_API = ""  # CHANGE TO MAKE THIS WORK
WEATHER_API = ""  # CHANGE TO MAKE THIS WORK
TWITCH_API_CLIENT_ID = CLIENT_ID
builtin_commands = {"commands", "bot", "roadmap", "quote", "timer", "ping", "cheerleader", "schedule", "mybits", "lurk", "unlurk", "lurking", "lurklead", "clip", "subscription", "hug", "kiss", "uptime", "typo", "typos", "followage", "deaths"}
mod_commands = {"addcommand", "removecommand", "removetypos", "quoteadd", "edittypos", "deathadd", "deathremove", "so", "marker", "checkupdate"}
builtin_aliases = {"cmds", "back", "shoutout", "typocount", "edittypo", "removetypo", "death+", "death-", "mysub"}

# Logs
webroot = "/var/www/"
logs_directory = "logs"
bot_logs = os.path.join(logs_directory, "bot")
chat_logs = os.path.join(logs_directory, "chat")
twitch_logs = os.path.join(logs_directory, "twitch")
api_logs = os.path.join(logs_directory, "api")
chat_history_logs = os.path.join(logs_directory, "chat_history")

# Ensure directories exist
for directory in [logs_directory, bot_logs, chat_logs, twitch_logs, api_logs, chat_history_logs]:
    directory_path = os.path.join(webroot, directory)
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

# Create a function to setup individual loggers for clarity
def setup_logger(name, log_file, level=logging.INFO):
    handler = logging.FileHandler(log_file)    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger

# Function to get today's date in the required format
def get_today_date():
    return datetime.now().strftime("%d-%m-%Y")

# Setup bot logger
bot_log_file = os.path.join(webroot, bot_logs, f"{CHANNEL_NAME}.txt")
bot_logger = setup_logger('bot', bot_log_file)

# Setup chat logger
chat_log_file = os.path.join(webroot, chat_logs, f"{CHANNEL_NAME}.txt")
chat_logger = setup_logger('chat', chat_log_file)

# Setup twitch logger
twitch_log_file = os.path.join(webroot, twitch_logs, f"{CHANNEL_NAME}.txt")
twitch_logger = setup_logger('twitch', twitch_log_file)

# Setup API logger
api_log_file = os.path.join(webroot, api_logs, f"{CHANNEL_NAME}.txt")
api_logger = setup_logger("api", api_log_file)

# Setup chat history logger
chat_history_folder = os.path.join(webroot, chat_history_logs, CHANNEL_NAME)
if not os.path.exists(chat_history_folder):
    os.makedirs(chat_history_folder)
chat_history_log_file = os.path.join(chat_history_folder, f"{get_today_date()}.txt")
chat_history_logger = setup_logger('chat_history', chat_history_log_file)

# Initialize your client with the CHANNEL_AUTH token:
client = twitchio.Client(token=CHANNEL_AUTH)
pubsub_pool = pubsub.PubSubPool(client)

async def main():
    channel_id_int = int(CHANNEL_ID)
    pubsub_pool = pubsub.PubSubPool(client)
    await pubsub_pool.subscribe_to_channel(CHANNEL_AUTH, channel_id_int, [pubsub.PubSubBits, pubsub.PubSubSubscriptions, pubsub.PubSubChannelPoints])
    pubsub_pool.on_message(event_handler)
    await pubsub_pool.listen()

async def event_handler(message):
    if message.type == pubsub.PubSubBits:
        bot_logger.info(f"Bits: {message.data}")
    elif message.type == pubsub.PubSubSubscriptions:
        bot_logger.info(f"Subscription: {message.data}")
    elif message.type == pubsub.PubSubChannelPoints:
        bot_logger.info(f"Channel Points: {message.data}")

# Create the database and table if it doesn't exist
database_directory = "/var/www/bot/commands"
if not os.path.exists(database_directory):
    os.makedirs(database_directory)
database_file = os.path.join(database_directory, f"{CHANNEL_NAME}.db")
conn = sqlite3.connect(database_file)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS everyone (
        username TEXT PRIMARY KEY,
        group_name TEXT DEFAULT NULL
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS custom_commands (
        command TEXT PRIMARY KEY,
        response TEXT,
        status TEXT DEFAULT 'Enabled'
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_typos (
        username TEXT PRIMARY KEY,
        typo_count INTEGER DEFAULT 0
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS lurk_times (
        user_id TEXT PRIMARY KEY,
        start_time TEXT NOT NULL
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS hug_counts (
        username TEXT PRIMARY KEY,
        hug_count INTEGER DEFAULT 0
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS kiss_counts (
        username TEXT PRIMARY KEY,
        kiss_count INTEGER DEFAULT 0
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS total_deaths (
        death_count INTEGER DEFAULT 0
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS game_deaths (
        game_name TEXT PRIMARY KEY,
        death_count INTEGER DEFAULT 0
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS custom_counts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        command TEXT NOT NULL,
        count INTEGER NOT NULL
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS bits_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        user_name TEXT,
        bits INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscription_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        user_name TEXT,
        sub_plan TEXT,
        months INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS followers_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        user_name TEXT,
        followed_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS raid_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        raider_name TEXT,
        viewers INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quote TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS seen_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        welcome_message TEXT DEFAULT NULL,
        status TEXT DEFAULT 'True'
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS seen_today (
        user_id TEXT PRIMARY KEY
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS timed_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        interval INTEGER,
        message TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timezone TEXT DEFAULT NULL,
        weather_location TEXT DEFAULT NULL
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS protection (
        url_blocking TEXT DEFAULT 'False',
        profanity TEXT DEFAULT 'False'
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS link_whitelight (
        link TEXT PRIMARY KEY DEFAULT NULL
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS link_blacklisting (
        link TEXT PRIMARY KEY DEFAULT NULL
    )
''')
conn.commit()

# Initialize instances for the translator, shoutout queue, webshockets and permitted users for protection
translator = Translator(service_urls=['translate.google.com'])
shoutout_queue = queue.Queue()
bot_logger.info("Bot script started.")
connected = set()
permitted_users = {}
scheduled_tasks: List[Task] = []

# Setup Token Refresh
async def refresh_token_every_day():
    global REFRESH_TOKEN
    next_refresh_time = time.time() + 4 * 60 * 60 - 300  # 4 hours in seconds, minus 5 minutes for refresh
    while True:
        current_time = time.time()
        time_until_expiration = next_refresh_time - current_time

        if current_time >= next_refresh_time:
            REFRESH_TOKEN, next_refresh_time = await refresh_token(REFRESH_TOKEN)
        else:
            if time_until_expiration > 3600:  # More than 1 hour until expiration
                sleep_time = 3600  # Check again in 1 hour
            elif time_until_expiration > 300:  # More than 5 minutes until expiration
                sleep_time = 300  # Check again in 5 minutes
            else:
                sleep_time = 60  # Check every minute when close to expiration
            
            # Log only when the check frequency changes or is about to refresh
            twitch_logger.info(f"Next token check in {sleep_time // 60} minutes. Token is still valid for {time_until_expiration // 60} minutes and {time_until_expiration % 60} seconds.")
            await asyncio.sleep(sleep_time)  # Wait before checking again, based on the time until expiration

async def refresh_token(current_refresh_token):
    global CHANNEL_AUTH, REFRESH_TOKEN
    url = 'https://id.twitch.tv/oauth2/token'
    body = {
        'grant_type': 'refresh_token',
        'refresh_token': current_refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=body) as response:
                if response.status == 200:
                    response_json = await response.json()
                    new_access_token = response_json.get('access_token')
                    if new_access_token:
                        # Token refreshed successfully
                        new_refresh_token = response_json.get('refresh_token', current_refresh_token)

                        # Update the global variables with the new tokens
                        CHANNEL_AUTH = new_access_token
                        REFRESH_TOKEN = new_refresh_token

                        # Calculate the next refresh time to be 5 minutes before the 4-hour mark
                        next_refresh_time = time.time() + 4 * 60 * 60 - 300  # 4 hours in seconds, minus 5 minutes, so we refresh before actual expiration

                        log_message = "Refreshed token. New Access Token: {}, New Refresh Token: {}".format(new_access_token, new_refresh_token)
                        twitch_logger.info(log_message)

                        return new_refresh_token, next_refresh_time
                    else:
                        twitch_logger.error("Token refresh failed: 'access_token' not found in response")
                else:
                    twitch_logger.error(f"Token refresh failed: HTTP {response.status}")
    except Exception as e:
        # Log the error if token refresh fails
        twitch_logger.error(f"Token refresh failed: {e}")

# Setup Twitch PubSub
async def twitch_pubsub():
    # Twitch PubSub URL
    url = "wss://pubsub-edge.twitch.tv"

    # Twitch PubSub topics to subscribe to
    topics = [
        f"channel-bits-events-v2.{CHANNEL_ID}",  # Bits
        f"channel-subscribe-events-v1.{CHANNEL_ID}",  # Subscriptions
    ]

    # Log what Topics we're asking for.
    twitch_logger.info(f"Subscribing to PubSub Topics: {topics}")

    authentication = {
        "type": "LISTEN",
        "data": {
            "topics": topics,
            "auth_token": f"{CHANNEL_AUTH}"
        }
    }

    while True:
        try:
            # Connect to Twitch PubSub server
            async with websockets.connect(url) as websocket:
                twitch_logger.info("Connected to Twitch PubSub server.")

                # Send authentication data
                await websocket.send(json.dumps(authentication))
                twitch_logger.info("Authentication data sent.")

                while True:
                    response = await websocket.recv()
                    # Process the received message
                    await process_pubsub_message(response)

        except websockets.ConnectionClosedError:
            # Handle connection closed error
            twitch_logger.warning("Connection to Twitch PubSub server closed. Reconnecting...")
            await asyncio.sleep(10)  # Wait before retrying
        except Exception as e:
            # Handle other exceptions
            twitch_logger.exception("An error occurred in Twitch PubSub connection:", exc_info=e)

async def process_pubsub_message(message):
    try:
        message_data = json.loads(message)
        message_type = message_data["type"]

        # Process based on message type
        if message_type == "MESSAGE":
            topic = message_data["data"]["topic"]
            event_data = json.loads(message_data["data"]["message"])
            
            # Process bits event
            if topic.startswith("channel-bits-events-v"):
                bits_event_data = event_data["data"]
                user_id = bits_event_data["user_id"]
                user_name = bits_event_data["user_name"]
                bits = bits_event_data["bits_used"]
                await process_bits_event(user_id, user_name, bits)
                
            # Process subscription event
            elif topic.startswith("channel-subscribe-events-v"):
                subscription_event_data = event_data
                user_id = subscription_event_data.get("user_id")
                user_name = subscription_event_data.get("user_name")
                sub_plan = await sub_plan_to_tier_name(subscription_event_data.get["sub_plan"])
                months = subscription_event_data.get("cumulative_months", 1)
                context = subscription_event_data.get("context")
                
                if context == "subgift":
                    recipient_user_id = subscription_event_data["recipient_id"]
                    recipient_user_name = subscription_event_data["recipient_user_name"]
                    await process_subgift_event(recipient_user_id, recipient_user_name, sub_plan, months, user_name)
                elif context == "resub":
                    await process_regular_subscription_event(user_id, user_name, sub_plan, months)
                elif context == "anonsubgift":
                    recipient_user_id = subscription_event_data["recipient_id"]
                    recipient_user_name = subscription_event_data["recipient_user_name"]
                    await process_anonsubgift_event(sub_plan, months, recipient_user_id, recipient_user_name)
                elif context == "sub":
                    recipient_user_id = subscription_event_data["recipient_id"]
                    recipient_user_name = subscription_event_data["recipient_user_name"]
                    multi_month_duration = subscription_event_data["multi_month_duration"]
                    await process_multi_month_sub_event(user_id, user_name, sub_plan, months, recipient_user_id, recipient_user_name, multi_month_duration)
                
            # Add more conditions to process other types of events as needed
            else:
                twitch_logger.warning(f"Received message with unknown topic: {topic}")
        
        # Handle PING message
        elif message_type == "PING":
            await websockets.send(json.dumps({"type": "PONG"}))
        
        # Handle RECONNECT message
        elif message_type == "RECONNECT":
            # Perform the reconnection
            twitch_logger.info("Received RECONNECT message. Reconnecting...")
            await websockets.close()
            await asyncio.sleep(5)
            await twitch_pubsub()
        
        # Handle AUTH_REVOKED message
        elif message_type == "AUTH_REVOKED":
            revoked_topics = message_data["data"]["topics"]
            twitch_logger.warning(f"Authentication revoked for topics: {revoked_topics}")
            pass

    except Exception as e:
        twitch_logger.exception("An error occurred while processing PubSub message:", exc_info=e)

class BotOfTheSpecter(commands.Bot):
    # Event Message to get the bot ready
    def __init__(self, token, prefix, channel_name):
        super().__init__(token=token, prefix=prefix, initial_channels=[channel_name])
        self.channel_name = channel_name

    async def event_ready(self):
        bot_logger.info(f'Logged in as | {self.nick}')
        channel = self.get_channel(self.channel_name)
        await channel.send(f"/me is connected and ready! Running V{VERSION}")

    # Function to check all messages and push out a custom command.
    async def event_message(self, message):
        # Ignore messages from the bot itself
        if message.echo:
            return

        # Log the message content
        chat_history_logger.info(f"Chat message from {message.author.name}: {message.content}")

        # Check for a valid author before proceeding
        if message.author is None:
            bot_logger.warning("Received a message without a valid author.")
            return
        
        # Handle commands
        await self.handle_commands(message)

        # Additonal welcome message handling logic
        await self.handle_welcome_message(message)
        
        # Additional custom message handling logic
        await self.handle_chat(message)

        # Process user group
        messageAuthor = message.author.name
        messageAuthorID = message.author.id
        await handle_user_grouping(messageAuthor, messageAuthorID)

    # Function to handle chat messages
    async def handle_chat(self, message):
        # Get message content to check if the message is a custom command
        message_content = message.content.strip().lower()  # Lowercase for case-insensitive match
        if message_content.startswith('!'):
            command_parts = message_content.split()
            command = command_parts[0][1:]  # Extract the command without '!'

            # Log all command usage
            chat_logger.info(f"{message.author.name} used the command: {command}")

            if command in builtin_commands or command in builtin_aliases:
                chat_logger.info(f"{message.author.name} used a built-in command called: {command}")
                return  # It's a built-in command or alias, do nothing more

            # Check if the command exists in a hypothetical database and respond
            cursor.execute('SELECT response, status FROM custom_commands WHERE command = ?', (command,))
            result = cursor.fetchone()

            if result:
                if result[1] == 'Enabled':
                    response = result[0]
                    # Check if the user has a custom API URL
                    if '(customapi.' in response:
                        url_match = re.search(r'\(customapi\.(\S+)\)', response)
                        if url_match:
                            url = url_match.group(1)
                            api_response = fetch_api_response(url)
                            response = response.replace(f"(customapi.{url})", api_response)
                    # Check if the user has a custom count
                    if '(count)' in response:
                        try:
                            update_custom_count(command)
                            get_count = get_custom_count(command)
                            response = response.replace('(count)', str(get_count))
                        except Exception as e:
                            chat_logger.error(f"{e}")
                    if '(daysuntil.' in response:
                        # Getting the date from the response = YEAR-MONTH-DAY
                        get_date = re.search(r'\(daysuntil\.(\d{4}-\d{2}-\d{2})\)', response)
                        if get_date:
                            date_str = get_date.group(1)
                            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                            current_date = datetime.now().date()
                            days_left = (event_date - current_date).days
                            response = response.replace(f"(daysuntil.{date_str})", str(days_left))
                    chat_logger.info(f"{command} command ran with response: {response}")
                    await message.channel.send(response)
                else:
                    chat_logger.info(f"{command} not ran becasue it's disabled.")
            else:
                # chat_logger.info(f"{message.author.name} tried to run a command called: {command}, but it's not a command.")
                # await message.channel.send(f'No such command found: !{command}')
                pass
        else:
            # If the message is not a command and does not come from a moderator or broadcaster, check for protection
            if 'http://' in message.content or 'https://' in message.content:
                # Fetch url_blocking option from the protection table in the user's database
                cursor.execute('SELECT url_blocking FROM protection')
                result = cursor.fetchone()
                if result:
                    url_blocking = bool(result[0])
                else:
                    # If url_blocking not found in the database, default to False
                    url_blocking = False

                # Check if url_blocking is enabled
                if url_blocking:
                    # Check if the user is permitted to post links
                    if message.author.name in permitted_users and time.time() < permitted_users[message.author.name]:
                        # User is permitted, skip URL blocking
                        return

                    if is_mod_or_broadcaster(message.author.name):
                        # User is a mod or is the broadcaster, they are by default permitted.
                        return

                    # Fetch link whitelist from the database
                    cursor.execute('SELECT link FROM link_whitelist')
                    whitelisted_links = cursor.fetchall()
                    whitelisted_links = [link[0] for link in whitelisted_links]

                    cursor.execute('SELECT link FROM link_blacklisting')
                    blacklisted_links = cursor.fetchall()
                    blacklisted_links = [link[0] for link in blacklisted_links]

                    # Check if the message content contains any whitelisted or blacklisted link
                    contains_whitelisted_link = any(link in message.content for link in whitelisted_links)
                    contains_blacklisted_link = any(link in message.content for link in blacklisted_links)

                    # Check if the message content contains a Twitch clip link
                    contains_twitch_clip_link = 'https://clips.twitch.tv/' in message.content

                    if contains_blacklisted_link:
                        # Delete the message if it contains a blacklisted URL
                        await message.delete()
                        chat_logger.info(f"Deleted message from {message.author.name} containing a blacklisted URL: {message.content}")
                        await message.channel.send(f"Oops! That link looks like it's gone on an adventure! Please ask a mod to give it a check and launch an investigation to find out where it's disappeared to!")
                        return  # Stop further processing
                    elif not contains_whitelisted_link and not contains_twitch_clip_link:
                        # Delete the message if it contains a URL and it's not whitelisted or a Twitch clip link
                        await message.delete()
                        chat_logger.info(f"Deleted message from {message.author.name} containing a URL: {message.content}")
                        # Notify the user not to post links without permission
                        await message.channel.send(f"{message.author.name}, links are not authorized in chat, ask moderator or the Broadcaster for permission.")
                    else:
                        chat_logger.info(f"URL found in message from {message.author.name}, not deleted due to being whitelisted or a Twitch clip link.")
                else:
                    chat_logger.info(f"URL found in message from {message.author.name}, but URL blocking is disabled.")

    # Function to handle welcome messages
    async def handle_welcome_message(self, message):
        # Setup for welcome messages
        user_trigger = message.author.name
        user_trigger_id = message.author.id

        # Has the user been seen during this stream
        cursor.execute('SELECT * FROM seen_today WHERE user_id = ?', (user_trigger_id,))
        temp_seen_users = cursor.fetchone()

        # Check if the user is in the list of already seen users
        if temp_seen_users:
            # twitch_logger.info(f"{user_trigger} has already had their welcome message.")
            return

        # Check if the user is the broadcaster
        if user_trigger.lower() == CHANNEL_NAME.lower():
            # twitch_logger.info(f"{CHANNEL_NAME} can't have a welcome message.")
            return

        # Check if the user is a VIP or MOD
        is_vip = is_user_vip(user_trigger_id)
        # twitch_logger.info(f"{user_trigger} - VIP={is_vip}")
        is_mod = is_user_moderator(user_trigger_id)
        # twitch_logger.info(f"{user_trigger} - MOD={is_mod}")

        # Check if the user is new or returning
        cursor.execute('SELECT * FROM seen_users WHERE username = ?', (user_trigger,))
        user_data = cursor.fetchone()

        if user_data:
            user_status = True
            welcome_message = user_data[2]
            user_status_enabled = user_data[3]
            cursor.execute('INSERT INTO seen_today (user_id) VALUES (?)', (user_trigger_id,))
            conn.commit()
            # twitch_logger.info(f"{user_trigger} has been found in the database.")
        else:
            user_status = False
            welcome_message = None
            user_status_enabled = 'True'
            cursor.execute('INSERT INTO seen_today (user_id) VALUES (?)', (user_trigger_id,))
            conn.commit()
            # twitch_logger.info(f"{user_trigger} has not been found in the database.")

        if user_status_enabled == 'True':
            if is_vip:
                # VIP user
                if user_status and welcome_message:
                    # Returning user with custom welcome message
                    await message.channel.send(welcome_message)
                elif user_status:
                    # Returning user
                    vip_welcome_message = f"ATTENTION! A very important person has entered the chat, welcome {user_trigger}!"
                    await message.channel.send(vip_welcome_message)
                else:
                    # New user
                    await user_is_seen(user_trigger)
                    new_vip_welcome_message = f"ATTENTION! A very important person has entered the chat, let's give {user_trigger} a warm welcome!"
                    await message.channel.send(new_vip_welcome_message)
            elif is_mod:
                # Moderator user
                if user_status and welcome_message:
                    # Returning user with custom welcome message
                    await message.channel.send(welcome_message)
                elif user_status:
                    # Returning user
                    mod_welcome_message = f"MOD ON DUTY! Welcome in {user_trigger}. The power of the sword has increased!"
                    await message.channel.send(mod_welcome_message)
                else:
                    # New user
                    await user_is_seen(user_trigger)
                    new_mod_welcome_message = f"MOD ON DUTY! Welcome in {user_trigger}. The power of the sword has increased! Let's give {user_trigger} a warm welcome!"
                    await message.channel.send(new_mod_welcome_message)
            else:
                # Non-VIP and Non-mod user
                if user_status and welcome_message:
                    # Returning user with custom welcome message
                    await message.channel.send(welcome_message)
                elif user_status:
                    # Returning user
                    welcome_back_message = f"Welcome back {user_trigger}, glad to see you again!"
                    await message.channel.send(welcome_back_message)
                else:
                    # New user
                    await user_is_seen(user_trigger)
                    new_user_welcome_message = f"{user_trigger} is new to the community, let's give them a warm welcome!"
                    await message.channel.send(new_user_welcome_message)
        else:
            # Status disabled for user
            chat_logger.info(f"Message not sent for {user_trigger} as status is disabled.")

    @commands.command(name='commands', aliases=['cmds',])
    async def commands_command(self, ctx):
        is_mod = is_mod_or_broadcaster(ctx.author)
        
        # Fetch custom commands from the database
        cursor.execute('SELECT command FROM custom_commands')
        custom_commands = [row[0] for row in cursor.fetchall()]
        
        # Construct the list of custom commands
        custom_commands_list = ", ".join(sorted(f"!{command}" for command in custom_commands))
    
        if is_mod:
            # If the user is a mod, include both custom_commands and builtin_commands
            all_commands = list(mod_commands) + list(builtin_commands)
        else:
            # If the user is not a mod, only include builtin_commands
            all_commands = list(builtin_commands)
        
        # Construct the list of available commands to the user
        commands_list = ", ".join(sorted(f"!{command}" for command in all_commands))
    
        # Construct the response messages
        response_message = f"Available commands to you: {commands_list}"
        custom_response_message = f"Available Custom Commands: https://commands.botofthespecter.com/?user={CHANNEL_NAME}"
    
        # Sending the response messages to the chat
        await ctx.send(response_message)
        await ctx.send(custom_response_message)

    @commands.command(name='bot')
    async def bot_command(self, ctx):
        chat_logger.info(f"{ctx.author} ran the Bot Command.")
        await ctx.send(f"This amazing bot is built by the one and the only gfaUnDead.")
    
    @commands.command(name='roadmap')
    async def roadmap_command(self, ctx):
        await ctx.send("Here's the roadmap for the bot: https://trello.com/b/EPXSCmKc/specterbot")

    @commands.command(name='weather')
    async def weather_command(self, ctx, location: str = None) -> None:
        if location:
            if ' ' in location:
                await ctx.send(f"Please provide the location in the format: City,CountryCode (e.g. Sydney,AU)")
                return
            weather_info = get_weather(location)
        else:
            location = get_streamer_weather()
            if location:
                weather_info = get_weather(location)
            else:
                weather_info = "I'm sorry, something went wrong trying to get the current weather."
        await ctx.send(weather_info)

    @commands.command(name='time')
    async def time_command(self, ctx, timezone: str = None) -> None:
        if timezone:
            tz = pytz.timezone(timezone)
            chat_logger.info(f"TZ: {tz} | Timezone: {timezone}")
            current_time = datetime.now(tz)
            time_format_date = current_time.strftime("%B %d, %Y")
            time_format_time = current_time.strftime("%I:%M %p")
            time_format_week = current_time.strftime("%A")
            time_format = f"For the timezone {timezone}, it is {time_format_week}, {time_format_date} and the time is: {time_format_time}"
        else:
            cursor.execute("SELECT timezone FROM profile")
            timezone = cursor.fetchone()[0]
            if timezone:
                tz = pytz.timezone(timezone)
                chat_logger.info(f"TZ: {tz} | Timezone: {timezone}")
                current_time = datetime.now(tz)
                time_format_date = current_time.strftime("%B %d, %Y")
                time_format_time = current_time.strftime("%I:%M %p")
                time_format_week = current_time.strftime("%A")
                time_format = f"It is {time_format_week}, {time_format_date} and the time is: {time_format_time}"
            else:
                ctx.send(f"Streamer timezone is not set.")
        await ctx.send(time_format)
    
    @commands.command(name='quote')
    async def quote_command(self, ctx, number: int = None):
        if number is None:  # If no number is provided, get a random quote
            cursor.execute("SELECT quote FROM quotes ORDER BY RANDOM() LIMIT 1")
            quote = cursor.fetchone()
            if quote:
                await ctx.send("Random Quote: " + quote[0])
            else:
                await ctx.send("No quotes available.")
        else:  # If a number is provided, retrieve the quote by its ID
            cursor.execute("SELECT quote FROM quotes WHERE id = ?", (number,))
            quote = cursor.fetchone()
            if quote:
                await ctx.send(f"Quote {number}: " + quote[0])
            else:
                await ctx.send(f"No quote found with ID {number}.")

    @commands.command(name='quoteadd')
    async def quote_add_command(self, ctx, *, quote):
        cursor.execute("INSERT INTO quotes (quote) VALUES (?)", (quote,))
        conn.commit()
        await ctx.send("Quote added successfully: " + quote)

    @commands.command(name='removequote')
    async def quote_remove_command(self, ctx, number: int = None):
        if number is None:
            ctx.send("Please specify the ID to remove.")
            return
        
        cursor.execute("DELETE FROM quotes WHERE ID = ?", (number,))
        conn.commit()
        await ctx.send(f"Quote {number} has been removed.")
    
    @commands.command(name='permit')
    async def permit_command(ctx, permit_user: str = None):
        if is_mod_or_broadcaster(ctx.author):
            permit_user = permit_user.lstrip('@')
            if permit_user:
                permitted_users[permit_user] = time.time() + 30
                await ctx.send(f"{permit_user} is now permitted to post links for the next 30 seconds.")
            else:
                await ctx.send("Please specify a user to permit.")
        else:
            chat_logger.info(f"{ctx.author} tried to use the command, !permit, but couldn't as they are not a moderator.")
            await ctx.send("You must be a moderator or the broadcaster to use this command.")

    # Command to set stream title
    @commands.command(name='settitle')
    async def set_title_command(self, ctx, *, title: str = None) -> None:
        if is_mod_or_broadcaster(ctx.author):
            if title is None:
                await ctx.send(f"Stream titles can not be blank. You must provide a title for the stream.")
                return

            # Update the stream title
            await trigger_twitch_title_update(title)
            twitch_logger.info(f'Setting stream title to: {title}')
            await ctx.send(f'Stream title updated to: {title}')
        else:
            await ctx.send(f"You must be a moderator or the broadcaster to use this command.")

    # Command to set stream game/category
    @commands.command(name='setgame')
    async def set_game_command(self, ctx, *, game: str = None) -> None:
        if is_mod_or_broadcaster(ctx.author):
            if game is None:
                await ctx.send("You must provide a game for the stream.")
                return

            # Get the game ID
            try:
                game_id = await get_game_id(game)
                # Update the stream game/category
                await trigger_twitch_game_update(game_id)
                twitch_logger.info(f'Setting stream game to: {game}')
                await ctx.send(f'Stream game updated to: {game}')
            except GameNotFoundException as e:
                await ctx.send(str(e))
            except GameUpdateFailedException as e:
                await ctx.send(str(e))
            except Exception as e:
                await ctx.send(f'An error occurred: {str(e)}')
        else:
            await ctx.send("You must be a moderator or the broadcaster to use this command.")

    @commands.command(name='song')
    async def get_current_song_command(self, ctx):
        await ctx.send("Please stand by, checking what song is currently playing...")
        try:
            song_info = await get_song_info_command()
            await ctx.send(song_info)
        except Exception as e:
            chat_logger.error(f"An error occurred while getting current song: {e}")
            await ctx.send("Sorry, there was an error retrieving the current song.")

    @commands.command(name='timer')
    async def start_timer_command(self, ctx):
        chat_logger.info(f"Timer command ran.")
        content = ctx.message.content.strip()
        try:
            _, minutes = content.split(' ')
            minutes = int(minutes)
        except ValueError:
            # Default to 5 minutes if the user didn't provide a valid value
            minutes = 5

        await ctx.send(f"Timer started for {minutes} minute(s) @{ctx.author.name}.")

        # Set a fixed interval of 30 seconds for countdown messages
        interval = 30

        # Wait for the first countdown message after the initial delay
        await asyncio.sleep(interval)

        for remaining_seconds in range((minutes * 60) - interval, 0, -interval):
            minutes_left = remaining_seconds // 60
            seconds_left = remaining_seconds % 60

            # Format the countdown message
            countdown_message = f"@{ctx.author.name}, timer has "

            if minutes_left > 0:
                countdown_message += f"{minutes_left} minute(s) "

            if seconds_left > 0:
                countdown_message += f"{seconds_left} second(s) left."
            else:
                countdown_message += "left."

            # Send countdown message
            await ctx.send(countdown_message)

            # Wait for the fixed interval of 30 seconds before sending the next message
            await asyncio.sleep(interval)

        await ctx.send(f"The {minutes} minute timer has ended @{ctx.author.name}!")

    @commands.command(name='hug')
    async def hug_command(self, ctx, *, mentioned_username: str = None):
        if mentioned_username:
            target_user = mentioned_username.lstrip('@')

            # Increment hug count in the database
            cursor.execute('INSERT INTO hug_counts (username, hug_count) VALUES (?, 1) ON CONFLICT(username) DO UPDATE SET hug_count = hug_count + 1', (target_user,))
            conn.commit()

            # Retrieve the updated count
            cursor.execute('SELECT hug_count FROM hug_counts WHERE username = ?', (target_user,))
            hug_count = cursor.fetchone()[0]

            # Send the message
            chat_logger.info(f"{target_user} has been hugged by {ctx.author}. They have been hugged: {hug_count}")
            await ctx.send(f"@{target_user} has been hugged by @{ctx.author.name}, they have been hugged {hug_count} times.")
        else:
            chat_logger.info(f"{ctx.author} tried to run the command without user mentioned.")
            await ctx.send("Usage: !hug @username")

    @commands.command(name='kiss')
    async def kiss_command(self, ctx, *, mentioned_username: str = None):
        if mentioned_username:
            target_user = mentioned_username.lstrip('@')

            # Increment kiss count in the database
            cursor.execute('INSERT INTO kiss_counts (username, kiss_count) VALUES (?, 1) ON CONFLICT(username) DO UPDATE SET kiss_count = kiss_count + 1', (target_user,))
            conn.commit()

            # Retrieve the updated count
            cursor.execute('SELECT kiss_count FROM kiss_counts WHERE username = ?', (target_user,))
            kiss_count = cursor.fetchone()[0]

            # Send the message
            chat_logger.info(f"{target_user} has been kissed by {ctx.author}. They have been kissed: {kiss_count}")
            await ctx.send(f"@{target_user} has been kissed by @{ctx.author.name}, they have been kissed {kiss_count} times.")
        else:
            chat_logger.info(f"{ctx.author} tried to run the command without user mentioned.")
            await ctx.send("Usage: !kiss @username")

    @commands.command(name='ping')
    async def ping_command(self, ctx):
        chat_logger.info(f"Ping command ran.")
        # Using subprocess to run the ping command
        result = subprocess.run(["ping", "-c", "1", "ping.botofthespecter.com"], stdout=subprocess.PIPE)
    
        # Decode the result from bytes to string and search for the time
        output = result.stdout.decode('utf-8')
        match = re.search(r"time=(\d+\.\d+) ms", output)
    
        if match:
            ping_time = match.group(1)
            bot_logger.info(f"Pong: {ping_time} ms")
            await ctx.send(f'Pong: {ping_time} ms')
        else:
            bot_logger.error(f"Error Pinging. {output}")
            await ctx.send(f'Error pinging')
    
    @commands.command(name='translate')
    async def translate_command(self, ctx):
        # Get the message content after the command
        message = ctx.message.content[len("!translate "):]

        # Check if there is a message to translate
        if not message:
            await ctx.send("Please provide a message to translate.")
            return

        try:
            # Check if the input message is too short
            if len(message.strip()) < 5:
                await ctx.send("The provided message is too short for reliable translation.")
                return

            # Debugging: Log the message content
            chat_logger.info(f"Message content: {message}")

            # Detect the language of the input text
            detected_lang = translator.detect(message)
            source_lang = detected_lang.lang if detected_lang else None

            # Debugging: Log detected language
            chat_logger.info(f"Detected language: {source_lang}")

            if source_lang:
                source_lang_name = LANGUAGES.get(source_lang, "Unknown")
                chat_logger.info(f"Translator Detected Language as: {source_lang_name}.")

                # Translate the message to English
                translated_message = translator.translate(message, src=source_lang, dest='en').text
                chat_logger.info(f'Translated from "{message}" to "{translated_message}"')

                # Send the translated message along with the source language
                await ctx.send(f"Detected Language: {source_lang_name}. Translation: {translated_message}")
            else:
                await ctx.send("Unable to detect the source language.")
        except AttributeError as ae:
            chat_logger.error(f"AttributeError: {ae}")
            await ctx.send("An error occurred while detecting the language.")
        except Exception as e:
            chat_logger.error(f"Translating error: {e}")
            await ctx.send("An error occurred while translating the message.")

    @commands.command(name='cheerleader')
    async def cheerleader_command(self, ctx):
        headers = {
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {CHANNEL_AUTH}'
        }
        params = {
            'count': 1
        }
        response = requests.get('https://api.twitch.tv/helix/bits/leaderboard', headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            if data['data']:
                top_cheerer = data['data'][0]
                score = "{:,}".format(top_cheerer['score'])
                await ctx.send(f"The current top cheerleader is {top_cheerer['user_name']} with {score} bits!")
            else:
                await ctx.send("There is no one currently in the leaderboard for bits, cheer to take this spot.")
        elif response.status_code == 401:
            await ctx.send("Sorry, something went wrong while reaching the Twitch API.")
        else:
            await ctx.send("Sorry, I couldn't fetch the leaderboard.")

    @commands.command(name='mybits')
    async def mybits_command(self, ctx):
        user_id = str(ctx.author.id)
        headers = {
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {CHANNEL_AUTH}'
        }
        params = {
            'user_id': user_id
        }
        response = requests.get('https://api.twitch.tv/helix/bits/leaderboard', headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            if data['data']:
                user_bits = data['data'][0]
                bits = "{:,}".format(user_bits['score'])
                await ctx.send(f"You have given {bits} bits in total.")
            else:
                await ctx.send("You haven't given any bits yet.")
        elif response.status_code == 401:
            await ctx.send("Sorry, something went wrong while reaching the Twitch API.")
        else:
            await ctx.send("Sorry, I couldn't fetch your bits information.")

    @commands.command(name='lurk')
    async def lurk_command(self, ctx):
        try:
            user_id = str(ctx.author.id)
            now = datetime.now()

            if ctx.author.name.lower() == CHANNEL_NAME.lower():
                await ctx.send(f"You cannot lurk in your own channel, Streamer.")
                chat_logger.info(f"{ctx.author.name} tried to lurk in their own channel.")
                return

            # Check if the user is already in the lurk table
            cursor.execute('SELECT start_time FROM lurk_times WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()

            if result:
                # User was lurking before
                previous_start_time = datetime.fromisoformat(result[0])
                lurk_duration = now - previous_start_time

                # Calculate the duration
                days, seconds = divmod(lurk_duration.total_seconds(), 86400)
                months, days = divmod(days, 30)
                hours, remainder = divmod(seconds, 3600)
                minutes, seconds = divmod(remainder, 60)

                # Create time string
                periods = [("months", int(months)), ("days", int(days)), ("hours", int(hours)), ("minutes", int(minutes)), ("seconds", int(seconds))]
                time_string = ", ".join(f"{value} {name}" for name, value in periods if value)

                # Inform the user of their previous lurk time
                await ctx.send(f"Continuing to lurk, {ctx.author.name}? No problem, you've been lurking for {time_string}. I've reset your lurk time.")
                chat_logger.info(f"{ctx.author.name} refreshed their lurk time after {time_string}.")
            else:
                # User is not in the lurk table
                await ctx.send(f"Thanks for lurking, {ctx.author.name}! See you soon.")
                chat_logger.info(f"{ctx.author.name} is now lurking.")

            # Update the start time in the database
            cursor.execute('INSERT OR REPLACE INTO lurk_times (user_id, start_time) VALUES (?, ?)', (user_id, now.isoformat()))
            conn.commit()
        except Exception as e:
            chat_logger.error(f"Error in lurk_command: {e}")
            await ctx.send(f"Oops, something went wrong while trying to lurk.")

    @commands.command(name='lurking')
    async def lurking_command(self, ctx):
        try:
            user_id = str(ctx.author.id)
    
            if ctx.author.name.lower() == CHANNEL_NAME.lower():
                await ctx.send(f"Streamer, you're always present!")
                chat_logger.info(f"{ctx.author.name} tried to check lurk time in their own channel.")
                return
    
            cursor.execute('SELECT start_time FROM lurk_times WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
    
            if result:
                start_time = datetime.fromisoformat(result[0])
                elapsed_time = datetime.now() - start_time
    
                # Calculate the duration
                days = elapsed_time.days
                months = days // 30
                days %= 30
                hours, seconds = divmod(elapsed_time.seconds, 3600)
                minutes, seconds = divmod(seconds, 60)
    
                # Build the time string
                periods = [("months", int(months)), ("days", int(days)), ("hours", int(hours)), ("minutes", int(minutes)), ("seconds", int(seconds))]
                time_string = ", ".join(f"{value} {name}" for name, value in periods if value)
    
                # Send the lurk time message
                await ctx.send(f"{ctx.author.name}, you've been lurking for {time_string} so far.")
                chat_logger.info(f"{ctx.author.name} checked their lurk time: {time_string}.")
            else:
                await ctx.send(f"{ctx.author.name}, you're not currently lurking.")
                chat_logger.info(f"{ctx.author.name} tried to check lurk time but is not lurking.")
        except Exception as e:
            chat_logger.error(f"Error in lurking_command: {e}")
            await ctx.send(f"Oops, something went wrong while trying to check your lurk time.")

    @commands.command(name='lurklead')
    async def lurklead_command(self, ctx):
        try:
            cursor.execute('SELECT user_id, start_time FROM lurk_times')
            lurkers = cursor.fetchall()

            longest_lurk = None
            longest_lurk_user_id = None
            now = datetime.now()

            for user_id, start_time in lurkers:
                start_time = datetime.fromisoformat(start_time)
                lurk_duration = now - start_time

                if longest_lurk is None or lurk_duration > longest_lurk:
                    longest_lurk = lurk_duration
                    longest_lurk_user_id = user_id

            if longest_lurk_user_id:
                display_name = await get_display_name(longest_lurk_user_id)

                if display_name:
                    # Calculate the duration
                    days, seconds = divmod(longest_lurk.total_seconds(), 86400)
                    months, days = divmod(days, 30)
                    hours, remainder = divmod(seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)

                    # Build the time string
                    periods = [("months", int(months)), ("days", int(days)), ("hours", int(hours)), ("minutes", int(minutes)), ("seconds", int(seconds))]
                    time_string = ", ".join(f"{value} {name}" for name, value in periods if value)

                    # Send the message
                    await ctx.send(f"{display_name} is currently lurking the most with {time_string} on the clock.")
                    chat_logger.info(f"Lurklead command run. User {display_name} has the longest lurk time of {time_string}.")
                else:
                    await ctx.send("There was an issue retrieving the display name of the lurk leader.")
            else:
                await ctx.send("No one is currently lurking.")
                chat_logger.info("Lurklead command run but no lurkers found.")
        except Exception as e:
            chat_logger.error(f"Error in lurklead_command: {e}")
            await ctx.send("Oops, something went wrong while trying to find the lurk leader.")

    @commands.command(name='unlurk', aliases=('back',))
    async def unlurk_command(self, ctx):
        try:
            user_id = str(ctx.author.id)
            if ctx.author.name.lower() == CHANNEL_NAME.lower():
                await ctx.send(f"Streamer, you've been here all along!")
                chat_logger.info(f"{ctx.author.name} tried to unlurk in their own channel.")
                return

            cursor.execute('SELECT start_time FROM lurk_times WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()

            if result:
                start_time = datetime.fromisoformat(result[0])
                elapsed_time = datetime.now() - start_time

                # Calculate the duration
                days, seconds = divmod(elapsed_time.total_seconds(), 86400)
                months, days = divmod(days, 30)
                hours, remainder = divmod(seconds, 3600)
                minutes, seconds = divmod(remainder, 60)

                # Build the time string
                periods = [("months", int(months)), ("days", int(days)), ("hours", int(hours)), ("minutes", int(minutes)), ("seconds", int(seconds))]
                time_string = ", ".join(f"{value} {name}" for name, value in periods if value)

                # Log the unlurk command execution and send a response
                chat_logger.info(f"{ctx.author.name} is no longer lurking. Time lurking: {time_string}")
                await ctx.send(f"{ctx.author.name} has returned from the shadows after {time_string}, welcome back!")

                # Remove the user's start time from the database
                cursor.execute('DELETE FROM lurk_times WHERE user_id = ?', (user_id,))
                conn.commit()
            else:
                await ctx.send(f"{ctx.author.name} has returned from lurking, welcome back!")
        except Exception as e:
            chat_logger.error(f"Error in unlurk_command: {e}")
            await ctx.send(f"Oops, something went wrong with the unlurk command.")

    @commands.command(name='clip')
    async def clip_command(self, ctx):
        try:
            if not stream_online:
                await ctx.send("Sorry, I can only create clips while the stream is online.")
                return

            # Headers & Params for TwitchAPI
            headers = {
                "Client-ID": TWITCH_API_CLIENT_ID,
                "Authorization": f"Bearer {CHANNEL_AUTH}"
            }
            params = {
                "broadcaster_id": CHANNEL_ID
            }
            clip_response = requests.post('https://api.twitch.tv/helix/clips', headers=headers, params=params)
            if clip_response.status_code == 202:
                clip_data = clip_response.json()
                clip_id = clip_data['data'][0]['id']
                clip_url = f"http://clips.twitch.tv/{clip_id}"
                await ctx.send(f"{ctx.author.name} created a clip: {clip_url}")

                # Create a stream marker
                marker_description = f"Clip created by {ctx.author.name}"
                marker_payload = {
                    "user_id": CHANNEL_ID,
                    "description": marker_description
                }
                marker_headers = {
                    "Client-ID": TWITCH_API_CLIENT_ID,
                    "Authorization": f"Bearer {CHANNEL_AUTH}",
                    "Content-Type": "application/json"
                }
                marker_response = requests.post('https://api.twitch.tv/helix/streams/markers', headers=marker_headers, json=marker_payload)
                if marker_response.status_code == 200:
                    marker_data = marker_response.json()
                    marker_created_at = marker_data['data'][0]['created_at']
                    twitch_logger.info(f"A stream marker was created at {marker_created_at} with description: {marker_description}.")
                else:
                    twitch_logger.info("Failed to create a stream marker for the clip.")

            else:
                await ctx.send(f"Failed to create clip.")
                twitch_logger.error(f"Clip Error Code: {clip_response.status_code}")
        except requests.exceptions.RequestException as e:
            twitch_logger.error(f"Error making clip: {e}")
            await ctx.send("An error occurred while making the request. Please try again later.")

    @commands.command(name='marker')
    async def marker_command(self, ctx, *, description: str):
        if is_mod_or_broadcaster(ctx.author):
            if description:
                marker_description = description
            else:
                marker_description = f"Marker made by {ctx.author.name}"
            try:
                marker_payload = {
                    "user_id": CHANNEL_ID,
                    "description": marker_description
                }
                marker_headers = {
                    "Client-ID": TWITCH_API_CLIENT_ID,
                    "Authorization": f"Bearer {CHANNEL_AUTH}",
                    "Content-Type": "application/json"
                }
                marker_response = requests.post('https://api.twitch.tv/helix/streams/markers', headers=marker_headers, json=marker_payload)
                if marker_response.status_code == 200:
                    marker_data = marker_response.json()
                    marker_created_at = marker_data['data'][0]['created_at']
                    await ctx.send(f"A stream marker was created at {marker_created_at} with description: {marker_description}.")
                else:
                    await ctx.send("Failed to create a stream marker.")
            except requests.exceptions.RequestException as e:
                twitch_logger.error(f"Error creating stream marker: {e}")
                await ctx.send("An error occurred while making the request. Please try again later.")
        else:
            await ctx.send(f"You must be a moderator or the broadcaster to use this command.")

    @commands.command(name='subscription', aliases=['mysub'])
    async def subscription_command(self, ctx):
        try:
            # Headers & Params for Twitch API
            user_id = ctx.author.id
            headers = {
                "Client-ID": TWITCH_API_CLIENT_ID,
                "Authorization": f"Bearer {CHANNEL_AUTH}"
            }
            params = {
                "broadcaster_id": CHANNEL_ID,
                "user_id": user_id
            }
            tier_mapping = {
                "1000": "Tier 1",
                "2000": "Tier 2",
                "3000": "Tier 3"
            }
            subscription_response = requests.get('https://api.twitch.tv/helix/subscriptions', headers=headers, params=params)
            if subscription_response.status_code == 200:
                subscription_data = subscription_response.json()
                subscriptions = subscription_data.get('data', [])

                if subscriptions:
                    # Iterate over each subscription
                    for subscription in subscriptions:
                        user_name = subscription['user_name']
                        tier = subscription['tier']
                        is_gift = subscription['is_gift']
                        gifter_name = subscription['gifter_name'] if is_gift else None
                        tier_name = tier_mapping.get(tier, tier)

                        # Prepare message based on subscription status
                        if is_gift:
                            await ctx.send(f"{user_name}, your gift subscription from {gifter_name} is {tier_name}.")
                        else:
                            await ctx.send(f"{user_name}, you are currently subscribed at {tier_name}.")
                else:
                    # If no subscriptions found for the provided user ID
                    await ctx.send(f"You are currently not subscribed to {CHANNEL_NAME}, you can subscribe here: https://subs.twitch.tv/{CHANNEL_NAME}")
            else:
                await ctx.send(f"Failed to retrieve subscription information. Please try again later.")
                twitch_logger.error(f"Failed to retrieve subscription information. Status code: {subscription_response.status_code}")

        except requests.exceptions.RequestException as e:
            twitch_logger.error(f"Error retrieving subscription information: {e}")
            await ctx.send("An error occurred while making the request. Please try again later.")

    @commands.command(name='uptime')
    async def uptime_command(self, ctx):
        chat_logger.info("Uptime Command ran.")
        headers = {
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {CHANNEL_AUTH}'
        }
        params = {
            'user_login': CHANNEL_NAME,
            'type': 'live'
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.twitch.tv/helix/streams', headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data['data']:  # If stream is live
                            started_at_str = data['data'][0]['started_at']
                            started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
                            started_at = started_at.replace(tzinfo=timezone.utc)
                            uptime = datetime.now(timezone.utc) - started_at
                            hours, remainder = divmod(uptime.seconds, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            await ctx.send(f"The stream has been live for {hours} hours, {minutes} minutes, and {seconds} seconds.")
                            chat_logger.info(f"{CHANNEL_NAME} has been online for {uptime}.")
                        else:
                            await ctx.send(f"{CHANNEL_NAME} is currently offline.")
                            api_logger.info(f"{CHANNEL_NAME} is currently offline.")
                    else:
                        await ctx.send(f"Failed to retrieve stream data. Status: {response.status}")
                        chat_logger.error(f"Failed to retrieve stream data. Status: {response.status}")
        except Exception as e:
            chat_logger.error(f"Error retrieving stream data: {e}")
            await ctx.send("Oops, something went wrong while trying to check uptime.")
    
    @commands.command(name='typo')
    async def typo_command(self, ctx, *, mentioned_username: str = None):
        chat_logger.info("Typo Command ran.")
        # Check if the broadcaster is running the command
        if ctx.author.name.lower() == CHANNEL_NAME.lower() or (mentioned_username and mentioned_username.lower() == CHANNEL_NAME.lower()):
            await ctx.send("Dear Streamer, you can never have a typo in your own channel.")
            return

        # Determine the target user: mentioned user or the command caller
        target_user = mentioned_username.lower().lstrip('@') if mentioned_username else ctx.author.name.lower()

        # Increment typo count in the database
        cursor.execute('INSERT INTO user_typos (username, typo_count) VALUES (?, 1) ON CONFLICT(username) DO UPDATE SET typo_count = typo_count + 1', (target_user,))
        conn.commit()

        # Retrieve the updated count
        cursor.execute('SELECT typo_count FROM user_typos WHERE username = ?', (target_user,))
        typo_count = cursor.fetchone()[0]

        # Send the message
        chat_logger.info(f"{target_user} has made a new typo in chat, their count is now at {typo_count}.")
        await ctx.send(f"Congratulations {target_user}, you've made a typo! You've made a typo in chat {typo_count} times.")
    
    @commands.command(name='typos', aliases=('typocount',))
    async def typos_command(self, ctx, *, mentioned_username: str = None):
        chat_logger.info("Typos Command ran.")
        # Check if the broadcaster is running the command
        if ctx.author.name.lower() == CHANNEL_NAME.lower():
            await ctx.send(f"Dear Streamer, you can never have a typo in your own channel.")
            return

        # Determine the target user: mentioned user or the command caller
        mentioned_username_lower = mentioned_username.lower() if mentioned_username else ctx.author.name.lower()
        target_user = mentioned_username_lower.lstrip('@')

        # Retrieve the typo count
        cursor.execute('SELECT typo_count FROM user_typos WHERE username = ?', (target_user,))
        result = cursor.fetchone()
        typo_count = result[0] if result else 0

        # Send the message
        chat_logger.info(f"{target_user} has made {typo_count} typos in chat.")
        await ctx.send(f"{target_user} has made {typo_count} typos in chat.")

    @commands.command(name='edittypos', aliases=('edittypo',))
    async def edit_typo_command(self, ctx, mentioned_username: str = None, new_count: int = None):
        if is_mod_or_broadcaster(ctx.author):
            chat_logger.info("Edit Typos Command ran.")
            try:
                # Determine the target user: mentioned user or the command caller
                mentioned_username_lower = mentioned_username.lower() if mentioned_username else ctx.author.name.lower()
                target_user = mentioned_username_lower.lstrip('@')
                chat_logger.info(f"Edit Typos Command ran with params: {target_user}, {new_count}")
    
                # Check if mentioned_username is not provided
                if mentioned_username is None:
                    chat_logger.error("There was no mentioned username for the command to run.")
                    await ctx.send("Usage: !edittypos @username [amount]")
                    return

                # Check if new_count is not provided
                if new_count is None:
                    chat_logger.error("There was no count added to the command to edit.")
                    await ctx.send(f"Usage: !edittypos @{target_user} [amount]")
                    return

                # Check if new_count is non-negative
                if new_count is not None and new_count < 0:
                    chat_logger.error(f"Typo count for {target_user} tried to be {new_count}.")
                    await ctx.send(f"Typo count cannot be negative.")
                    return

                # Check if the user exists in the database
                cursor.execute('SELECT typo_count FROM user_typos WHERE username = ?', (target_user,))
                result = cursor.fetchone()
    
                if result is not None:
                    # Update typo count in the database
                    cursor.execute('UPDATE user_typos SET typo_count = ? WHERE username = ?', (new_count, target_user))
                    conn.commit()
                    chat_logger.info(f"Typo count for {target_user} has been updated to {new_count}.")
                    await ctx.send(f"Typo count for {target_user} has been updated to {new_count}.")
                else:
                    # If user does not exist, send an error message and add the user with the given typo count
                    await ctx.send(f"No record for {target_user}. Adding them with the typo count.")
                    cursor.execute('INSERT INTO user_typos (username, typo_count) VALUES (?, ?)', (target_user, new_count))
                    conn.commit()
                    chat_logger.info(f"Typo count for {target_user} has been set to {new_count}.")
                    await ctx.send(f"Typo count for {target_user} has been set to {new_count}.")
            except Exception as e:
                chat_logger.error(f"Error in edit_typo_command: {e}")
                await ctx.send(f"An error occurred while trying to edit typos. {e}")
        else:
            await ctx.send(f"You must be a moderator or the broadcaster to use this command.")

    @commands.command(name='removetypos', aliases=('removetypo',))
    async def remove_typos_command(self, ctx, mentioned_username: str = None, decrease_amount: int = 1):
        chat_logger.info("Remove Typos Command ran.")
        try:
            if is_mod_or_broadcaster(ctx.author):
                # Ensure a username is mentioned
                if not mentioned_username is None:
                    chat_logger.error("Command missing username parameter.")
                    await ctx.send(f"Usage: !remotetypos @username")
                    return
            
                # Determine the target user: mentioned user or the command caller
                mentioned_username_lower = mentioned_username.lower() if mentioned_username else ctx.author.name.lower()
                target_user = mentioned_username_lower.lstrip('@')
                chat_logger.info(f"Remove Typos Command ran with params")
                
                # Validate decrease_amount is non-negative
                if decrease_amount < 0:
                    chat_logger.error(f"Typo count for {target_user} tried to be {new_count}.")
                    await ctx.send(f"Remove amount cannot be negative.")
                    return

                # Check if the user exists in the database
                cursor.execute('SELECT typo_count FROM user_typos WHERE username = ?', (target_user,))
                result = cursor.fetchone()

                if result:
                    current_count = result[0]
                    new_count = max(0, current_count - decrease_amount)  # Ensure count doesn't go below 0
                    cursor.execute('UPDATE user_typos SET typo_count = ? WHERE username = ?', (new_count, target_user))
                    conn.commit()
                    await ctx.send(f"Typo count for {target_user} decreased by {decrease_amount}. New count: {new_count}.")
                else:
                    await ctx.send(f"No typo record found for {target_user}.")
            else:
                await ctx.send(f"You must be a moderator or the broadcaster to use this command.")
        except Exception as e:
            chat_logger.error(f"Error in remove_typos_command: {e}")
            await ctx.send(f"An error occurred while trying to remove typos.")

    @commands.command(name='deaths')
    async def deaths_command(self, ctx):
        try:
            global current_game
            chat_logger.info("Deaths command ran.")

            # Retrieve the game-specific death count
            cursor.execute('SELECT death_count FROM game_deaths WHERE game_name = ?', (current_game,))
            game_death_count_result = cursor.fetchone()
            game_death_count = game_death_count_result[0] if game_death_count_result else 0

            # Retrieve the total death count
            cursor.execute('SELECT death_count FROM total_deaths')
            total_death_count_result = cursor.fetchone()
            total_death_count = total_death_count_result[0] if total_death_count_result else 0

            chat_logger.info(f"{ctx.author} has reviewed the death count for {current_game}. Total deaths are: {total_death_count}")
            await ctx.send(f"We have died {game_death_count} times in {current_game}, with a total of {total_death_count} deaths in all games.")
        except Exception as e:
            await ctx.send(f"An error occurred while executing the command. {e}")
            chat_logger.error(f"Error in deaths_command: {e}")

    @commands.command(name='deathadd', aliases=['death+',])
    async def deathadd_command(self, ctx):
        if is_mod_or_broadcaster(ctx.author):
            global current_game
            try:
                chat_logger.info("Death Add Command ran.")

                # Ensuring connection and cursor are correctly used 
                global conn, cursor

                # Ensure there is exactly one row in total_deaths
                cursor.execute("SELECT COUNT(*) FROM total_deaths")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("INSERT INTO total_deaths (death_count) VALUES (0)")
                    conn.commit()

                # Increment game-specific death count & total death count
                cursor.execute('INSERT INTO game_deaths (game_name, death_count) VALUES (?, 1) ON CONFLICT(game_name) DO UPDATE SET death_count = death_count + 1 WHERE game_name = ?', (current_game, current_game))
                cursor.execute('UPDATE total_deaths SET death_count = death_count + 1')
                conn.commit()

                # Retrieve updated counts
                cursor.execute('SELECT death_count FROM game_deaths WHERE game_name = ?', (current_game,))
                game_death_count_result = cursor.fetchone()
                game_death_count = game_death_count_result[0] if game_death_count_result else 0

                cursor.execute('SELECT death_count FROM total_deaths')
                total_death_count_result = cursor.fetchone()
                total_death_count = total_death_count_result[0] if total_death_count_result else 0

                chat_logger.info(f"{current_game} now has {game_death_count} deaths.")
                chat_logger.info(f"Total Death count has been updated to: {total_death_count}")
                await ctx.send(f"We have died {game_death_count} times in {current_game}, with a total of {total_death_count} deaths in all games.")
            except Exception as e:
                await ctx.send(f"An error occurred while executing the command. {e}")
                chat_logger.error(f"Error in deathadd_command: {e}")
        else:
            chat_logger.info(f"{ctx.author} tried to use the command, death add, but couldn't has they are not a moderator.")
            await ctx.send("You must be a moderator or the broadcaster to use this command.")

    @commands.command(name='deathremove', aliases=['death-',])
    async def deathremove_command(self, ctx):
        if is_mod_or_broadcaster(ctx.author):
            global current_game
            try:
                chat_logger.info("Death Remove Command Ran")

                # Decrement game-specific death count & total death count (ensure it doesn't go below 0)
                cursor.execute('UPDATE game_deaths SET death_count = CASE WHEN death_count > 0 THEN death_count - 1 ELSE 0 END WHERE game_name = ?', (current_game,))
                cursor.execute('UPDATE total_deaths SET death_count = CASE WHEN death_count > 0 THEN death_count - 1 ELSE 0 END')
                conn.commit()

                # Retrieve updated counts
                cursor.execute('SELECT death_count FROM game_deaths WHERE game_name = ?', (current_game,))
                game_death_count_result = cursor.fetchone()
                game_death_count = game_death_count_result[0] if game_death_count_result else 0

                cursor.execute('SELECT death_count FROM total_deaths')
                total_death_count_result = cursor.fetchone()
                total_death_count = total_death_count_result[0] if total_death_count_result else 0

                # Send the message
                chat_logger.info(f"{current_game} death has been removed, we now have {game_death_count} deaths.")
                chat_logger.info(f"Total Death count has been updated to: {total_death_count} to reflect the removal.")
                await ctx.send(f"Death removed from {current_game}, count is now {game_death_count}. Total deaths in all games: {total_death_count}.")
            except Exception as e:
                await ctx.send(f"An error occurred while executing the command. {e}")
                chat_logger.error(f"Error in deaths_command: {e}")
        else:
            chat_logger.info(f"{ctx.author} tried to use the command, death remove, but couldn't has they are not a moderator.")
            await ctx.send("You must be a moderator or the broadcaster to use this command.")
    
    @commands.command(name='game')
    async def game_command(self, ctx):
        global current_game
        chat_logger.info("Game Command has been ran.")

        if current_game is not None:
            await ctx.send(f"The current game we're playing is: {current_game}")
        else:
            await ctx.send("We're not currently streaming any specific game category.")

    @commands.command(name='followage')
    async def followage_command(self, ctx, *, mentioned_username: str = None):
        chat_logger.info("Follow Age Command ran.")
        target_user = mentioned_username.lstrip('@') if mentioned_username else ctx.author.name
        headers = {
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {CHANNEL_AUTH}'
        }
        if mentioned_username:
            user_info = await self.fetch_users(names=[target_user])
            if user_info:
                mentioned_user_id = user_info[0].id
                params = {
                    'user_id': CHANNEL_ID,
                    'broadcaster_id': mentioned_user_id
                }
        else:
            params = {
                'user_id': CHANNEL_ID,
                'broadcaster_id': ctx.author.id
            }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.twitch.tv/helix/channels/followed', headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        followage_text = None

                        # Iterate over followed channels to find the target user
                        for followed_channel in data['data']:
                            if followed_channel['broadcaster_login'] == target_user.lower():
                                followed_at_str = followed_channel['followed_at']
                                followed_at = datetime.fromisoformat(followed_at_str.replace('Z', '+00:00'))
                                followed_at = followed_at.replace(tzinfo=timezone.utc)
                                followage = datetime.now(timezone.utc) - followed_at
                                years = followage.days // 365
                                remaining_days = followage.days % 365
                                months = remaining_days // 30
                                remaining_days %= 30
                                days = remaining_days

                                if years > 0:
                                    years_text = f"{years} {'year' if years == 1 else 'years'}"
                                else:
                                    years_text = ""

                                if months > 0:
                                    months_text = f"{months} {'month' if months == 1 else 'months'}"
                                else:
                                    months_text = ""

                                if days > 0:
                                    days_text = f"{days} {'day' if days == 1 else 'days'}"
                                else:
                                    days_text = ""

                                # Join the non-empty parts with commas
                                parts = [part for part in [years_text, months_text, days_text] if part]
                                followage_text = ", ".join(parts)
                                break

                        if followage_text:
                            await ctx.send(f"{target_user} has been following for: {followage_text}.")
                            chat_logger.info(f"{target_user} has been following for: {followage_text}.")
                        else:
                            await ctx.send(f"{target_user} does not follow {CHANNEL_NAME}.")
                            chat_logger.info(f"{target_user} does not follow {CHANNEL_NAME}.")
                    else:
                        await ctx.send(f"Failed to retrieve followage information for {target_user}.")
                        chat_logger.info(f"Failed to retrieve followage information for {target_user}.")
        except Exception as e:
            chat_logger.error(f"Error retrieving followage: {e}")
            await ctx.send(f"Oops, something went wrong while trying to check followage.")

    @commands.command(name='schedule')
    async def schedule_command(self, ctx):
        utc_now = datetime.now(timezone.utc)
        headers = {
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {CHANNEL_AUTH}'
        }
        params = {
            'broadcaster_id': CHANNEL_ID,
            'first': '2'
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.twitch.tv/helix/schedule', headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        segments = data['data']['segments']

                        next_stream = None
                        for segment in segments:
                            start_time = datetime.fromisoformat(segment['start_time'][:-1]).replace(tzinfo=timezone.utc)
                            if start_time > utc_now:
                                next_stream = segment
                                break  # Exit the loop after finding the first upcoming stream

                        if next_stream:
                            start_date = next_stream['start_time'].split('T')[0]  # Extract date from start_time
                            time_until = start_time - utc_now

                            # Format time_until
                            days, seconds = time_until.days, time_until.seconds
                            hours = seconds // 3600
                            minutes = (seconds % 3600) // 60
                            seconds = (seconds % 60)

                            time_str = f"{days} days, {hours} hours, {minutes} minutes, {seconds} seconds" if days else f"{hours} hours, {minutes} minutes, {seconds} seconds"

                            await ctx.send(f"The next stream will be on {start_date} which is in {time_str}. Check out the full schedule here: https://www.twitch.tv/{CHANNEL_NAME}/schedule")
                        else:
                            await ctx.send(f"There are no upcoming streams in the next two days.")
                    else:
                        await ctx.send(f"Something went wrong while trying to get the schedule from Twitch.")
        except Exception as e:
            chat_logger.error(f"Error retrieving schedule: {e}")
            await ctx.send(f"Oops, something went wrong while trying to check the schedule.")

    @commands.command(name='checkupdate')
    async def check_update_command(self, ctx):
        if is_mod_or_broadcaster(ctx.author):
            REMOTE_VERSION_URL = "https://api.botofthespecter.com/bot_version_control.txt"
            response = requests.get(REMOTE_VERSION_URL)
            remote_version = response.text.strip()

            if remote_version != VERSION:
                if len(remote_version) == len(VERSION) + 1:
                    message = f"A new hotfix update (V{remote_version}) is available. Please head over to the website and restart the bot. You are currently running V{VERSION}."
                else:
                    message = f"A new update (V{remote_version}) is available. Please head over to the website and restart the bot. You are currently running V{VERSION}."
                bot_logger.info(f"Bot update available. (V{remote_version})")
                await ctx.send(f"{message}")
            else:
                message = f"There is no update pending. You are currently running V{VERSION}."
                bot_logger.info(f"{message}")
                await ctx.send(f"{message}")
        else:
            chat_logger.info(f"{ctx.author} tried to use the command, !checkupdate, but couldn't as they are not a moderator.")
            await ctx.send("You must be a moderator or the broadcaster to use this command.")
    
    @commands.command(name='so', aliases=('shoutout',))
    async def shoutout_command(self, ctx, user_to_shoutout: str = None):
        chat_logger.info(f"Shoutout command attempting to run.")
        if is_mod_or_broadcaster(ctx.author):
            chat_logger.info(f"Shoutout command running from {ctx.author}")
            if user_to_shoutout is None:
                chat_logger.error(f"Shoutout command missing username parameter.")
                await ctx.send(f"Usage: !so @username")
                return
            try:
                chat_logger.info(f"Shoutout command trying to run.")
                # Remove @ from the username if present
                user_to_shoutout = user_to_shoutout.lstrip('@')

                # Check if the user exists on Twitch
                if not await is_valid_twitch_user(user_to_shoutout):
                    chat_logger.error(f"User {user_to_shoutout} does not exist on Twitch. Failed to give shoutout")
                    await ctx.send(f"The user @{user_to_shoutout} does not exist on Twitch.")
                    return

                chat_logger.info(f"Shoutout for {user_to_shoutout} ran by {ctx.author.name}")
                user_info = await self.fetch_users(names=[user_to_shoutout])
                mentioned_user_id = user_info[0].id
                game = await get_latest_stream_game(mentioned_user_id, user_to_shoutout)

                if not game:
                    shoutout_message = (
                        f"Hey, huge shoutout to @{user_to_shoutout}! "
                        f"You should go give them a follow over at "
                        f"https://www.twitch.tv/{user_to_shoutout}"
                    )
                    chat_logger.info(shoutout_message)
                    await ctx.send(shoutout_message)
                else:
                    shoutout_message = (
                        f"Hey, huge shoutout to @{user_to_shoutout}! "
                        f"You should go give them a follow over at "
                        f"https://www.twitch.tv/{user_to_shoutout} where they were playing: {game}"
                    )
                    chat_logger.info(shoutout_message)
                    await ctx.send(shoutout_message)

                # Trigger the Twitch shoutout
                await trigger_twitch_shoutout(user_to_shoutout, mentioned_user_id)

            except Exception as e:
                chat_logger.error(f"Error in shoutout_command: {e}")
        else:
            chat_logger.info(f"{ctx.author} tried to use the command, !shoutout, but couldn't as they are not a moderator.")
            await ctx.send("You must be a moderator or the broadcaster to use this command.")

    @commands.command(name='addcommand')
    async def add_command_command(self, ctx):
        chat_logger.info("Add Command ran.")
        # Check if the user is a moderator or the broadcaster
        if is_mod_or_broadcaster(ctx.author):
            # Parse the command and response from the message
            try:
                command, response = ctx.message.content.strip().split(' ', 1)[1].split(' ', 1)
            except ValueError:
                await ctx.send(f"Invalid command format. Use: !addcommand [command] [response]")
                return

            # Insert the command and response into the database
            cursor.execute('INSERT OR REPLACE INTO custom_commands (command, response) VALUES (?, ?)', (command, response))
            conn.commit()
            chat_logger.info(f"{ctx.author} has added the command !{command} with the response: {response}")
            await ctx.send(f'Custom command added: !{command}')
        else:
            await ctx.send(f"You must be a moderator or the broadcaster to use this command.")

    @commands.command(name='removecommand')
    async def remove_command_command(self, ctx):
        chat_logger.info("Remove Command ran.")
        # Check if the user is a moderator or the broadcaster
        if is_mod_or_broadcaster(ctx.author):
            try:
                command = ctx.message.content.strip().split(' ')[1]
            except IndexError:
                await ctx.send(f"Invalid command format. Use: !removecommand [command]")
                return

            # Delete the command from the database
            cursor.execute('DELETE FROM custom_commands WHERE command = ?', (command,))
            conn.commit()
            chat_logger.info(f"{ctx.author} has removed {command}")
            await ctx.send(f'Custom command removed: !{command}')
        else:
            await ctx.send(f"You must be a moderator or the broadcaster to use this command.")

# Functions for all the commands
##
# Function  to check if the user is a real user on Twitch
async def is_valid_twitch_user(user_to_shoutout):
    # Twitch API endpoint to check if a user exists
    url = f"https://api.twitch.tv/helix/users?login={user_to_shoutout}"

    # Headers including the Twitch Client ID
    headers = {
        "Client-ID": TWITCH_API_CLIENT_ID,
        "Authorization": f"Bearer {CHANNEL_AUTH}"
    }

    # Send a GET request to the Twitch API
    response = requests.get(url, headers=headers)

    # Check if the response is successful and if the user exists
    if response.status_code == 200:
        data = response.json()
        if data['data']:
            return True  # User exists
        else:
            return False  # User does not exist
    else:
        # If there's an error with the request or response, return False
        return False

# Function to get the diplay name of the user from their user id
async def get_display_name(user_id):
    # Replace with actual method to get display name from Twitch API
    url = f"https://api.twitch.tv/helix/users?id={user_id}"
    headers = {
        "Client-ID": TWITCH_API_CLIENT_ID,
        "Authorization": f"Bearer {CHANNEL_AUTH}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data['data'][0]['display_name'] if data['data'] else None
            else:
                return None

# Function to check if the user running the task is a mod to the channel or the channel broadcaster.
def is_mod_or_broadcaster(user):
    # Check if the user is the bot owner
    if user.name == 'gfaundead':
        twitch_logger.info(f"User is gfaUnDead. (Bot owner)")
        return True

    # Check if the user is the broadcaster
    elif user.name == CHANNEL_NAME:
        twitch_logger.info(f"User {user.name} is the broadcaster.")
        return True

    # Check if the user is a moderator
    elif is_user_mod(user):
        twitch_logger.info(f"User {user.name} is a moderator.")
        return True

    # If none of the above, the user is neither the bot owner, broadcaster, nor a moderator
    else:
        twitch_logger.info(f"User {user.name} does not have required permissions.")
        return False

# Function to check if a user is a MOD of the channel using the Twitch API
def is_user_mod(user):
    # Send request to Twitch API to check if user is a moderator
    headers = {
        "Authorization": f"Bearer {CHANNEL_AUTH}",
        "Client-ID": TWITCH_API_CLIENT_ID,
    }
    params = {
        "broadcaster_id": f"{CHANNEL_ID}",
        "user_name": user.name
    }

    response = requests.get("https://api.twitch.tv/helix/moderation/moderators", headers=headers, params=params)
    if response.status_code == 200:
        moderators = response.json().get("data", [])
        for mod in moderators:
            if mod["user_name"].lower() == user.name.lower():
                twitch_logger.info(f"User {user.name} is a Moderator")
                return True
            return False
    return False

# Function to check if a user is a VIP of the channel using the Twitch API
def is_user_vip(user_trigger_id):
    headers = {
        'Client-ID': TWITCH_API_CLIENT_ID,
        'Authorization': f'Bearer {CHANNEL_AUTH}',
    }
    params = {
        'broadcaster_id': CHANNEL_ID
    }
    try:
        response = requests.get('https://api.twitch.tv/helix/channels/vips', headers=headers, params=params)
        if response.status_code == 200:
            vips = response.json().get("data", [])
            for vip in vips:
                if vip["user_id"] == user_trigger_id:
                    user_name = vip["user_name"]
                    twitch_logger.info(f"User {user_name} is a VIP Member")
                    return True
            return False
    except requests.RequestException as e:
        print(f"Failed to retrieve VIP status: {e}")
    return False

# Function to check if a user is a subscriber of the channel
def is_user_subscribed(user_id):
    headers = {
        "Client-ID": TWITCH_API_CLIENT_ID,
        "Authorization": f"Bearer {CHANNEL_AUTH}"
    }
    params = {
        "broadcaster_id": CHANNEL_ID,
        "user_id": user_id
    }
    tier_mapping = {
        "1000": "Tier 1",
        "2000": "Tier 2",
        "3000": "Tier 3"
    }
    subscription_response = requests.get('https://api.twitch.tv/helix/subscriptions', headers=headers, params=params)
    if subscription_response.status_code == 200:
        subscription_data = subscription_response.json()
        subscriptions = subscription_data.get('data', [])
        if subscriptions:
            # Iterate over each subscription
            for subscription in subscriptions:
                tier = subscription['tier']
                tier_name = tier_mapping.get(tier, tier)
                return tier_name
    return None

# Function to check if a user is a MOD of the channel using the Twitch API
def is_user_moderator(user_trigger_id):
    # Send request to Twitch API to check if user is a moderator
    headers = {
        "Authorization": f"Bearer {CHANNEL_AUTH}",
        "Client-ID": TWITCH_API_CLIENT_ID,
    }
    params = {
        "broadcaster_id": f"{CHANNEL_ID}",
        "user_id": user_trigger_id
    }

    response = requests.get("https://api.twitch.tv/helix/moderation/moderators", headers=headers, params=params)
    if response.status_code == 200:
        moderators = response.json().get("data", [])
        for mod in moderators:
            if mod["user_id"] == user_trigger_id:
                user_name = mod["user_name"]
                twitch_logger.info(f"User {user_name} is a Moderator")
                return True
            return False
    return False

# Function to add user to the table of known users
async def user_is_seen(username):
    try:
        cursor.execute('INSERT INTO seen_users (username) VALUES (?)', (username,))
        conn.commit()
    except Exception as e:
        bot_logger.error(f"Error occurred while adding user '{username}' to seen_users table: {e}")

# Function to fetch custom API responses
def fetch_api_response(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        else:
            return f"Status Error: {response.status_code}"
    except Exception as e:
        return f"Exception Error: {str(e)}"

# Function to update custom counts
def update_custom_count(command):
    cursor.execute('SELECT count FROM custom_counts WHERE command = ?', (command,))
    result = cursor.fetchone()
    if result:
        current_count = result[0]
        new_count = current_count + 1
        cursor.execute('UPDATE custom_counts SET count = ? WHERE command = ?', (new_count, command))
    else:
        cursor.execute('INSERT INTO custom_counts (command, count) VALUES (?, ?)', (command, 1))
    conn.commit()

def get_custom_count(command):
    cursor.execute('SELECT count FROM custom_counts WHERE command = ?', (command,))
    result = cursor.fetchone()
    if result:
        return result[0]
    else:
        return 0

# Functions for weather
def get_streamer_weather():
    cursor.execute("SELECT weather_location FROM profile")
    info = cursor.fetchone()
    location = info[0]
    chat_logger.info(f"Got {location} weather info.")
    return location

def getWindDirection(deg):
    cardinalDirections = {
        'N': (337.5, 22.5),
        'NE': (22.5, 67.5),
        'E': (67.5, 112.5),
        'SE': (112.5, 157.5),
        'S': (157.5, 202.5),
        'SW': (202.5, 247.5),
        'W': (247.5, 292.5),
        'NW': (292.5, 337.5)
    }
    for direction, (start, end) in cardinalDirections.items():
        if deg >= start and deg < end:
            return direction
    return 'N/A'

def get_weather(location):
    owm = pyowm.OWM(WEATHER_API)
    try:
        observation = owm.weather_manager().weather_at_place(location)
        weather = observation.weather
        status = weather.detailed_status
        temperature = weather.temperature('celsius')['temp']
        temperature_f = round(temperature * 9 / 5 + 32, 1)
        wind_speed = round(weather.wind()['speed'])
        wind_speed_mph = round(wind_speed / 1.6, 2)
        humidity = weather.humidity
        wind_direction = getWindDirection(weather.wind()['deg'])

        return f"The weather in {location} is {status} with a temperature of {temperature}°C ({temperature_f}°F). Wind is blowing from the {wind_direction} at {wind_speed}kph ({wind_speed_mph}mph) and the humidity is {humidity}%."
    except pyowm.exceptions.NotFoundError:
        return f"Location '{location}' not found."
    except AttributeError:
        return f"An error occurred while processing the weather data for '{location}'."

# Function to trigger updating stream title or game
class GameNotFoundException(Exception):
    pass
class GameUpdateFailedException(Exception):
    pass

async def trigger_twitch_title_update(new_title):
    # Twitch API
    url = "https://api.twitch.tv/helix/channels"
    headers = {
        "Authorization": f"Bearer {CHANNEL_AUTH}",
        "Client-ID": TWITCH_API_CLIENT_ID,
    }
    params = {
        "broadcaster_id": CHANNEL_ID,
        "title": new_title
    }
    response = requests.patch(url, headers=headers, json=params)
    if response.status_code == 200:
        twitch_logger.info(f'Stream title updated to: {new_title}')
    else:
        twitch_logger.error(f'Failed to update stream title: {response.text}')

async def trigger_twitch_game_update(new_game_id):
    # Twitch API
    url = "https://api.twitch.tv/helix/channels"
    headers = {
        "Authorization": f"Bearer {CHANNEL_AUTH}",
        "Client-ID": TWITCH_API_CLIENT_ID,
    }
    params = {
        "broadcaster_id": CHANNEL_ID,
        "game_id": new_game_id
    }
    response = requests.patch(url, headers=headers, json=params)
    if response.status_code == 200:
        twitch_logger.info(f'Stream game updated to: {new_game_id}')
    else:
        twitch_logger.error(f'Failed to update stream game: {response.text}')
        raise GameUpdateFailedException(f'Failed to update stream game')

async def get_game_id(game_name):
    # Twitch API
    url = "https://api.twitch.tv/helix/games/top"
    headers = {
        "Authorization": f"Bearer {CHANNEL_AUTH}",
        "Client-ID": TWITCH_API_CLIENT_ID,
    }
    params = {
        "name": game_name
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        if data and 'data' in data and len(data['data']) > 0:
            return data['data'][0]['id']
    twitch_logger.error(f"Game '{game_name}' not found.")
    raise GameNotFoundException(f"Game '{game_name}' not found.")

# Function to trigger a twitch shoutout via Twitch API
async def trigger_twitch_shoutout(user_to_shoutout, mentioned_user_id):
    # Add the shoutout request to the queue
    shoutout_queue.put((user_to_shoutout, mentioned_user_id))

    # Check if the queue is empty and no shoutout is currently being processed
    if shoutout_queue.qsize() == 1:
        await process_shoutouts()

async def get_latest_stream_game(broadcaster_id, user_to_shoutout):
    headers = {
        'Client-ID': CLIENT_ID,
        'Authorization': f'Bearer {CHANNEL_AUTH}'
    }
    params = {
        'broadcaster_id': broadcaster_id
    }
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.twitch.tv/helix/channels', headers=headers, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("data"):
                    game_name = data["data"][0].get("game_name")
                    if game_name:
                        twitch_logger.info(f"Got game for {user_to_shoutout}: {game_name}.")
                        return game_name
                    else:
                        api_logger.error(f"Game name not found in Twitch API response for {user_to_shoutout}.")
                        return None
                else:
                    api_logger.error(f"Empty response data from Twitch API for {user_to_shoutout}.")
                    return None
            else:
                api_logger.error(f"Failed to get game for {user_to_shoutout}. Status code: {response.status}")
                return None

async def process_shoutouts():
    while not shoutout_queue.empty():
        user_to_shoutout, mentioned_user_id = shoutout_queue.get()
        twitch_logger.info(f"Processing Shoutout via Twitch for {user_to_shoutout}={mentioned_user_id}")
        url = 'https://api.twitch.tv/helix/chat/shoutouts'
        headers = {
            "Authorization": f"Bearer {CHANNEL_AUTH}",
            "Client-ID": TWITCH_API_CLIENT_ID,
        }
        payload = {
            "from_broadcaster_id": CHANNEL_ID,
            "to_broadcaster_id": mentioned_user_id,
            "moderator_id": CHANNEL_ID
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 429:
                        # Rate limit exceeded, wait for cooldown period (3 minutes) before retrying
                        retry_after = 180  # 3 minutes in seconds
                        twitch_logger.warning(f"Rate limit exceeded. Retrying after {retry_after} seconds.")
                        await asyncio.sleep(retry_after)
                        continue  # Retry the request
                    elif response.status in (200, 204):
                        twitch_logger.info(f"Shoutout triggered successfully for {user_to_shoutout}.")
                        await asyncio.sleep(180)  # Wait for 3 minutes before processing the next shoutout
                    else:
                        twitch_logger.error(f"Failed to trigger shoutout. Status: {response.status}. Message: {await response.text()}")
                        # Retry the request (exponential backoff can be implemented here)
                        await asyncio.sleep(5)  # Wait for 5 seconds before retrying
                        continue
                    shoutout_queue.task_done()
        except aiohttp.ClientError as e:
            twitch_logger.error(f"Error triggering shoutout: {e}")
            # Retry the request (exponential backoff can be implemented here)
            await asyncio.sleep(5)  # Wait for 5 seconds before retrying
            continue

# Function to process JSON requests
async def fetch_json(url, headers=None):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    if "json" in response.headers.get("Content-Type", ""):
                        return await response.json()
                    else:
                        return await response.text()
    except Exception as e:
        api_logger.error(f"Error fetching data: {e}")
    return None

# Function for checking updates
async def check_auto_update():
    while True:
        REMOTE_VERSION_URL = "https://api.botofthespecter.com/bot_version_control.txt"
        async with aiohttp.ClientSession() as session:
            async with session.get(REMOTE_VERSION_URL) as response:
                if response.status == 200:
                    remote_version = await response.text()
                    remote_version = remote_version.strip()
                    if remote_version != VERSION:
                        if len(remote_version) == len(VERSION) + 1:
                            message = f"A new hotfix update (V{remote_version}) is available. Please head over to the website and restart the bot. You are currently running V{VERSION}."
                        else:
                            message = f"A new update (V{remote_version}) is available. Please head over to the website and restart the bot. You are currently running V{VERSION}."
                        bot_logger.info(message)
                        channel = bot.get_channel(CHANNEL_NAME)
                        if channel:
                            await channel.send(message)
        await asyncio.sleep(1800)

# Function to check if the stream is online
async def check_stream_online():
    global stream_online
    global current_game
    stream_online = False
    stream_state = False
    offline_logged = False
    time_now = time.time()

    while True:
        async with aiohttp.ClientSession() as session:
            headers = {
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {CHANNEL_AUTH}'
            }
            params = {
                'user_login': CHANNEL_NAME,
                'type': 'live'
            }
            async with session.get('https://api.twitch.tv/helix/streams', headers=headers, params=params) as response:
                data = await response.json()

                # Check if the stream is offline
                if not data.get('data'):
                    stream_online = False
                    current_game = None
                    # twitch_logger.info(f"API returned no data.")
                else:
                    # Stream is online, extract the game name
                    stream_online = True
                    game = data['data'][0].get('game_name', None)
                    uptime_str = data['data'][0].get('started_at', None)
                    uptime = datetime.strptime(uptime_str, "%Y-%m-%dT%H:%M:%SZ")
                    current_game = game
                    # twitch_logger.info(f"API Found Live Data, processing.")

                # Stream state change
                if stream_online != stream_state:
                    if stream_online:
                        twitch_logger.info(f"Stream is now online.")
                        streaming_for = time_now - uptime.timestamp()
                        if current_game:
                            message = f"Stream is now online! Streaming {current_game}"
                            if streaming_for < 300: # Only send a message if steram uptime is less than 5 minutes
                                await send_online_message(message)
                            else:
                                twitch_logger.info(f"Online message not sent to chat as the uptime is more than 5 mintues.")
                        else:
                            message = "Stream is now online!"
                            if streaming_for < 300: # Only send a message if steram uptime is less than 5 minutes
                                await send_online_message(message)
                            else:
                                twitch_logger.info(f"Online message not sent to chat as the uptime is more than 5 mintues.")
                    else:
                        if not offline_logged:
                            bot_logger.info(f"Stream is now offline.")
                            twitch_logger.info(f"Stream is now offline.")
                            await clear_seen_today()
                            offline_logged = True
                    stream_state = stream_online
                elif stream_online:
                    offline_logged = False

        await asyncio.sleep(60)  # Check every 1 minute

async def send_online_message(message):
    await asyncio.sleep(3)
    channel = bot.get_channel(CHANNEL_NAME)
    if channel:
        bot_logger.info(f"Attempted to send message: {message}")
        await channel.send(message)
    else:
        bot_logger.error("Failed to send message")

async def clear_seen_today():
    cursor.execute('DELETE FROM seen_today')
    conn.commit()

# Funciont for timmed messages
async def send_timed_message(message, interval):
    try:
        await sleep(interval)
        if stream_online:
            channel = bot.get_channel(CHANNEL_NAME)
            await channel.send(message)
    except asyncio.CancelledError:
        pass
    await sleep(interval)

async def timed_message():
    global stream_online
    while True:
        if stream_online:
            cursor.execute('SELECT interval, message FROM timed_messages')
            messages = cursor.fetchall()
            for message, interval in messages:
                time_now = datetime.now()
                send_time = time_now + timedelta(minutes=int(interval))
                wait_time = (send_time - time_now).total_seconds()
                task = create_task(send_timed_message(message, wait_time))
                scheduled_tasks.append(task)  # Keep track of the task
        else:
            # Cancel all scheduled tasks if the stream goes offline
            for task in scheduled_tasks:
                task.cancel()
            scheduled_tasks.clear()  # Clear the list of tasks

        await sleep(300)

# Function to get the current playing song
async def get_song_info_command():
    try:
        song_info = await get_song_info()
        if "error" in song_info:
            error_message = song_info["error"]
            chat_logger.error(f"Error: {error_message}")
            return error_message
        else:
            artist = song_info.get('artist', '')
            song = song_info.get('song', '')
            message = f"The current song is: {song} by {artist}"
            chat_logger.info(message)
            return message
    except Exception as e:
        api_logger.error(f"An error occurred while getting song info: {e}")
        return "Error: Failed to get song information."

async def get_song_info():
    try:
        # Test validity of GQL OAuth token
        if not await twitch_gql_token_valid():
            return {"error": "Twitch GQL Token Expired"}

        # Record stream audio
        random_file_name = str(random.randint(10000000, 99999999))
        working_dir = "/var/www/logs/songs"
        stream_recording_file = os.path.join(working_dir, f"{random_file_name}.acc")
        raw_recording_file = os.path.join(working_dir, f"{random_file_name}.raw")
        outfile = os.path.join(working_dir, f"{random_file_name}.acc")
        if not await record_stream(outfile):
            return {"error": "Stream is not available"}

        # Convert Stream Audio into Raw Format for Shazam
        if not await convert_to_raw_audio(stream_recording_file, raw_recording_file):
            return {"error": "Error converting stream audio from ACC to raw PCM s16le"}

        # Encode raw audio to base64
        with open(raw_recording_file, "rb") as song:
            songBytes = song.read()
            songb64 = base64.b64encode(songBytes)

            # Detect the song
            matches = await detect_song(songb64)

            if "track" in matches.keys():
                artist = matches["track"].get("subtitle", "")
                song_title = matches["track"].get("title", "")
                api_logger.info(f"Identified song: {song_title} by {artist}.")
                return {"artist": artist, "song": song_title}
            else:
                return {"error": "The current song can not be identified."}
    except Exception as e:
        api_logger.error(f"An error occurred while getting song info: {e}")
        return {"error": "Failed to get song information."}

async def twitch_gql_token_valid():
    try:
        url = "https://gql.twitch.tv/gql"
        headers = {
            "Client-Id": CLIENT_ID,
            "Content-Type": "text/plain",
            "Authorization": f"OAuth {TWITCH_GQL}"
        }
        data = [
            {
                "operationName": "SyncedSettingsEmoteAnimations",
                    "variables": {},
                    "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "64ac5d385b316fd889f8c46942a7c7463a1429452ef20ffc5d0cd23fcc4ecf30"
                    }
                }
            }
        ]
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=10) as response:
                # Log the status code received
                api_logger.info(f"Twitch GQL token validation response status code: {response.status}")

                if response.status == 200:
                    return True
                else:
                    api_logger.error(f"Twitch GQL token validation failed with status code: {response.status}")
                    return False
    except Exception as e:
        api_logger.error(f"An error occurred while checking Twitch GQL token validity: {e}")
        return False

async def detect_song(raw_audio_b64):
    try:
        url = "https://shazam.p.rapidapi.com/songs/v2/detect"
        querystring = {"timezone": "Australia/Sydney", "locale": "en-US"}
        headers = {
            "content-type": "text/plain",
            "X-RapidAPI-Key": SHAZAM_API,
            "X-RapidAPI-Host": "shazam.p.rapidapi.com"
        }
        # Convert base64 encoded audio to bytes
        audio_bytes = raw_audio_b64
        response = requests.post(url, data=audio_bytes, headers=headers, params=querystring, timeout=15)
        # Check requests remaining for the API
        if "x-ratelimit-requests-remaining" in response.headers:
            requests_left = response.headers['x-ratelimit-requests-remaining']
            api_logger.info(f"There are {requests_left} requests lefts for the song command.")
            if requests_left == 0:
                return {"error": "Sorry, no more requests for song info are available for the rest of the month. Requests reset each month on the 23rd."}
        return response.json()
    except Exception as e:
        api_logger.error(f"An error occurred while detecting song: {e}")
        return {}

async def convert_to_raw_audio(in_file, out_file):
    try:
        ffmpeg_path = "/usr/bin/ffmpeg"
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_path, '-i', in_file, "-vn", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", "-f", "s16le", out_file,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL)
        # Wait for the subprocess to finish
        returncode = await proc.wait()
        return returncode == 0
    except Exception as e:
        api_logger.error(f"An error occurred while converting audio: {e}")
        return False

async def record_stream(outfile):
    try:
        session = streamlink.Streamlink()
        session.set_option("http-headers", {"Authorization": f"OAuth {TWITCH_GQL}"})
        streams = session.streams(f"https://twitch.tv/{CHANNEL_NAME}")
        if len(streams) == 0 or "worst" not in streams.keys():
            return False
        stream_obj = streams["worst"]
        fd = stream_obj.open()
        chunk = 1024
        num_bytes = 0
        data = b''
        max_bytes = 200
        while num_bytes <= max_bytes * 1024:
            data += fd.read(chunk)
            num_bytes += chunk
        fd.close()
        with open(outfile, "wb") as file:
            file.write(data)
        return os.path.exists(outfile)
    except Exception as e:
        api_logger.error(f"An error occurred while recording stream: {e}")
        return False

# Function for BITS
async def process_bits_event(user_id, user_name, bits):
    # Connect to the database
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    # Check if the user exists in the database
    cursor.execute('SELECT bits FROM bits_data WHERE user_id = ? OR user_name = ?', (user_id, user_name))
    existing_bits = cursor.fetchone()

    if existing_bits:
        # Update the user's total bits count
        total_bits = existing_bits[0] + bits
        cursor.execute('''
            UPDATE bits_data
            SET bits = ?
            WHERE user_id = ? OR user_name = ?
        ''', (total_bits, user_id, user_name))
        
        # Send message to channel with total bits
        channel = bot.get_channel(CHANNEL_NAME)
        await channel.send(f"Thank you {user_name} for {bits} bits! You've given a total of {total_bits} bits.")
    else:
        # Insert a new record for the user
        cursor.execute('''
            INSERT INTO bits_data (user_id, user_name, bits)
            VALUES (?, ?, ?)
        ''', (user_id, user_name, bits))
        
        # Send message to channel without total bits
        channel = bot.get_channel(CHANNEL_NAME)
        await channel.send(f"Thank you {user_name} for {bits} bits!")

    conn.commit()
    conn.close()

# Function for SUBSCRIPTIONS
def sub_plan_to_tier_name(sub_plan):
    sub_plan = str(sub_plan).lower()
    if sub_plan == "prime":
        return "Prime"
    elif sub_plan == "1000":
        return "Tier 1"
    elif sub_plan == "2000":
        return "Tier 2"
    elif sub_plan == "3000":
        return "Tier 3"
    else:
        raise ValueError("Unknown subscription plan")

async def process_regular_subscription_event(user_id, user_name, sub_plan, event_months):
    # Connect to the database
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    # Check if the user exists in the database
    cursor.execute('SELECT sub_plan, months FROM subscription_data WHERE user_id = ?', (user_id,))
    existing_subscription = cursor.fetchone()

    if existing_subscription:
        # User exists in the database
        existing_sub_plan, db_months = existing_subscription
        if existing_sub_plan != sub_plan:
            # User upgraded their subscription plan
            cursor.execute('''
                UPDATE subscription_data
                SET sub_plan = ?, months = ?
                WHERE user_id = ?
            ''', (sub_plan, db_months, user_id))
        else:
            # User maintained the same subscription plan, update cumulative months
            cursor.execute('''
                UPDATE subscription_data
                SET months = ?
                WHERE user_id = ?
            ''', (db_months, user_id))
    else:
        # User does not exist in the database, insert new record
        cursor.execute('''
            INSERT INTO subscription_data (user_id, user_name, sub_plan, months)
            VALUES (?, ?, ?, ?)
        ''', (user_id, user_name, sub_plan, event_months))

    # Commit changes to the database
    conn.commit()
    conn.close()

    # Construct the message to be sent to the channel & send the message to the channel
    message = f"Thank you {user_name} for subscribing! You are now a {sub_plan} subscriber for {event_months} months!"
    
    # Send the message to the channel
    channel = bot.get_channel(CHANNEL_NAME)
    await channel.send(message)

async def process_subgift_event(recipient_user_id, recipient_user_name, sub_plan, months, user_name):
    # Connect to the database
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    # Check if the recipient user exists in the database
    cursor.execute('SELECT months FROM subscription_data WHERE user_id = ?', (recipient_user_id,))
    existing_months = cursor.fetchone()

    if existing_months:
        # Recipient user exists in the database
        existing_months = existing_months[0]
        # Update the existing subscription with the new cumulative months
        updated_months = existing_months + months
        cursor.execute('''
            UPDATE subscription_data
            SET sub_plan = ?, months = ?
            WHERE user_id = ?
        ''', (sub_plan, updated_months, recipient_user_id))
    else:
        # Recipient user does not exist in the database, insert new record
        cursor.execute('''
            INSERT INTO subscription_data (user_id, user_name, sub_plan, months)
            VALUES (?, ?, ?, ?)
        ''', (recipient_user_id, recipient_user_name, sub_plan, months))

    # Commit changes to the database
    conn.commit()
    conn.close()

    # Construct the message to be sent to the channel
    message = f"Thank you {user_name} for gifting a {sub_plan} subscription to {recipient_user_name}! They are now a {sub_plan} subscriber for {months} months!"

    # Send the message to the channel
    channel = bot.get_channel(CHANNEL_NAME)
    await channel.send(message)

async def process_anonsubgift_event(sub_plan, months, recipient_user_id, recipient_user_name):
    # Connect to the database
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    # Check if the recipient user exists in the database
    cursor.execute('SELECT months FROM subscription_data WHERE user_id = ?', (recipient_user_id,))
    existing_months = cursor.fetchone()

    if existing_months:
        # Recipient user exists in the database
        existing_months = existing_months[0]
        # Update the existing subscription with the new cumulative months
        updated_months = existing_months + months
        cursor.execute('''
            UPDATE subscription_data
            SET sub_plan = ?, months = ?
            WHERE user_id = ?
        ''', (sub_plan, updated_months, recipient_user_id))
    else:
        # Recipient user does not exist in the database, insert new record
        cursor.execute('''
            INSERT INTO subscription_data (user_id, user_name, sub_plan, months)
            VALUES (?, ?, ?, ?)
        ''', (recipient_user_id, recipient_user_name, sub_plan, months))

    # Commit changes to the database
    conn.commit()
    conn.close()

    # Construct the message to be sent to the channel
    message = f"An anonymous user has gifted a {sub_plan} subscription to {recipient_user_name}! They are now a {sub_plan} subscriber for {months} months!"

    # Send the message to the channel
    channel = bot.get_channel(CHANNEL_NAME)
    await channel.send(message)

async def process_multi_month_sub_event(user_id, user_name, sub_plan, months, recipient_user_id, recipient_user_name, multi_month_duration):
    # Connect to the database
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    # Process the subscription event for multi-month sub
    cursor.execute('''
        INSERT INTO subscription_data (user_id, user_name, sub_plan, months)
        VALUES (?, ?, ?, ?)
    ''', (recipient_user_id, recipient_user_name, sub_plan, months))

    # Commit changes to the database
    conn.commit()
    conn.close()

    # Construct the message to be sent to the channel
    message = f"Thank you {user_name} for subscribing for {multi_month_duration} months! You are now a {sub_plan} subscriber for {months} months!"

    # Send the message to the channel
    channel = bot.get_channel(CHANNEL_NAME)
    await channel.send(message)

# Function for FOLLOWERS
async def process_followers_event(user_id, user_name, followed_at):
    # Connect to the database
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()

    # Insert a new record for the follower
    cursor.execute('''
        INSERT INTO followers_data (user_id, user_name, followed_at)
        VALUES (?, ?, ?)
    ''', (user_id, user_name, followed_at))

    # Commit changes to the database
    conn.commit()
    conn.close()

    # Construct the message to be sent to the channel
    message = f"Thank you {user_name} for following! Welcome to the channel!"

    # Send the message to the channel
    channel = bot.get_channel(CHANNEL_NAME)
    await channel.send(message)

# Function to create a new group if it doesn't exist
def group_creation():
    group_names = ["VIP", "Subscriber T1", "Subscriber T2", "Subscriber T3"]
    for name in group_names:
        cursor.execute("SELECT * FROM groups WHERE name=?", (name,))
        if not cursor.fetchone():
            try:
                cursor.execute("INSERT INTO groups (name) VALUES (?)", (name,))
                conn.commit()
                bot_logger.info(f"Group '{name}' created successfully.")
            except sqlite3.IntegrityError:
                bot_logger.error(f"Failed to create group '{name}' due to integrity error.")
        else:
            return

# Function to handle user grouping
async def handle_user_grouping(username, user_id):
    group_names = []
    
    # Check if the user is the broadcaster
    if username == CHANNEL_NAME:
        return
    
    # Check if the user is a VIP
    if is_user_vip(user_id):
        group_names.append("VIP")

    # Check if the user is a subscriber
    subscription_tier = is_user_subscribed(user_id)
    if subscription_tier:
        # Map subscription tier to group name
        if subscription_tier == "Tier 1":
            group_names.append("Subscriber T1")
        elif subscription_tier == "Tier 2":
            group_names.append("Subscriber T2")
        elif subscription_tier == "Tier 3":
            group_names.append("Subscriber T3")

    # Assign user to groups
    for name in group_names:
        cursor.execute("SELECT * FROM groups WHERE name=?", (name,))
        group = cursor.fetchone()
        if group:
            try:
                cursor.execute("INSERT OR REPLACE INTO everyone (username, group_name) VALUES (?, ?)", (username, name))
                conn.commit()
                bot_logger.info(f"User '{username}' assigned to group '{name}' successfully.")
            except sqlite3.IntegrityError:
                bot_logger.error(f"Failed to assign user '{username}' to group '{name}'.")
        else:
            bot_logger.error(f"Group '{name}' does not exist.")

# Here is the BOT
bot = BotOfTheSpecter(
    token=OAUTH_TOKEN,
    prefix='!',
    channel_name=CHANNEL_NAME
)

# Errors
@bot.event
async def event_command_error(error):
    bot_logger.error(f"Error occurred: {error}")

# Run the bot
def start_bot():
    # Schedule bot tasks
    asyncio.get_event_loop().create_task(refresh_token_every_day())
    asyncio.get_event_loop().create_task(check_auto_update())
    asyncio.get_event_loop().create_task(check_stream_online())
    asyncio.get_event_loop().create_task(twitch_pubsub())
    asyncio.get_event_loop().create_task(timed_message())
    
    # Create groups if they don't exist
    group_creation()

    # Start the bot
    bot.run()

if __name__ == '__main__':
    start_bot()