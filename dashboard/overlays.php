<?php 
// Initialize the session
session_start();

// Check if the user is logged in
if (!isset($_SESSION['access_token'])) {
    header('Location: login.php');
    exit();
}

// Page Title
$title = "Overlays";

// Include all the information
require_once "db_connect.php";
include 'userdata.php';
include 'bot_control.php';
include 'sqlite.php';
foreach ($profileData as $profile) {
  $timezone = $profile['timezone'];
  $weather = $profile['weather_location'];
}
date_default_timezone_set($timezone);
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <!-- Header -->
    <?php include('header.php'); ?>
    <!-- /Header -->
</head>
<body>
<!-- Navigation -->
<?php include('navigation.php'); ?>
<!-- /Navigation -->

<div class="container">
    <br>
    <div class="notification is-info">
        This system is fully compatible with all popular streaming software, including OBS Studio, Streamlabs OBS, XSplit Broadcaster, Wirecast, vMix, Lightstream, and more.<br>
        To integrate with your streaming setup, simply add one or more of the following links to a browser source in your streaming software.<br>
        Your API key is unique to you and acts as a password to access your overlays, so it must be kept secure and private.<br>
        You can find your API key on your profile page in the Specter Dashboard, which is accessible via the link in the navigation bar above.<br>
        Be sure to replace `API_KEY_HERE` in each URL below with your actual key.
    </div>
    <br>
    <div class="columns is-desktop is-multiline">
        <div class="column is-full">
            <!-- All the Overlays -->
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">All Overlays:</h4>
                <p><em>This URL includes all overlays we offer, automatically added and updated.
                    <br>The only exception is the Stream Ending Credits & To Do List, which must be added separately.
                    <br>Add this link once, and any new overlays will be included automatically:</em></p>
                <code>https://overlay.botofthespecter.com/?code=API_KEY_HERE</code>
            </div>
        </div>
        <!-- Stream Ending Credits Overlay -->
        <div class="column is-half">
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">Stream Ending Credits:</h4>
                <p><em>The Stream Ending Credits display a scrolling list of all viewers who attended and supported the stream.
                    <br>This includes followers, subscribers, donors, and cheerers to thank those who contributed.
                    <br>(Coming Soon)</em></p>
                <code>https://overlay.botofthespecter.com/credits.php?code=API_KEY_HERE</code>
            </div>
        </div>
        <!-- To Do List Overlay -->
        <div class="column is-half">
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">To Do List:</h4>
                <p><em>Display a list of tasks to complete during the stream.
                    <br>This overlay helps you keep track of your goals and share them with your audience.
                    <br>You can specify a category by adding it to the URL like this:
                    <br>todolist.php?code=API_KEY&category=1</em></p>
                <code>https://overlay.botofthespecter.com/todolist.php?code=API_KEY_HERE</code>
            </div>
        </div>
        <!-- Death Overlay -->
        <div class="column is-half">
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">Death Overlay Only:</h4>
                <p><em>Show only the death overlay for the death commands triggered in chat:
                    <br>"!deaths", "!deathadd", and "!deathremove".
                    <br>For best results, set Width to 450 and Height to 350:</em></p>
                <code>https://overlay.botofthespecter.com/deaths.php?code=API_KEY_HERE</code>
            </div>
        </div>
        <!-- Weather Overlay -->
        <div class="column is-half">
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">Weather Overlay:</h4>
                <p><em>Show current weather information for your specified location in your stream.
                    <br>To use this overlay, add the following URL as a browser source and append your API key.</em></p>
                <code>https://overlay.botofthespecter.com/weather.php?code=API_KEY_HERE</code>
            </div>
        </div>
        <!-- Discord Join Notifications Overlay -->
        <div class="column is-half">
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">Discord Join Notifications:</h4>
                <p><em>Display notifications when a user joins your Discord server.
                    <br>Add this URL as a browser source and append your API key.</em></p>
                <code>https://overlay.botofthespecter.com/discord.php?code=API_KEY_HERE</code>
            </div>
        </div>
        <!-- Subathon Overlay -->
        <div class="column is-half">
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">Subathon:</h4>
                <p><em>Show a countdown timer for a subathon.
                    <br>Add this URL as a browser source and append your API key.</em></p>
                <code>https://overlay.botofthespecter.com/subathon.php?code=API_KEY_HERE</code>
            </div>
        </div>
        <!-- All Audio Overlays -->
        <div class="column is-half">
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">All Audio:</h4>
                <p><em>This URL includes all audio alerts we offer, automatically updated.
                    <br>Add this link once to include any new audio alerts automatically.</em></p>
                <code>https://overlay.botofthespecter.com/alert.php?code=API_KEY_HERE</code>
            </div>
        </div>
        <!-- TTS Only Overlay -->
        <div class="column is-half">
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">Text To Speech (TTS) Only:</h4>
                <p><em>Only hear the Text To Speech audio.</em></p>
                <code>https://overlay.botofthespecter.com/tts.php?code=API_KEY_HERE</code>
            </div>
        </div>
        <!-- Walkons Only Overlay -->
        <div class="column is-half">
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">Walkons Only:</h4>
                <p><em>Only hear Walkon audio set for each user.</em></p>
                <code>https://overlay.botofthespecter.com/walkons.php?code=API_KEY_HERE</code>
            </div>
        </div>
        <!-- Sound Alerts Only Overlay -->
        <div class="column is-half">
            <div class="box" style="height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <h4 class="title is-4">Sound Alerts Only:</h4>
                <p><em>Only hear the sound alerts for each channel point reward.</em></p>
                <code>https://overlay.botofthespecter.com/sound-alert.php?code=API_KEY_HERE</code>
            </div>
        </div>
    </div>
    <br>
</div>

<!-- Include the JavaScript files -->
<script src="https://code.jquery.com/jquery-2.1.4.min.js"></script>
</body>
</html>