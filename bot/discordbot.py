import asyncio
import logging
import os
import signal
import aiohttp
import discord
from discord.ext import commands as commands
from enum import Enum
import argparse
import aiomysql
import socketio
from dotenv import load_dotenv
from urllib.parse import urlencode

# Load environment variables from .env file
load_dotenv()

# Define logging directory
logs_directory = "/var/www/logs"
discord_logs = os.path.join(logs_directory, "discord")

# Ensure directory exists
for directory in [logs_directory, discord_logs]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Function to setup logger
def setup_logger(name, log_file, level=logging.INFO):
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    handler = logging.FileHandler(log_file)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    return logger

# Global configuration class
class Config:
    def __init__(self):
        self.admin_user_id = None
        self.live_channel_id = None
        self.guild_id = None
        self.api_token = None
        self.online_text = None
        self.offline_text = None

config = Config()

# MySQL connection
async def get_mysql_connection(logger):
    sql_host = os.getenv('SQL_HOST')
    sql_user = os.getenv('SQL_USER')
    sql_password = os.getenv('SQL_PASSWORD')
    if not sql_host or not sql_user or not sql_password:
        logger.error("Missing SQL connection parameters. Please check the .env file.")
        return None
    try:
        conn = await aiomysql.connect(
            host=sql_host,
            user=sql_user,
            password=sql_password,
            db='website'
        )
        return conn
    except Exception as e:
        logger.error(f"Error connecting to MySQL: {e}")
        return None

# Fetch admin user ID, live channel ID, guild ID, online text, and offline text from the database
async def fetch_discord_details(username, logger):
    connection = await get_mysql_connection(logger)
    if connection is None:
        return
    try:
        async with connection.cursor() as cursor:
            await cursor.execute("""
                SELECT du.discord_id, du.live_channel_id, du.guild_id, du.online_text, du.offline_text
                FROM discord_users du
                JOIN users u ON du.user_id = u.id
                WHERE u.username = %s
            """, (username,))
            result = await cursor.fetchone()
        await connection.ensure_closed()
        if result:
            logger.info(f"Fetched details from DB: discord_id={result[0]}, live_channel_id={result[1]}, guild_id={result[2]}, online_text={result[3]}, offline_text={result[4]}")
            config.admin_user_id = result[0]
            config.live_channel_id = result[1]
            config.guild_id = result[2]
            config.online_text = result[3]
            config.offline_text = result[4]
        else:
            logger.error("No results found for discord details")
    except Exception as e:
        logger.error(f"Error fetching discord details: {e}")

# Fetch API token from the database
async def fetch_api_token(username, logger):
    connection = await get_mysql_connection(logger)
    if connection is None:
        return
    try:
        async with connection.cursor() as cursor:
            await cursor.execute("""
                SELECT api_key
                FROM users
                WHERE username = %s
            """, (username,))
            result = await cursor.fetchone()
        await connection.ensure_closed()
        if result:
            config.api_token = result[0]
        else:
            logger.error("No results found for API token")
    except Exception as e:
        logger.error(f"Error fetching API token: {e}")

# Function to connect to the websocket server and push a notice
async def websocket_notice(event, member=None, api_token=None, logger=None):
    async with aiohttp.ClientSession() as session:
        params = {
            'code': api_token,
            'event': event,
            'member': member
        }
        # URL-encode the parameters
        encoded_params = urlencode(params)
        url = f'https://websocket.botofthespecter.com/notify?{encoded_params}'
        logger.info(f"Sending HTTP event '{event}' with URL: {url}")
        async with session.get(url) as response:
            if response.status == 200:
                logger.info(f"HTTP event '{event}' sent successfully with params: {params}")
            else:
                logger.error(f"Failed to send HTTP event '{event}'. Status: {response.status}")

