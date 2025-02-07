import asyncio
import logging
import os
import signal
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import aiomysql

# Load environment variables from .env file
load_dotenv()

# Define logging directory
logs_directory = "/var/www/logs"
discord_logs = os.path.join(logs_directory, "specterdiscord")

# Ensure directory exists
for directory in [logs_directory, discord_logs]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Function to setup logger
def setup_logger(name, log_file, level=logging.INFO):
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
        self.discord_token = os.getenv("DISCORD_TOKEN")
        self.api_token = os.getenv("API_KEY")

config = Config()

# Define the bot version
BOT_VERSION = "2.0"

# Bot class
class BotOfTheSpecter(commands.Bot):
    def __init__(self, discord_token, discord_logger, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, **kwargs)
        self.discord_token = discord_token
        self.logger = discord_logger
        self.typing_speed = 50
        self.processed_messages_file = f"/var/www/logs/discord/messages.txt"
        self.version = BOT_VERSION
        self.pool = None  # Initialize the pool attribute
        # Ensure the log file exists
        if not os.path.exists(self.processed_messages_file):
            open(self.processed_messages_file, 'w').close()

    async def init_access_website_database(self):
        self.pool = await aiomysql.create_pool(
            host=os.getenv('SQL_HOST'),
            user=os.getenv('SQL_USER'),
            password=os.getenv('SQL_PASSWORD'),
            db="website"
        )
        self.logger.info("Database connection pool for website initialized")

    async def get_twitch_access_token(self, user_id: str):
        if not self.pool:
            await self.init_access_website_database()
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT twitch_access_token FROM twitch_bot_access WHERE twitch_user_id = %s LIMIT 1", (user_id,))
                result = await cur.fetchone()
                return result.get('twitch_access_token') if result else None

    async def is_streaming(self):
        client_id = os.getenv("CLIENT_ID")
        twitch_user = "botofthespecter"
        # Get the Twitch access token from the database
        access_token = await self.get_twitch_access_token("971436498")  # Replace with your Twitch user ID
        if not access_token:
            self.logger.error("Failed to retrieve Twitch access token from the database.")
            return False, None  # Return None for thumbnail if access token is not available

        async with aiohttp.ClientSession() as session:
            # Check if the user is live
            async with session.get(
                f'https://api.twitch.tv/helix/streams?user_login={twitch_user}',
                headers={'Client-ID': client_id, 'Authorization': f'Bearer {access_token}'}
            ) as response:
                stream_data = await response.json()
                if stream_data.get('data'):
                    # Stream is live, return the thumbnail URL
                    thumbnail_url = stream_data['data'][0]['thumbnail_url']
                    # Replace {width} and {height} with desired dimensions
                    thumbnail_url = thumbnail_url.replace("{width}", "1280").replace("{height}", "720")
                    return True, thumbnail_url  # Return True and the thumbnail URL
                return False, None  # Stream is not live

    async def periodic_stream_check(self):
        await self.wait_until_ready()  # Wait until the bot is ready
        while not self.is_closed():
            is_live, thumbnail_url = await self.is_streaming()
            if is_live:
                await self.change_presence(activity=discord.Streaming(name="Streaming on Twitch", url="https://www.twitch.tv/botofthespecter", details="Live now!", state="Come join!", image=thumbnail_url))
            else:
                await self.change_presence(activity=discord.Game(name="Not currently streaming"))
            await asyncio.sleep(300)  # Wait for 5 minutes (300 seconds)

    async def on_ready(self):
        self.logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        self.logger.info(f'Bot version: {self.version}')
        # Ensure the database pool is initialized
        if not self.pool:
            await self.init_access_website_database()
        # Set the initial presence
        await self.update_presence()
        # Start the periodic stream check in the background
        self.loop.create_task(self.periodic_stream_check())
        await self.add_cog(QuoteCog(self, config.api_token, self.logger))
        await self.add_cog(TicketCog(self, self.logger))
        self.logger.info("BotOfTheSpecter Discord Bot has started.")

    async def setup_hook(self):
        # Sync the slash commands when the bot starts
        try:
            await self.tree.sync()
            self.logger.info("Successfully synced slash commands.")
        except Exception as e:
            self.logger.error(f"Error syncing slash commands: {e}")
        
        # Add error handler for command tree
        self.tree.on_error = self.on_app_command_error

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Ignore CommandNotFound errors (commands from other bots)
        if isinstance(error, app_commands.CommandNotFound):
            return
        # Log other errors as usual
        self.logger.error(f"Error in application command: {str(error)}")

    async def get_ai_response(self, user_message, channel_name):
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "message": user_message,
                    "channel": channel_name,
                }
                self.logger.info(f"Sending payload to AI: {payload}")
                async with session.post('https://ai.botofthespecter.com/', json=payload) as response:
                    self.logger.info(f"AI server response status: {response.status}")
                    response.raise_for_status()  # Raise an exception for bad responses
                    ai_response = await response.text()  # Read response as plain text
                    self.logger.info(f"AI response received: {ai_response}")
                    # Split the response into chunks of 2000 characters
                    if ai_response:  # Ensure response is not empty
                        chunks = [ai_response[i:i + 2000] for i in range(0, len(ai_response), 2000)]
                        return chunks
                    else:
                        self.logger.error("Received empty AI response")
                        return ["Sorry, I could not understand your request."]
        except aiohttp.ClientError as e:
            self.logger.error(f"Error getting AI response: {e}")
            return ["Sorry, I could not understand your request."]
        except Exception as e:
            self.logger.error(f"Unexpected error in get_ai_response: {e}")
            return ["Sorry, I encountered an error processing your request."]

    async def on_message(self, message):
        # Ignore bot's own messages
        if message.author == self.user:
            return
        # Determine the "channel_name" based on the source of the message
        if isinstance(message.channel, discord.DMChannel):
            channel = message.channel
            channel_name = str(message.author.id)  # Use user ID for DMs
        else:
            channel = message.channel
            channel_name = str(message.guild.name)  # Use guild name for server messages
        # Use the message ID to track if it's already been processed
        message_id = str(message.id)
        with open(self.processed_messages_file, 'r') as file:
            processed_messages = file.read().splitlines()
        if message_id in processed_messages:
            self.logger.info(f"Message ID {message_id} has already been processed. Skipping.")
            return
        # Process the message if it's in a DM channel
        if isinstance(message.channel, discord.DMChannel):
            try:
                # Fetch AI responses
                ai_responses = await self.get_ai_response(message.content, channel_name)
                # Only enter typing context if there are responses to send
                if ai_responses:
                    async with channel.typing():
                        self.logger.info(f"Processing message from {message.author}: {message.content}")
                        # Send each chunk of AI response
                        for ai_response in ai_responses:
                            if ai_response:  # Ensure we're not sending an empty message
                                typing_delay = len(ai_response) / self.typing_speed
                                await asyncio.sleep(typing_delay)  # Simulate typing speed
                                await message.author.send(ai_response)
                                self.logger.info(f"Sent AI response to {message.author}: {ai_response}")
                            else:
                                self.logger.error("AI response chunk was empty, not sending.")
            except discord.HTTPException as e:
                self.logger.error(f"Failed to send message: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error in on_message: {e}")
            # Mark the message as processed by appending the message ID to the file
            with open(self.processed_messages_file, 'a') as file:
                file.write(message_id + '\n')
        # If the message is in a server channel, process commands
        await self.process_commands(message)

    async def update_presence(self):
        server_count = len(self.guilds)  # Get the number of servers the bot is in
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{server_count} servers"))
        self.logger.info(f"Updated presence to 'Watching {server_count} servers'.")

    async def periodic_presence_update(self):
        await self.wait_until_ready()  # Wait until the bot is ready
        while not self.is_closed():
            await self.update_presence()  # Update the presence
            await asyncio.sleep(300)  # Wait for 5 minutes (300 seconds)

