import os
import socket
import signal
import asyncio
import logging
import ssl
import argparse
import socketio
from aiohttp import web
from google.cloud import texttospeech
import ipaddress
import paramiko
from dotenv import load_dotenv, find_dotenv

# Load ENV file
load_dotenv(find_dotenv("/home/websocket/.env"))

class BotOfTheSpecterWebsocketServer:
    def __init__(self, logger):
        # Set up Google Cloud credentials
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "/home/websocket/service-account-file.json"
        # Initialize the WebSocket server.
        self.logger = logger
        self.ip = self.get_own_ip()
        self.script_dir = os.path.dirname(os.path.realpath(__file__)).replace("\\", "/")
        self.tts_dir = "/home/websocket/tts"
        self.registered_clients = {}
        self.sio = socketio.AsyncServer(
            logger=logger, 
            engineio_logger=logger, 
            cors_allowed_origins='*', 
            ping_timeout=30,
            ping_interval=25
        )
        self.app = web.Application(middlewares=[self.ip_restriction_middleware])
        self.app.on_shutdown.append(self.on_shutdown)
        self.setup_routes()
        self.setup_event_handlers()
        self.sio.attach(self.app)
        self.loop = None
        signal.signal(signal.SIGTERM, self.sig_handler)
        signal.signal(signal.SIGINT, self.sig_handler)
        self.tts_client = texttospeech.TextToSpeechClient()
        self.tts_queue = asyncio.Queue()
        self.processing_task = None
        ips_file = "/home/websocket/ips.txt"
        self.allowed_ips = self.load_ips(ips_file)

    def load_ips(self, ips_file):
        allowed_ips = []
        try:
            with open(ips_file, 'r') as file:
                for line in file:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        allowed_ips.append(ipaddress.ip_network(line))
        except FileNotFoundError:
            self.logger.error(f"IPs file not found.")
        return allowed_ips

    def is_ip_allowed(self, ip):
        ip_address = ipaddress.ip_address(ip)
        for allowed_ip in self.allowed_ips:
            if ip_address in allowed_ip:
                return True
        return False

    def setup_routes(self):
        # Set up the routes for the web application.
        self.app.add_routes([
            web.get("/", self.index),
            web.get("/notify", self.notify_http),
            web.get("/heartbeat", self.heartbeat),
            web.get("/clients", self.list_clients)
        ])

    def setup_event_handlers(self):
        # Set up the event handlers for the SocketIO server.
        event_handlers = [
            ("connect", self.connect),
            ("disconnect", self.disconnect),
            ("REGISTER", self.register),
            ("LIST_CLIENTS", self.list_clients_event),
            ("NOTIFY", self.notify),
            ("DEATHS", self.deaths),
            ("WEATHER", self.weather),
            ("WEATHER_DATA", self.weather_data),
            ("TWITCH_FOLLOW", self.twitch_follow),
            ("TWITCH_CHEER", self.twitch_cheer),
            ("TWITCH_RAID", self.twitch_raid),
            ("TWITCH_SUB", self.twitch_sub),
            ("WALKON", self.walkon),
            ("TTS", self.tts),
            ("SOUND_ALERT", self.sound_alert),
            ("STREAM_ONLINE", self.stream_online),
            ("STREAM_OFFLINE", self.stream_offline),
            ("DISCORD_JOIN", self.discord_join),
            ("FOURTHWALL", self.handle_fourthwall_event),
            ("*", self.event)
        ]
        for event, handler in event_handlers:
            self.sio.on(event, handler)

    async def ip_restriction_middleware(self, app, handler):
        async def middleware_handler(request):
            if request.path in ['/clients', '/notify']:
                peername = request.transport.get_extra_info('peername')
                if peername is not None:
                    ip = peername[0]
                    if not self.is_ip_allowed(ip):
                        self.logger.warning(f"Unauthorized access attempt from IP: {ip}")
                        return web.HTTPForbidden(text="403 Forbidden: Access denied")
            return await handler(request)
        return middleware_handler

    async def process_tts_queue(self):
        while True:
            text, session_id = await self.tts_queue.get()
            asyncio.create_task(self.process_tts_request(text, session_id))
            self.tts_queue.task_done()

    async def process_tts_request(self, text, code):
        # Generate the TTS audio
        self.logger.info(f"Processing TTS request for code {code} with text: {text}")
        response = self.generate_speech(text)
        if response is None:
            self.logger.error(f"Failed to generate speech for text: {text}")
            return
        audio_file = os.path.join(self.tts_dir, f'tts_output_{code}.mp3')
        with open(audio_file, 'wb') as out:
            out.write(response.audio_content)
            self.logger.info(f'Audio content written to file "{audio_file}"')
        # Transfer the file via SFTP
        await self.sftp_transfer(audio_file)
        # Emit the TTS audio to all clients associated with the API code
        sids = self.registered_clients.get(code, [])
        if sids:
            self.logger.info(f"Emitting TTS event to clients with code {code}")
            for sid in sids:
                self.logger.info(f"Emitting TTS event to SID {sid}")
                try:
                    # Ensure valid session ID and emit the event
                    if sid and isinstance(sid, dict) and 'sid' in sid:
                        await self.sio.emit("TTS", {"audio_file": f"https://tts.botofthespecter.com/{os.path.basename(audio_file)}"}, to=sid['sid'])
                    else:
                        self.logger.error(f"Invalid SID structure for code {code}: {sid}")
                except KeyError as e:
                    self.logger.error(f"KeyError while emitting TTS event: {e}")
        else:
            self.logger.error(f"No clients found with code {code}. Unable to emit TTS event.")
        # Estimate the duration of the audio and wait for it to finish
        duration = self.estimate_duration(response)
        self.logger.info(f"TTS event emitted. Waiting for {duration} seconds before continuing.")
        await asyncio.sleep(duration + 5)
        # After playback, delete the TTS file from the SFTP server
        try:
            await self.sftp_delete(audio_file)
            self.logger.info(f'Audio file "{audio_file}" successfully deleted from SFTP server.')
        except Exception as e:
            self.logger.error(f'Failed to delete audio file "{audio_file}" from SFTP server: {e}')

    async def sftp_transfer(self, local_file_path):
        # Set up the SFTP connection details from .env file
        hostname = "10.240.0.169"
        username = os.getenv("SFPT_USERNAME")
        password = os.getenv("SFPT_PASSWORD")
        remote_file_path = "/var/www/tts/" + os.path.basename(local_file_path)
        try:
            # Establish an SFTP session
            transport = paramiko.Transport((hostname, 22))
            transport.connect(username=username, password=password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            # Upload the file
            sftp.put(local_file_path, remote_file_path)
            self.logger.info(f"File {local_file_path} transferred to {remote_file_path} on webserver {hostname}")
            # Close the SFTP session
            sftp.close()
            transport.close()
        except Exception as e:
            self.logger.error(f"Failed to transfer file via SFTP: {e}")

    async def sftp_delete(self, local_file_path):
        # Set up the SFTP connection details from .env file
        hostname = "10.240.0.169"
        username = os.getenv("SFPT_USERNAME")
        password = os.getenv("SFPT_PASSWORD")
        remote_file_path = "/var/www/tts/" + os.path.basename(local_file_path)
        try:
            # Establish an SFTP session
            transport = paramiko.Transport((hostname, 22))
            transport.connect(username=username, password=password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            # Delete the file
            sftp.remove(remote_file_path)
            self.logger.info(f"File {remote_file_path} deleted from webserver {hostname}")
            # Close the SFTP session
            sftp.close()
            transport.close()
        except Exception as e:
            self.logger.error(f"Failed to delete file via SFTP: {e}")

    def estimate_duration(self, response):
        # Calculate the duration based on the audio content length and bitrate
        return len(response.audio_content) / 64000 # Duration in seconds for 64kbps MP3

    async def walkon(self, sid, data):
        # Handle the walkon event for SocketIO.
        self.logger.info(f"Walkon event from SID [{sid}]: {data}")
        channel = data.get('channel')
        user = data.get('user')
        if not channel or not user:
            self.logger.error('Missing channel or user information for WALKON event')
            return
        walkon_data = {
            'channel': channel,
            'user': user
        }
        # Broadcast the walkon event to all clients
        await self.sio.emit("WALKON", walkon_data)

    async def index(self, request):
        # Redirect to the main page
        raise web.HTTPFound(location="https://botofthespecter.com")
    
    async def heartbeat(self, request):
        if request.method == 'OPTIONS':
            response = web.Response(status=204)
        else:
            response = web.json_response({"status": "OK"})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    async def list_clients(self, request):
        # List the registered clients.
        return web.json_response(self.registered_clients)

    async def list_clients_event(self, sid):
        # Handle the LIST_CLIENTS event for SocketIO.
        self.logger.info(f"LIST_CLIENTS event from SID [{sid}]")
        await self.sio.emit("LIST_CLIENTS", self.registered_clients, to=sid)

    async def notify_http(self, request):
        code = request.query.get("code")
        event = request.query.get("event")
        text = request.query.get("text")
        if not code or not event:
            raise web.HTTPBadRequest(text="400 Bad Request: code or event is missing")
        data = {k: v for k, v in request.query.items()}
        self.logger.info(f"Notify request data: {data}")
        event = event.upper().replace(" ", "_")
        count = 0
        if event == "TTS" and text:
            await self.tts_queue.put((text, code))
            self.logger.info(f"TTS request added to queue: {text}")
        elif event == "FOURTHWALL":
            await self.handle_fourthwall_event(code, data)
        else:
            if code in self.registered_clients:
                for client in self.registered_clients[code]:
                    sid = client['sid']
                    await self.sio.emit(event, data, to=sid)
                    self.logger.info(f"Emitted event '{event}' to client {sid}")
                    count += 1
            self.logger.info(f"Broadcasted event to {count} clients")
        return web.json_response({"success": 1, "count": count, "msg": f"Broadcasted event to {count} clients"})

    async def handle_fourthwall_event(self, code, data):
        # Log and broadcast the FOURTHWALL event to the clients
        self.logger.info(f"Handling FOURTHWALL event with data: {data}")
        count = 0
        if code in self.registered_clients:
            for client in self.registered_clients[code]:
                sid = client['sid']
                await self.sio.emit("FOURTHWALL", data, to=sid)
                self.logger.info(f"Emitted FOURTHWALL event to client {sid}")
                count += 1
        self.logger.info(f"Broadcasted FOURTHWALL event to {count} clients")

    async def notify(self, sid, data):
        self.logger.info(f"Notify event from SID [{sid}]: {data}")
        event = data.get('event')

    async def notify(self, sid, data):
        self.logger.info(f"Notify event from SID [{sid}]: {data}")
        event = data.get('event')
        if not event:
            self.logger.error('Missing event information for NOTIFY event')
            return
        # Broadcast the event to all clients
        await self.sio.emit(event, data, sid)

    def generate_speech(self, text):
        input_text = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        try:
            response = self.tts_client.synthesize_speech(
                input=input_text, voice=voice, audio_config=audio_config
            )
            if not hasattr(response, 'audio_content'):
                raise ValueError("TTS API response does not contain audio content.")
            return response
        except Exception as e:
            self.logger.error(f"Failed to generate speech: {e}")
            return None

    async def event(self, sid, event, data):
        # Handle generic events for SocketIO.
        self.logger.debug(f"Event {event} from SID [{sid}]: {data}")

    async def connect(self, sid, environ, auth):
        # Handle the connect event for SocketIO.
        self.logger.info(f"Connect event: {sid}")
        if environ["REMOTE_ADDR"] in ['0.0.0.0', self.ip]:
            self.logger.debug(f"Client [{sid}] is a local user with elevated access")
        self.logger.debug(environ)
        await self.sio.emit("WELCOME", {"message": "Please register your code"}, to=sid)

    async def disconnect(self, sid):
        # Handle the disconnect event for SocketIO.
        self.logger.info(f"Disconnect event: {sid}")
        # Iterate through all registered clients and remove the disconnected SID
        for code, sids in list(self.registered_clients.items()):
            if sid in sids:
                sids.remove(sid)
                self.logger.info(f"Unregistered SID [{sid}] from code [{code}]")
                if not sids:
                    del self.registered_clients[code]
                    self.logger.info(f"No more clients for code [{code}]. Removed code from registered clients.")
                break
        else:
            self.logger.info(f"SID [{sid}] not found in registered clients.")
        # Log the current state of registered clients after disconnect
        self.logger.info(f"Current registered clients: {self.registered_clients}")

    async def register(self, sid, data):
        # Handle the register event for SocketIO.
        code = data.get("code")
        name = data.get("name", f"Unnamed-{sid}")
        self.logger.info(f"Register event received from SID {sid} with code: {code} and name: {name}")
        if code:
            # Initialize the list for the code if it doesn't exist
            if code not in self.registered_clients:
                self.registered_clients[code] = []
            # Check if there's already a client with the same name
            for client in self.registered_clients[code]:
                if client['name'] == name:
                    # Disconnect the old session
                    old_sid = client['sid']
                    self.logger.info(f"Disconnecting old session [{old_sid}] for name [{name}] before registering new session [{sid}]")
                    await self.sio.emit("ERROR", {"message": f"Disconnected: Duplicate session for name {name}"}, to=old_sid)
                    await self.sio.disconnect(old_sid)
                    # Remove the old client
                    self.registered_clients[code] = [c for c in self.registered_clients[code] if c['sid'] != old_sid]
                    break
            # Register the new client
            client_data = {"sid": sid, "name": name}
            self.registered_clients[code].append(client_data)
            self.logger.info(f"Client [{sid}] with name [{name}] registered with code: {code}")
            # Send success message to the new client
            await self.sio.emit("SUCCESS", {"message": "Registration successful", "code": code, "name": name}, to=sid)
            self.logger.info(f"Total registered clients for code {code}: {len(self.registered_clients[code])}")
        else:
            self.logger.warning("Code not provided during registration")
            await self.sio.emit("ERROR", {"message": "Registration failed: code missing"}, to=sid)
        # Log the current state of registered clients after registration
        self.logger.info(f"Current registered clients: {self.registered_clients}")

    async def deaths(self, sid, data):
        self.logger.info(f"Death event from SID [{sid}]: {data}")
        death_text = data.get('death-text')
        game = data.get('game')
        if not death_text or not game:
            self.logger.error('Missing death-text or game information for DEATHS event')
            return
        death_data = {
            'death-text': death_text,
            'game': game
        }
        self.logger.info(f"Broadcasting DEATHS event with data: {death_data}")
        # Broadcast the death event to all clients
        await self.sio.emit("DEATHS", death_data)

    async def tts(self, sid, data):
        self.logger.info(f"TTS event from SID [{sid}]: {data}")
        text = data.get("text")
        if text:
            await self.tts_queue.put((text, sid))
            self.logger.info(f"TTS request added to queue: {text}")

    async def twitch_follow(self, sid, data):
        # Handle the Twitch follow event for SocketIO.
        self.logger.info(f"Twitch follow event from SID [{sid}]: {data}")
        # Broadcast the follow event to all clients
        await self.sio.emit("TWITCH_FOLLOW", data)

    async def twitch_cheer(self, sid, data):
        # Handle the Twitch cheer event for SocketIO.
        self.logger.info(f"Twitch cheer event from SID [{sid}]: {data}")
        # Broadcast the cheer event to all clients
        await self.sio.emit("TWITCH_CHEER", data)

    async def twitch_raid(self, sid, data):
        # Handle the Twitch raid event for SocketIO.
        self.logger.info(f"Twitch raid event from SID [{sid}]: {data}")
        # Broadcast the raid event to all clients
        await self.sio.emit("TWITCH_RAID", data)

    async def twitch_sub(self, sid, data):
        # Handle the Twitch sub event for SocketIO.
        self.logger.info(f"Twitch sub event from SID [{sid}]: {data}")
        # Broadcast the sub event to all clients
        await self.sio.emit("TWITCH_SUB", data)

    async def stream_online(self, sid, data):
        # Handle the STREAM_ONLINE event for SocketIO.
        self.logger.info(f"Stream online event from SID [{sid}]: {data}")
        # Broadcast the stream online event to all clients
        await self.sio.emit("STREAM_ONLINE", data)

    async def stream_offline(self, sid, data):
        # Handle the STREAM_OFFLINE event for SocketIO.
        self.logger.info(f"Stream offline event from SID [{sid}]: {data}")
        # Broadcast the stream offline event to all clients
        await self.sio.emit("STREAM_OFFLINE", data)

    async def weather(self, sid, data):
        self.logger.info(f"Weather event from SID [{sid}]: {data}")
        weather_data = data.get("weather_data")
        if not weather_data:
            self.logger.error('Missing weather data for WEATHER event')
            return
        self.logger.info(f"Broadcasting WEATHER event with data: {weather_data}")
        # Broadcast the weather event to all clients
        await self.sio.emit("WEATHER", weather_data)

    async def weather_data(self, sid, data):
        self.logger.info(f"Weather data event from SID [{sid}]: {data}")
        weather_data = data.get("weather_data")
        if not weather_data:
            self.logger.error('Missing weather data for WEATHER_DATA event')
            return
        self.logger.info(f"Broadcasting WEATHER_DATA event with data: {weather_data}")
        # Broadcast the weather data event to all clients
        await self.sio.emit("WEATHER_DATA", weather_data)

    async def discord_join(self, sid, data):
        # Handle the DISCORD_JOIN event for SocketIO.
        self.logger.info(f"DISCORD_JOIN event from SID [{sid}]: {data}")
        member = data.get("member")
        if not member:
            self.logger.error("Missing member information for DISCORD_JOIN event")
            return
        join_data = {
            "member": member
        }
        # Broadcast the DISCORD_JOIN event to all clients
        await self.sio.emit("DISCORD_JOIN", join_data)

    async def sound_alert(self, sid, data):
        self.logger.info(f"Sound Alert event from SID [{sid}]: {data}")
        return

    async def send_notification(self, message):
        # Broadcast a notification to all registered clients
        for sid in self.registered_clients.keys():
            await self.sio.emit("NOTIFY", {"message": message}, to=sid)

    async def on_shutdown(self, app):
        self.logger.info("Shutting down...")
        # Disconnect all registered clients properly
        for code, sids in list(self.registered_clients.items()):
            for client in sids:
                sid = client['sid']
                self.logger.info(f"Disconnecting SID [{sid}] during shutdown.")
                try:
                    await self.sio.disconnect(sid)
                except Exception as e:
                    self.logger.error(f"Error disconnecting SID [{sid}]: {e}")
        self.logger.info("All clients disconnected.")

    def sig_handler(self, signum, frame):
        # Handle system signals for graceful shutdown.
        signame = signal.Signals(signum).name
        self.logger.info(f'Caught signal {signame} ({signum})')
        self.stop()
        self.logger.info("Server stopped")

    def run_app(self, host="0.0.0.0", port=443):
        # Run the web application.
        self.logger.info("=== Starting BotOfTheSpecter Websocket Server ===")
        self.logger.info(f"Host: {host} Port: {port}")
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.processing_task = self.loop.create_task(self.process_tts_queue())
        web.run_app(self.app, loop=self.loop, host=host, port=port, ssl_context=self.create_ssl_context(), handle_signals=True, shutdown_timeout=10)
    
    def stop(self):
        # Stop the SocketIO server.
        self.logger.info("Stopping SocketIO Server")
        future = asyncio.run_coroutine_threadsafe(self.sio.shutdown(), self.loop)
        try:
            future.result(5)
        except TimeoutError:
            self.logger.error("Timeout error - SocketIO Server didn't respond. Forcing close.")
        raise web.GracefulExit

    def create_ssl_context(self):
        # Create the SSL context for secure connections.
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile='/home/websocket/ssl/fullchain.pem', keyfile='/home/websocket/ssl/privkey.pem')
        return ssl_context

    @staticmethod
    def ext_to_content_type(ext, default="text/html"):
        # Get the content type based on file extension.
        content_types = {
            ".js": "text/javascript",
            ".css": "text/css",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".gif": "image/gif",
            ".ico": "image/vnd.microsoft.icon"
        }
        return content_types.get(ext, default)

    @staticmethod
    def get_own_ip():
        # Get the IP address of the current machine.
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)

if __name__ == '__main__':
    SCRIPT_DIR = os.path.dirname(__file__)
    parser = argparse.ArgumentParser(prog='BotOfTheSpecter Websocket Server', description='A WebSocket server for handling notifications and real-time communication between the website and the bot itself.')
    parser.add_argument("-H", "--host", default="0.0.0.0", help="Specify the listener host. Default is 0.0.0.0")
    parser.add_argument("-p", "--port", default=443, type=int, help="Specify the listener port number. Default is 443")
    parser.add_argument("-l", "--loglevel", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Specify the log level. INFO is the default.")
    parser.add_argument("-f", "--logfile", help="Specify log file location. Production location should be <WEBROOT>/log/noti_server.log")
    args = parser.parse_args()
    log_level = logging.getLevelName(args.loglevel)
    log_file = args.logfile if args.logfile else os.path.join(SCRIPT_DIR, "noti_server.log")
    logging.basicConfig(filename=log_file, level=log_level, filemode="a", format="%(asctime)s - %(levelname)s - %(message)s")
    logging.getLogger().addHandler(logging.StreamHandler())
    server = BotOfTheSpecterWebsocketServer(logging)
    server.run_app(host=args.host, port=args.port)