class ChannelType(Enum):
    GUILD_TEXT = 0
    DM = 1
    GUILD_VOICE = 2
    GROUP_DM = 3
    GUILD_CATEGORY = 4
    GUILD_ANNOUNCEMENT = 5
    ANNOUNCEMENT_THREAD = 10
    PUBLIC_THREAD = 11
    PRIVATE_THREAD = 12
    GUILD_STAGE_VOICE = 13
    GUILD_DIRECTORY = 14
    GUILD_FORUM = 15
    GUILD_MEDIA = 16

    @classmethod
    def has_value(cls, value):
        return value in cls._value2member_map_

class LoggingClientSession(aiohttp.ClientSession):
    def __init__(self, *args, logger=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logger or logging.getLogger(__name__)

    async def _request(self, method, url, **kwargs):
        response = await super()._request(method, url, **kwargs)
        self.log_rate_limit_headers(response)
        return response

    def log_rate_limit_headers(self, response):
        headers = response.headers
        rate_limit_limit = headers.get("X-RateLimit-Limit")
        rate_limit_remaining = headers.get("X-RateLimit-Remaining")
        
        if rate_limit_limit or rate_limit_remaining:
            self.logger.info(f"Rate limit - Limit: {rate_limit_limit}, Remaining: {rate_limit_remaining}")

class BotOfTheSpecter(commands.Bot):
    def __init__(self, discord_token, channel_name, discord_logger, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__("!", intents=intents, **kwargs)
        self.discord_token = discord_token
        self.channel_name = channel_name
        self.logger = discord_logger
        self.typing_speed = 50
        self.http._HTTPClient__session = LoggingClientSession(logger=self.logger, connector=aiohttp.TCPConnector(ssl=False))

    async def on_ready(self):
        self.logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        self.logger.info("BotOfTheSpecter Discord Bot has started.")
        self.logger.info(f'Setting channel {config.live_channel_id} to offline status on bot start.')
        await self.add_cog(WebSocketCog(self, config.api_token, self.logger))
        await self.update_channel_status(config.live_channel_id, "offline")

    async def on_member_join(self, member):
        self.logger.info(f'{member.name} has joined the server!')
        await websocket_notice(event="DISCORD_JOIN", member=member.name, api_token=config.api_token, logger=self.logger)

    async def on_message(self, message):
        # Ignore bot's own messages
        if message.author == self.user:
            return
        # Process the message
        await self.process_commands(message)

    async def update_channel_status(self, channel_id: int, status: str):
        self.logger.info(f'Updating channel {channel_id} to {status} status in guild {config.guild_id}.')
        try:
            await fetch_discord_details(self.channel_name, self.logger) 
            guild = await self.fetch_guild(config.guild_id)
            self.logger.info(f'Fetched guild: {guild}')
            if guild is None:
                self.logger.error(f'Guild with ID {config.guild_id} not found.')
                return
            channel = guild.get_channel(channel_id)
            self.logger.info(f'Fetched channel from cache: {channel}')
            if channel is None:
                self.logger.error(f'Channel with ID {channel_id} not found. Fetching from API.')
                try:
                    channel = await guild.fetch_channel(channel_id)
                    self.logger.info(f'Fetched channel from API: {channel}')
                except discord.HTTPException as e:
                    self.logger.error(f'Error fetching channel from API: {e}')
                    return
            # Check if the current channel name already matches the intended status
            if status == "offline":
                intended_name = f"🔴 {config.offline_text}"
            elif status == "online":
                intended_name = f"🟢 {config.online_text}"
            else:
                self.logger.error(f"Unknown status: {status}")
                return
            if channel.name == intended_name:
                self.logger.info(f"Channel name already set to {intended_name}, no update needed.")
            else:
                await self.set_channel_name(channel, intended_name)
        except discord.HTTPException as e:
            self.logger.error(f'Error fetching guild with ID {config.guild_id}: {e}')

    async def fetch_channel(self):
        self.logger.info("Fetching channels in the guild.")
        guild = await self.fetch_guild(config.guild_id)
        if guild:
            channels = guild.channels
            for channel in channels:
                self.logger.info(f'Channel found: {channel.name} (ID: {channel.id})')
        else:
            self.logger.error(f'Guild with ID {config.guild_id} not found.')

    async def set_channel_name(self, channel: discord.VoiceChannel, name: str):
        if channel:
            self.logger.info(f'Setting channel name to {name}')
            try:
                await channel.edit(name=name)
                self.logger.info(f'Channel name set to {name}')
            except discord.HTTPException as e:
                self.logger.error(f'Error setting channel name: {e}')

class WebSocketCog(commands.Cog, name='WebSocket'):
    def __init__(self, bot: BotOfTheSpecter, api_token: str, logger=None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.bot = bot
        self.api_token = api_token
        self.sio = socketio.AsyncClient()

        @self.sio.event
        async def connect():
            self.logger.info("Connected to WebSocket server")
            await self.sio.emit('REGISTER', {'code': self.api_token, 'name': 'DiscordBot'})

        @self.sio.event
        async def disconnect():
            self.logger.info("Disconnected from WebSocket server")

        @self.sio.event
        async def STREAM_ONLINE(data):
            self.logger.info(f"Received STREAM_ONLINE event: {data}")
            await self.bot.update_channel_status(config.live_channel_id, "online")

        @self.sio.event
        async def STREAM_OFFLINE(data):
            self.logger.info(f"Received STREAM_OFFLINE event: {data}")
            await self.bot.update_channel_status(config.live_channel_id, "offline")

        self.bot.loop.create_task(self.start_websocket())

    async def start_websocket(self):
        try:
            await self.sio.connect('wss://websocket.botofthespecter.com')
            await self.sio.wait()
        except Exception as e:
            self.logger.error(f"WebSocket connection error: {e}")
            await asyncio.sleep(5)
            self.bot.loop.create_task(self.start_websocket())

    def cog_unload(self):
        self.bot.loop.create_task(self.sio.disconnect())

class DiscordBotRunner:
    def __init__(self, discord_token, channel_name, discord_logger):
        self.logger = discord_logger
        self.discord_token = discord_token
        self.channel_name = channel_name
        self.bot = None
        self.loop = None
        signal.signal(signal.SIGTERM, self.sig_handler)
        signal.signal(signal.SIGINT, self.sig_handler)

    def sig_handler(self, signum, frame):
        signame = signal.Signals(signum).name
        self.logger.error(f'Caught Signal {signame} ({signum})')
        self.stop()

    def stop(self):
        if self.bot is not None:
            self.logger.info("Stopping BotOfTheSpecter Discord Bot")
            future = asyncio.run_coroutine_threadsafe(self.bot.close(), self.loop)
            try:
                future.result(5)
            except TimeoutError:
                self.logger.error("Timeout error - Bot didn't respond. Forcing close.")
            except asyncio.CancelledError:
                self.logger.error("Bot task was cancelled. Forcing close.")

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.logger.info("Starting BotOfTheSpecter Discord Bot")
        try:
            self.loop.run_until_complete(self.initialize_bot())
        except asyncio.CancelledError:
            self.logger.error("BotRunner task was cancelled.")
        finally:
            self.loop.close()

    async def initialize_bot(self):
        await fetch_api_token(self.channel_name, self.logger)
        if config.api_token is None:
            self.logger.error("API token is None. Exiting.")
            return
        await fetch_discord_details(self.channel_name, self.logger)
        if config.admin_user_id is None or config.live_channel_id is None or config.guild_id is None:
            self.logger.error("Admin user ID, live channel ID, or guild ID is None. Exiting.")
            return
        self.bot = BotOfTheSpecter(self.discord_token, self.channel_name, self.logger)
        await self.bot.start(self.discord_token)

def main():
    parser = argparse.ArgumentParser(description="BotOfTheSpecter Discord Bot")
    parser.add_argument("-channel", dest="channel_name", required=True, help="Target Twitch channel name")
    args = parser.parse_args()
    bot_log_file = os.path.join(discord_logs, f"{args.channel_name}.txt")
    discord_logger = setup_logger('discord', bot_log_file, level=logging.INFO)
    discord_token = os.getenv("DISCORD_TOKEN")
    bot_runner = DiscordBotRunner(discord_token, args.channel_name, discord_logger)
    bot_runner.run()

if __name__ == "__main__":
    main()