class QuoteCog(commands.Cog, name='Quote'):
    def __init__(self, bot: BotOfTheSpecter, api_token: str, logger=None):
        self.bot = bot
        self.api_token = api_token
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.typing_speed = 50
        # Register the slash command
        self.bot.tree.add_command(
            app_commands.Command(
                name="quote",
                description="Get a random quote",
                callback=self.slash_quote,
            )
        )

    @commands.command(name="quote")
    async def get_quote(self, ctx):
        await self.fetch_and_send_quote(ctx)

    async def slash_quote(self, interaction: discord.Interaction):
        await self.fetch_and_send_quote(interaction)

    async def fetch_and_send_quote(self, ctx_or_interaction):
        if isinstance(ctx_or_interaction, commands.Context):
            ctx = ctx_or_interaction
        else:
            ctx = await commands.Context.from_interaction(ctx_or_interaction)
        url = f"https://api.botofthespecter.com/quotes?api_key={self.api_token}"
        try:
            async with aiohttp.ClientSession() as session:
                async with ctx.typing():
                    async with session.get(url) as response:
                        if response.status == 200:
                            quote_data = await response.json()
                            if "quote" in quote_data and "author" in quote_data:
                                quote = quote_data["quote"]
                                author = quote_data["author"]
                                message = f'📜 **Quote:** "{quote}" — *{author}*'
                                # Calculate delay based on message length
                                typing_delay = len(message) / self.typing_speed
                                await asyncio.sleep(typing_delay)
                                await ctx.send(message)
                            else:
                                await ctx.send("Sorry, I couldn't fetch a quote at this time.")
                        else:
                            self.logger.error(f"Failed to fetch quote. Status code: {response.status}")
                            await ctx.send("Sorry, I couldn't fetch a quote at this time.")
        except Exception as e:
            self.logger.error(f"Error fetching quote: {e}")
            await ctx.send("An error occurred while fetching the quote.")

