<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WebSocket Audio Notifications</title>
    <link rel="stylesheet" href="index.css">
    <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', () => {
            let socket;
            const retryInterval = 5000;
            let reconnectAttempts = 0;
            const urlParams = new URLSearchParams(window.location.search);
            const code = urlParams.get('code');

            if (!code) {
                alert('No code provided in the URL');
                return;
            }

            function connectWebSocket() {
                socket = io('wss://websocket.botofthespecter.com', {
                    reconnection: false
                });

                socket.on('connect', () => {
                    console.log('Connected to WebSocket server');
                    reconnectAttempts = 0;
                    socket.emit('REGISTER', { code: code, name: 'All Audio Overlay' });
                });

                socket.on('disconnect', () => {
                    console.log('Disconnected from WebSocket server');
                    attemptReconnect();
                });

                socket.on('connect_error', (error) => {
                    console.error('Connection error:', error);
                    attemptReconnect();
                });

                socket.on('WELCOME', (data) => {
                    console.log('Server says:', data.message);
                });

                socket.on('NOTIFY', (data) => {
                    console.log('Notification:', data);
                    alert(data.message);
                });

                // Function to play audio with error handling
                const playAudio = (audioFile) => {
                    if (!audioFile) return;
                    // Add cache-busting query parameter with timestamp
                    const audio = new Audio(`${audioFile}?t=${new Date().getTime()}`);
                    audio.volume = 0.8;
                    audio.autoplay = true;

                    audio.addEventListener('canplaythrough', () => {
                        console.log('Audio can play through without buffering');
                        audio.play().catch(error => {
                            console.error('Error playing audio:', error);
                            alert('Click to play audio');
                        });
                    });

                    audio.addEventListener('error', (e) => {
                        console.error('Error occurred while loading the audio file:', e);
                        alert('Failed to load audio file');
                    });
                };

                // Listen for TTS audio events
                socket.on('TTS', (data) => {
                    console.log('TTS Audio file path:', data.audio_file);
                    playAudio(data.audio_file);
                });

                // Listen for WALKON events
                socket.on('WALKON', (data) => {
                    console.log('Walkon:', data);
                    const audioFile = `https://walkons.botofthespecter.com/${data.channel}/${data.user}.mp3`;
                    playAudio(audioFile);
                });

                // Handle user interaction to allow audio playback if blocked
                document.body.addEventListener('click', () => {
                    playAudio();
                }, { once: true });
            }

            function attemptReconnect() {
                reconnectAttempts++;
                const delay = Math.min(retryInterval * reconnectAttempts, 30000);
                console.log(`Attempting to reconnect in ${delay / 1000} seconds...`);
                setTimeout(() => {
                    connectWebSocket();
                }, delay);
            }

            // Start initial connection
            connectWebSocket();
        });
    </script>
</head>
<body>
</body>
</html>