class TicketCog(commands.Cog, name='Tickets'):
    def __init__(self, bot: commands.Bot, logger=None):
        self.bot = bot
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.pool = None
        self.OWNER_ID = 127783626917150720              # gfaUnDead User ID (Owner)
        self.SUPPORT_GUILD_ID = 1103694163930787880     # YourStreamingTools Server ID
        self.MOD_CHANNEL_ID = 1103695077928345683       # Moderator Channel ID

    async def init_ticket_database(self):
        # First create a connection without specifying a database
        temp_pool = await aiomysql.create_pool(
            host=os.getenv('SQL_HOST'),
            user=os.getenv('SQL_USER'),
            password=os.getenv('SQL_PASSWORD'),
            autocommit=True
        )
        try:
            # Create database if it doesn't exist
            async with temp_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("CREATE DATABASE IF NOT EXISTS tickets")
            # Close the temporary pool
            temp_pool.close()
            await temp_pool.wait_closed()
            # Create the main connection pool with the tickets database
            self.pool = await aiomysql.create_pool(
                host=os.getenv('SQL_HOST'),
                user=os.getenv('SQL_USER'),
                password=os.getenv('SQL_PASSWORD'),
                db='tickets',
                autocommit=True
            )
            self.logger.info("Successfully initialized ticket database connection pool")
            # Create necessary tables
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Create tickets table
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS tickets (
                            ticket_id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id BIGINT NOT NULL,
                            username VARCHAR(255) NOT NULL,
                            issue TEXT NOT NULL,
                            status VARCHAR(20) DEFAULT 'open',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            closed_at TIMESTAMP NULL,
                            priority VARCHAR(20) DEFAULT 'normal',
                            category VARCHAR(50) DEFAULT 'general',
                            channel_id BIGINT NULL
                        )
                    """)
                    # Create ticket_comments table
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS ticket_comments (
                            comment_id INT AUTO_INCREMENT PRIMARY KEY,
                            ticket_id INT NOT NULL,
                            user_id BIGINT NOT NULL,
                            username VARCHAR(255) NOT NULL,
                            comment TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id)
                            ON DELETE CASCADE
                        )
                    """)
                    # Create ticket_attachments table
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS ticket_attachments (
                            attachment_id INT AUTO_INCREMENT PRIMARY KEY,
                            ticket_id INT NOT NULL,
                            file_url VARCHAR(512) NOT NULL,
                            file_name VARCHAR(255) NOT NULL,
                            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id)
                            ON DELETE CASCADE
                        )
                    """)
                    # Create ticket_history table
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS ticket_history (
                            history_id INT AUTO_INCREMENT PRIMARY KEY,
                            ticket_id INT NOT NULL,
                            user_id BIGINT NOT NULL,
                            username VARCHAR(255) NOT NULL,
                            action VARCHAR(50) NOT NULL,
                            details TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id)
                            ON DELETE CASCADE
                        )
                    """)
                    # Create ticket_settings table
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS ticket_settings (
                            guild_id BIGINT PRIMARY KEY,
                            info_channel_id BIGINT,
                            category_id BIGINT,
                            enabled BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                        )
                    """)
            self.logger.info("Successfully initialized ticket database and tables")
        except Exception as e:
            self.logger.error(f"Error initializing ticket database: {e}")
            raise

    async def get_settings(self, guild_id: int):
        if not self.pool:
            await self.init_ticket_database()
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM ticket_settings WHERE guild_id = %s",
                    (guild_id,)
                )
                return await cur.fetchone()

    async def create_ticket_channel(self, guild_id: int, user_id: int, ticket_id: int):
        settings = await self.get_settings(guild_id)
        if not settings:
            raise ValueError("Ticket system not set up")
        guild = self.bot.get_guild(guild_id)
        category = guild.get_channel(settings['category_id'])
        user = guild.get_member(user_id)
        owner = guild.get_member(self.OWNER_ID)
        # Create the ticket channel
        channel = await guild.create_text_channel(
            name=f"ticket-{ticket_id}",
            category=category,
            topic=f"Support Ticket #{ticket_id} | User: {user.name}"
        )
        # Set permissions
        await channel.set_permissions(guild.default_role, read_messages=False)
        await channel.set_permissions(user, read_messages=True, send_messages=True)
        await channel.set_permissions(owner, read_messages=True, send_messages=True)
        # Create welcome message
        embed = discord.Embed(
            title=f"Support Ticket #{ticket_id}",
            description=(
                "Welcome to your support ticket channel!\n\n"
                "Please provide the following information:\n"
                "1. A detailed description of your issue\n"
                "2. What you've tried so far (if applicable)\n"
                "3. Any relevant screenshots or files\n\n"
                "Our support team will assist you as soon as possible.\n"
                "Please be patient and remain respectful throughout the process."
            ),
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Commands",
            value=(
                "`!close` - Close this ticket when resolved\n"
                "`!add @user` - Add another user to this ticket"
            ),
            inline=False
        )
        embed.set_footer(text="Bot of the Specter Support System")
        await channel.send(f"{user.mention} Welcome to your support ticket!", embed=embed)
        return channel

    async def create_ticket(self, guild_id: int, user_id: int, username: str) -> int:
        settings = await self.get_settings(guild_id)
        if not settings or not settings['enabled']:
            raise ValueError("Ticket system is not set up in this server")
        if not self.pool:
            await self.init_ticket_database()
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO tickets (user_id, username, issue) VALUES (%s, %s, %s)",
                    (user_id, username, "Awaiting user's issue description")
                )
                ticket_id = cur.lastrowid
                await cur.execute(
                    "INSERT INTO ticket_history (ticket_id, user_id, username, action, details) VALUES (%s, %s, %s, %s, %s)",
                    (ticket_id, user_id, username, "created", "Ticket channel created")
                )
                return ticket_id

    async def close_ticket(self, ticket_id: int, channel_id: int, closer_id: int, closer_name: str):
        if not self.pool:
            await self.init_ticket_database()
        # Get the channel and ticket information
        channel = self.bot.get_channel(channel_id)
        if not channel:
            raise ValueError("Channel not found")
        # Get ticket information to identify the ticket creator
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT user_id FROM tickets WHERE ticket_id = %s", (ticket_id,))
                ticket_data = await cur.fetchone()
                if not ticket_data:
                    raise ValueError("Ticket not found in database")
                # Update ticket status and store channel_id
                await cur.execute(
                    """UPDATE tickets 
                       SET status = 'closed', 
                           closed_at = NOW(), 
                           channel_id = %s 
                       WHERE ticket_id = %s""",
                    (channel_id, ticket_id)
                )
                # Log the closure in history
                await cur.execute(
                    "INSERT INTO ticket_history (ticket_id, user_id, username, action, details) VALUES (%s, %s, %s, %s, %s)",
                    (ticket_id, closer_id, closer_name, "closed", "Ticket closed by user")
                )
        if channel:
            # Send closure message in channel
            embed = discord.Embed(
                title="Ticket Closing",
                description=(
                    "The support team has been notified that you no longer require assistance.\n"
                    "This ticket will be closed and archived.\n\n"
                    "If you need further assistance in the future, please create a new ticket."
                ),
                color=discord.Color.orange()
            )
            await channel.send(embed=embed)
            # Try to send DM to ticket creator
            try:
                ticket_creator = channel.guild.get_member(ticket_data['user_id'])
                if ticket_creator:
                    settings = await self.get_settings(channel.guild.id)
                    dm_embed = discord.Embed(
                        title="Support Ticket Closed",
                        description=(
                            f"Your support ticket (#{ticket_id}) has been closed by the support team.\n\n"
                            f"If you need further assistance or if this ticket was closed by mistake, "
                            f"please return to <#{settings['info_channel_id']}> and create a new ticket "
                            f"using `/ticket create` or `!ticket create`."
                        ),
                        color=discord.Color.blue()
                    )
                    await ticket_creator.send(embed=dm_embed)
                    self.logger.info(f"Sent closure DM to user {ticket_creator.name} for ticket #{ticket_id}")
            except discord.Forbidden:
                self.logger.warning(f"Could not send DM to user {ticket_data['user_id']} for ticket #{ticket_id}")
            except Exception as e:
                self.logger.error(f"Error sending closure DM: {e}")
            # Wait 10 seconds before proceeding with closure
            await asyncio.sleep(10)
            try:
                # Get or create the Closed Tickets category
                closed_category = discord.utils.get(channel.guild.categories, name="Closed Tickets")
                if not closed_category:
                    closed_category = await channel.guild.create_category(
                        name="Closed Tickets",
                        reason="Ticket System Archive"
                    )
                    # Set permissions for Closed Tickets category
                    await closed_category.set_permissions(channel.guild.default_role, read_messages=False)
                    await closed_category.set_permissions(
                        channel.guild.get_member(self.OWNER_ID),
                        read_messages=True,
                        send_messages=True
                    )
                # Remove ticket creator's access
                if ticket_creator:
                    await channel.set_permissions(ticket_creator, overwrite=None)
                # Move channel to Closed Tickets category
                await channel.edit(
                    category=closed_category,
                    sync_permissions=False,  # Don't sync with category permissions
                    locked=True  # Lock the channel
                )
                # Update channel topic to indicate it's closed
                new_topic = f"{channel.topic} [CLOSED]" if channel.topic else "[CLOSED]"
                await channel.edit(topic=new_topic)
                self.logger.info(f"Ticket #{ticket_id} closed and archived successfully")
            except discord.Forbidden:
                self.logger.error(f"Missing permissions to modify channel for ticket #{ticket_id}")
                raise
            except Exception as e:
                self.logger.error(f"Error archiving ticket #{ticket_id}: {e}")
                raise

    @commands.command(name="ticket")
    async def ticket_command(self, ctx, action: str = "create"):
        """Ticket system commands"""
        if action.lower() == "create":
            try:
                ticket_id = await self.create_ticket(ctx.guild.id, ctx.author.id, str(ctx.author))
                channel = await self.create_ticket_channel(ctx.guild.id, ctx.author.id, ticket_id)
                await ctx.send(
                    f"✅ Your ticket has been created! Please check {channel.mention} to provide your issue details.",
                    delete_after=10
                )
                self.logger.info(f"Ticket #{ticket_id} created by {ctx.author} with channel {channel.name}")
            except ValueError as e:
                await ctx.send(f"Error: {str(e)}")
            except Exception as e:
                self.logger.error(f"Error creating ticket: {e}")
                await ctx.send("An error occurred while creating your ticket. Please try again later.")
                
        elif action.lower() == "close":
            # Check if the command is used in a ticket channel
            if not ctx.channel.name.startswith("ticket-"):
                await ctx.send("This command can only be used in a ticket channel.")
                return
            try:
                ticket_id = int(ctx.channel.name.split("-")[1])
                # Check if user is ticket creator or bot owner
                ticket = await self.get_ticket(ticket_id)
                if not ticket:
                    await ctx.send("Could not find ticket information.")
                    return
                if ctx.author.id != ticket['user_id'] and ctx.author.id != self.OWNER_ID:
                    await ctx.send("Only the ticket creator or support team can close this ticket.")
                    return
                await self.close_ticket(ticket_id, ctx.channel.id, ctx.author.id, str(ctx.author))
                self.logger.info(f"Ticket #{ticket_id} closed by {ctx.author}")
            except Exception as e:
                self.logger.error(f"Error closing ticket: {e}")
                await ctx.send("An error occurred while closing the ticket.")
        else:
            await ctx.send("Invalid command. Use `!ticket create` to create a ticket or `!ticket close` to close your ticket.")

    @app_commands.command(name="ticket", description="Ticket system commands")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Create a new ticket", value="create"),
            app_commands.Choice(name="Close this ticket", value="close")
        ]
    )
    async def slash_ticket(self, interaction: discord.Interaction, action: str):
        if action == "create":
            try:
                await interaction.response.defer(ephemeral=True)
                ticket_id = await self.create_ticket(interaction.guild_id, interaction.user.id, str(interaction.user))
                channel = await self.create_ticket_channel(interaction.guild_id, interaction.user.id, ticket_id)
                await interaction.followup.send(
                    f"✅ Your ticket has been created! Please check {channel.mention} to provide your issue details.",
                    ephemeral=True
                )
                self.logger.info(f"Ticket #{ticket_id} created by {interaction.user} with channel {channel.name}")
            except ValueError as e:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
            except Exception as e:
                self.logger.error(f"Error creating ticket: {e}")
                await interaction.followup.send(
                    "An error occurred while creating your ticket. Please try again later.",
                    ephemeral=True
                )
        elif action == "close":
            # Check if the command is used in a ticket channel
            if not interaction.channel.name.startswith("ticket-"):
                await interaction.response.send_message(
                    "This command can only be used in a ticket channel.",
                    ephemeral=True
                )
                return
            try:
                ticket_id = int(interaction.channel.name.split("-")[1])
                # Check if user is ticket creator or bot owner
                ticket = await self.get_ticket(ticket_id)
                if not ticket:
                    await interaction.response.send_message(
                        "Could not find ticket information.",
                        ephemeral=True
                    )
                    return
                if interaction.user.id != ticket['user_id'] and interaction.user.id != self.OWNER_ID:
                    await interaction.response.send_message(
                        "Only the ticket creator or support team can close this ticket.",
                        ephemeral=True
                    )
                    return
                await interaction.response.defer()
                await self.close_ticket(ticket_id, interaction.channel.id, interaction.user.id, str(interaction.user))
                self.logger.info(f"Ticket #{ticket_id} closed by {interaction.user}")
            except Exception as e:
                self.logger.error(f"Error closing ticket: {e}")
                await interaction.followup.send("An error occurred while closing the ticket.")

    @commands.command(name="viewticket")
    @commands.has_permissions(administrator=True)
    async def view_ticket(self, ctx, ticket_id: int):
        """View a ticket (Admin only)"""
        ticket = await self.get_ticket(ticket_id)
        if ticket:
            embed = discord.Embed(
                title=f"Ticket #{ticket_id}",
                color=discord.Color.blue()
            )
            embed.add_field(name="User", value=ticket['username'], inline=False)
            embed.add_field(name="Issue", value=ticket['issue'], inline=False)
            embed.add_field(name="Status", value=ticket['status'], inline=False)
            embed.add_field(name="Created At", value=ticket['created_at'], inline=False)
            await ctx.send(embed=embed)
            self.logger.info(f"Ticket #{ticket_id} viewed by {ctx.author}")
        else:
            await ctx.send("Ticket not found!")

    @app_commands.command(name="viewticket", description="View a support ticket (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def slash_view_ticket(self, interaction: discord.Interaction, ticket_id: int):
        ticket = await self.get_ticket(ticket_id)
        if ticket:
            embed = discord.Embed(
                title=f"Ticket #{ticket_id}",
                color=discord.Color.blue()
            )
            embed.add_field(name="User", value=ticket['username'], inline=False)
            embed.add_field(name="Issue", value=ticket['issue'], inline=False)
            embed.add_field(name="Status", value=ticket['status'], inline=False)
            embed.add_field(name="Created At", value=ticket['created_at'], inline=False)
            await interaction.response.send_message(embed=embed)
            self.logger.info(f"Ticket #{ticket_id} viewed by {interaction.user}")
        else:
            await interaction.response.send_message("Ticket not found!")

    @commands.command(name="setuptickets")
    async def setup_tickets(self, ctx):
        """Set up the ticket system (Bot Owner Only)"""
        # Check if command is used in the moderator channel
        if ctx.channel.id != self.MOD_CHANNEL_ID:
            await ctx.send(
                "❌ This command can only be used in the moderator channel.",
                delete_after=10
            )
            return
        # Check if user is in the correct server
        if ctx.guild.id != self.SUPPORT_GUILD_ID:
            await ctx.send(
                "❌ The ticket system can only be set up in the YourStreamingTools Discord server.\n"
                "This is a centralized support system - please join <https://discord.com/invite/ANwEkpauHJ> "
                "to create support tickets."
            )
            return
        # Check if user is the bot owner
        if ctx.author.id != self.OWNER_ID:
            await ctx.send(
                "❌ Only the bot owner can set up the ticket system.\n"
                "The ticket system is managed centrally through the YourStreamingTools Discord server.\n"
                "Please join <https://discord.com/invite/ANwEkpauHJ> for support."
            )
            return
        try:
            # Create the category if it doesn't exist
            category = discord.utils.get(ctx.guild.categories, name="Open Tickets")
            if not category:
                category = await ctx.guild.create_category(
                    name="Open Tickets",
                    reason="Ticket System Setup"
                )
                self.logger.info(f"Created 'Open Tickets' category in {ctx.guild.name}")
            # Create info channel if it doesn't exist
            info_channel = discord.utils.get(category.channels, name="ticket-info")
            if not info_channel:
                info_channel = await ctx.guild.create_text_channel(
                    name="ticket-info",
                    category=category,
                    topic="How to create support tickets",
                    reason="Ticket System Setup"
                )
                self.logger.info(f"Created ticket-info channel in {ctx.guild.name}")
            # Save settings to database
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        INSERT INTO ticket_settings 
                        (guild_id, info_channel_id, category_id, enabled) 
                        VALUES (%s, %s, %s, TRUE)
                        ON DUPLICATE KEY UPDATE 
                        info_channel_id = VALUES(info_channel_id),
                        category_id = VALUES(category_id),
                        enabled = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    """, (ctx.guild.id, info_channel.id, category.id))
            # Create the info message
            embed = discord.Embed(
                title="🎫 YourStreamingTools Support System",
                description=(
                    "Welcome to our support ticket system!\n\n"
                    "To create a new support ticket, use either:\n"
                    "• `/ticket create`\n"
                    "• `!ticket create`\n\n"
                    "Once your ticket is created, you'll get access to a private channel where you can describe your issue "
                    "in detail and communicate with our support team.\n\n"
                    "Your ticket will be created and our support team will assist you as soon as possible."
                ),
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Important Notes",
                value=(
                    "• Your ticket will be created in a private channel\n"
                    "• Provide a clear description of your issue in the ticket channel\n"
                    "• One ticket per issue\n"
                    "• Be patient while waiting for a response\n"
                    "• Keep all communication respectful\n"
                    "• Only support team members can close tickets"
                ),
                inline=False
            )
            embed.set_footer(text="YourStreamingTools Support System")
            # Clear existing messages in info channel
            await info_channel.purge()
            await info_channel.send(embed=embed)
            # Set channel permissions
            await info_channel.set_permissions(
                ctx.guild.default_role,  # or interaction.guild.default_role for slash command
                read_messages=True,      # Allow everyone to see the channel
                send_messages=True,      # Allow sending messages (for commands)
                add_reactions=False,     # Prevent reactions
                embed_links=False,       # Prevent embeds
                attach_files=False,      # Prevent file attachments
                use_application_commands=True  # Allow slash commands
            )
            # Set up channel slowmode to prevent spam
            await info_channel.edit(slowmode_delay=5)  # 5 seconds between messages
            # Add a warning message about channel usage
            warning_embed = discord.Embed(
                title="⚠️ Channel Information",
                description=(
                    "This channel is for creating support tickets only.\n"
                    "Please use the commands `/ticket create` or `!ticket create` to open a ticket.\n"
                    "Regular messages will be automatically deleted."
                ),
                color=discord.Color.yellow()
            )
            await info_channel.send(embed=warning_embed)
            # Set proper permissions for the Open Tickets category
            await category.set_permissions(
                ctx.guild.default_role,  # or interaction.guild.default_role for slash command
                read_messages=False,     # Hide all ticket channels by default
                send_messages=False
            )
            await ctx.send(f"✅ Ticket system has been set up successfully!\nPlease check {info_channel.mention} for the info message.")
            self.logger.info(f"Ticket system set up completed in {ctx.guild.name}")
        except Exception as e:
            self.logger.error(f"Error setting up ticket system: {e}")
            await ctx.send("❌ An error occurred while setting up the ticket system. Please check the logs.")

    @app_commands.command(name="setuptickets", description="Set up the ticket system (Bot Owner Only)")
    async def slash_setup_tickets(self, interaction: discord.Interaction):
        """Set up the ticket system (Bot Owner Only)"""
        # Check if command is used in the moderator channel
        if interaction.channel_id != self.MOD_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ This command can only be used in the moderator channel.",
                ephemeral=True
            )
            return
        # Check if user is in the correct server
        if interaction.guild_id != self.SUPPORT_GUILD_ID:
            await interaction.response.send_message(
                "❌ The ticket system can only be set up in the YourStreamingTools Discord server.\n"
                "This is a centralized support system - please join <https://discord.com/invite/ANwEkpauHJ> "
                "to create support tickets.",
                ephemeral=True
            )
            return
        # Check if user is the bot owner
        if interaction.user.id != self.OWNER_ID:
            await interaction.response.send_message(
                "❌ Only the bot owner can set up the ticket system.\n"
                "The ticket system is managed centrally through the YourStreamingTools Discord server.\n"
                "Please join <https://discord.com/invite/ANwEkpauHJ> for support.",
                ephemeral=True
            )
            return
        await interaction.response.defer()
        try:
            # Create the category if it doesn't exist
            category = discord.utils.get(interaction.guild.categories, name="Open Tickets")
            if not category:
                category = await interaction.guild.create_category(
                    name="Open Tickets",
                    reason="Ticket System Setup"
                )
                self.logger.info(f"Created 'Open Tickets' category in {interaction.guild.name}")
            # Create info channel if it doesn't exist
            info_channel = discord.utils.get(category.channels, name="ticket-info")
            if not info_channel:
                info_channel = await interaction.guild.create_text_channel(
                    name="ticket-info",
                    category=category,
                    topic="How to create support tickets",
                    reason="Ticket System Setup"
                )
                self.logger.info(f"Created ticket-info channel in {interaction.guild.name}")
            # Save settings to database
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        INSERT INTO ticket_settings 
                        (guild_id, info_channel_id, category_id, enabled) 
                        VALUES (%s, %s, %s, TRUE)
                        ON DUPLICATE KEY UPDATE 
                        info_channel_id = VALUES(info_channel_id),
                        category_id = VALUES(category_id),
                        enabled = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    """, (interaction.guild_id, info_channel.id, category.id))
            # Create the info message
            embed = discord.Embed(
                title="🎫 YourStreamingTools Support System",
                description=(
                    "Welcome to our support ticket system!\n\n"
                    "To create a new support ticket, use either:\n"
                    "• `/ticket create`\n"
                    "• `!ticket create`\n\n"
                    "Once your ticket is created, you'll get access to a private channel where you can describe your issue "
                    "in detail and communicate with our support team.\n\n"
                    "Your ticket will be created and our support team will assist you as soon as possible."
                ),
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Important Notes",
                value=(
                    "• Your ticket will be created in a private channel\n"
                    "• Provide a clear description of your issue in the ticket channel\n"
                    "• One ticket per issue\n"
                    "• Be patient while waiting for a response\n"
                    "• Keep all communication respectful\n"
                    "• Only support team members can close tickets"
                ),
                inline=False
            )
            embed.set_footer(text="YourStreamingTools Support System")
            # Clear existing messages in info channel
            await info_channel.purge()
            await info_channel.send(embed=embed)
            # Set channel permissions
            await info_channel.set_permissions(
                interaction.guild.default_role,  # or interaction.guild.default_role for slash command
                read_messages=True,      # Allow everyone to see the channel
                send_messages=True,      # Allow sending messages (for commands)
                add_reactions=False,     # Prevent reactions
                embed_links=False,       # Prevent embeds
                attach_files=False,      # Prevent file attachments
                use_application_commands=True  # Allow slash commands
            )
            # Set up channel slowmode to prevent spam
            await info_channel.edit(slowmode_delay=5)  # 5 seconds between messages
            # Add a warning message about channel usage
            warning_embed = discord.Embed(
                title="⚠️ Channel Information",
                description=(
                    "This channel is for creating support tickets only.\n"
                    "Please use the commands `/ticket create` or `!ticket create` to open a ticket.\n"
                    "Regular messages will be automatically deleted."
                ),
                color=discord.Color.yellow()
            )
            await info_channel.send(embed=warning_embed)
            # Set proper permissions for the Open Tickets category
            await category.set_permissions(
                interaction.guild.default_role,  # or interaction.guild.default_role for slash command
                read_messages=False,     # Hide all ticket channels by default
                send_messages=False
            )
            await interaction.followup.send(f"✅ Ticket system has been set up successfully!\nPlease check {info_channel.mention} for the info message.")
            self.logger.info(f"Ticket system set up completed in {interaction.guild.name}")
        except Exception as e:
            self.logger.error(f"Error setting up ticket system: {e}")
            await interaction.followup.send("❌ An error occurred while setting up the ticket system. Please check the logs.")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bot messages
        if message.author.bot:
            return
        try:
            # Check if this is a ticket-info channel
            settings = await self.get_settings(message.guild.id)
            if not settings:
                return
            if message.channel.id == settings['info_channel_id']:
                # Check if message is a ticket command
                is_ticket_command = (
                    message.content.startswith('!ticket') or 
                    message.content.startswith('/ticket')
                )
                if not is_ticket_command:
                    # Delete non-ticket messages
                    await message.delete()
                    # Send a temporary warning message
                    warning = await message.channel.send(
                        f"{message.author.mention} This channel is for ticket commands only. "
                        "Please use `/ticket create` or `!ticket create` to open a ticket.",
                        delete_after=10
                    )
                    self.logger.info(f"Deleted non-ticket message from {message.author} in ticket-info channel")
        except Exception as e:
            self.logger.error(f"Error in ticket-info message watcher: {e}")

class DiscordBotRunner:
    def __init__(self, discord_logger):
        self.logger = discord_logger
        self.discord_token = config.discord_token
        self.bot = None
        self.loop = None
        signal.signal(signal.SIGTERM, self.sig_handler)
        signal.signal(signal.SIGINT, self.sig_handler)

    def sig_handler(self, signum, frame):
        signame = signal.Signals(signum).name
        self.logger.error(f'Caught Signal {signame} ({signum})')
        self.loop.create_task(self.stop_bot())

    async def stop_bot(self):
        if self.bot is not None:
            self.logger.info("Stopping BotOfTheSpecter Discord Bot")
            tasks = [t for t in asyncio.all_tasks(self.loop) if not t.done()]
            list(map(lambda task: task.cancel(), tasks))
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
                await self.bot.close()
            except asyncio.CancelledError as e:
                self.logger.error(f"Bot task was cancelled. Error: {e}")
            finally:
                self.loop.stop()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.initialize_bot())
        except asyncio.CancelledError:
            self.logger.error("BotRunner task was cancelled.")
        finally:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()

    async def initialize_bot(self):
        self.bot = BotOfTheSpecter(self.discord_token, self.logger)
        await self.bot.start(self.discord_token)

def main():
    bot_log_file = os.path.join(discord_logs, f"discordbot.txt")
    discord_logger = setup_logger('discord', bot_log_file, level=logging.INFO)
    discord_logger.info(f"Starting BotOfTheSpecter Discord Bot version {BOT_VERSION}")
    bot_runner = DiscordBotRunner(discord_logger)
    bot_runner.run()

if __name__ == "__main__":
    main()