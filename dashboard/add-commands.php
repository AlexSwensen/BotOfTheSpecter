<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

// Initialize the session
session_start();

// check if user is logged in
if (!isset($_SESSION['access_token'])) {
    header('Location: login.php');
    exit();
}

// Page Title
$title = "Add Bot Commands";

// Connect to database
require_once "db_connect.php";

// Fetch the user's data from the database based on the access_token
$access_token = $_SESSION['access_token'];
$userSTMT = $conn->prepare("SELECT * FROM users WHERE access_token = ?");
$userSTMT->bind_param("s", $access_token);
$userSTMT->execute();
$userResult = $userSTMT->get_result();
$user = $userResult->fetch_assoc();
$user_id = $user['id'];
$username = $user['username'];
$twitchDisplayName = $user['twitch_display_name'];
$twitch_profile_image_url = $user['profile_image'];
$is_admin = ($user['is_admin'] == 1);
$twitchUserId = $user['twitch_user_id'];
$authToken = $access_token;
$refreshToken = $user['refresh_token'];
$timezone = 'Australia/Sydney';
date_default_timezone_set($timezone);
$greeting = 'Hello';
include 'bot_control.php';
include 'sqlite.php';

if ($_SERVER["REQUEST_METHOD"] == "POST") {
    if (isset($_POST['command']) && isset($_POST['response'])) {
        $newCommand = $_POST['command'];
        $newResponse = $_POST['response'];
        
        // Insert new command into MySQL database
        try {
            $stmt = $db->prepare("INSERT INTO custom_commands (command, response, status) VALUES (?, ?, 'Enabled')");
            $stmt->execute([$newCommand, $newResponse]);
        } catch (PDOException $e) {
            echo 'Error adding command: ' . $e->getMessage();
        }
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <!-- Header -->
    <?php include('header.php'); ?>
    <style>
        .custom-width { width: 90vw; max-width: none; }
        .variable-item { margin-bottom: 1.5rem; }
        .variable-title { color: #ffdd57; }
    </style>
    <!-- /Header -->
</head>
<body>
<!-- Navigation -->
<?php include('navigation.php'); ?>
<!-- /Navigation -->
<div class="container">
    <h1 class="title"><?php echo "$greeting, $twitchDisplayName <img id='profile-image' class='round-image' src='$twitch_profile_image_url' width='50px' height='50px' alt='$twitchDisplayName Profile Image'>"; ?></h1>
    <br>
    <div class="columns">
        <div class="column">
            <form method="post" action="">
                <div class="field">
                    <label class="label" for="command">Command:</label>
                    <div class="control">
                        <input class="input" type="text" name="command" id="command" required>
                    </div>
                </div>
                <div class="field">
                    <label class="label" for="response">Response:</label>
                    <div class="control">
                        <input class="input" type="text" name="response" id="response" required>
                    </div>
                </div>
                <div class="control">
                    <button class="button is-primary" type="submit">Add Command</button>
                </div>
            </form>
            <br>
            <?php if ($_SERVER["REQUEST_METHOD"] == "POST"): ?>
                <?php if (isset($_POST['command']) && isset($_POST['response'])): ?>
                    <p class="has-text-success">Command "<?php echo $_POST['command']; ?>" has been successfully added to the database.</p>
                <?php endif; ?>
            <?php endif; ?>
        </div>
    </div>
    <div class="columns">
        <div class="column">
            <h3 class='has-text-info'>
                When adding commands via this site, please note the following:<br>
                <ul>
                    <li>Avoid using the exclamation mark (!) in your command. This will be automatically added.</li>
                    <li>Alternatively, you or your moderators can add commands during a stream using the command !addcommand.<br>
                        Example: <code>!addcommand mycommand This is my command</code></li>
                </ul>
            </h3>
        </div>
        <div class="column">
            <button class="button is-info" id="openModalButton">View Custom Variables</button>
            <div class="modal" id="customVariablesModal">
                <div class="modal-background"></div>
                <div class="modal-card custom-width">
                    <header class="modal-card-head has-background-dark">
                        <p class="modal-card-title has-text-white">Custom Variables to use while adding commands</p>
                        <button class="delete" aria-label="close" id="closeModalButton"></button>
                    </header>
                    <section class="modal-card-body has-background-dark has-text-white">
                        <div class="columns is-desktop is-multiline">
                            <div class="column is-4">
                                <span class="has-text-weight-bold variable-title">(count)</span>: This counts how many times the command has been used and shows that number.
                                <br><span class="has-text-weight-bold">Example:</span> <code>This command has been used (count) times.</code>
                                <br><span class="has-text-weight-bold">In Twitch Chat:</span> "This command has been used 5 times."
                            </div>
                            <div class="column is-4">
                                <span class="has-text-weight-bold variable-title">(customapi.URL)</span>: This gets information from a URL and posts it in chat. You can use this to get jokes, weather, or any other data from a website.
                                <br><span class="has-text-weight-bold">Example:</span> <code>(customapi.https://api.botofthespecter.com/joke?api_key=APIKEY)</code>
                                <br><span class="has-text-weight-bold">In Twitch Chat:</span> "Why don’t skeletons fight each other? They don’t have the guts."
                            </div>
                            <div class="column is-4">
                                <span class="has-text-weight-bold variable-title">(daysuntil.DATE)</span>: This shows how many days until a specific date, like a holiday or event.
                                <br><span class="has-text-weight-bold">Example:</span> <code>There are (daysuntil.2024-12-25) days until Christmas.</code>
                                <br><span class="has-text-weight-bold">In Twitch Chat:</span> "There are 75 days until Christmas."
                            </div>
                            <div class="column is-4">
                                <span class="has-text-weight-bold variable-title">(user)</span>: This lets you tag someone by name when they use the command. If no one is tagged, it will tag the person who used the command.
                                <br><span class="has-text-weight-bold">Example:</span> <code>(user) is awesome!</code>
                                <br><span class="has-text-weight-bold">In Twitch Chat:</span> "BotOfTheSpecter is awesome!"
                            </div>
                            <div class="column is-4">
                                <span class="has-text-weight-bold variable-title">(command.COMMAND)</span>: This allows you to trigger other commands inside of one command. You can combine multiple commands to post different messages.
                                <br><span class="has-text-weight-bold">Example:</span> <code>Use these raid calls: (command.raid1) (command.raid2) (command.raid3)</code>
                                <br><span class="has-text-weight-bold">In Twitch Chat:</span> 
                                <br> "Use these raid calls:"
                                <br> "Raid 1 message."
                                <br> "Raid 2 message."
                                <br> "Raid 3 message."
                            </div>
                            <div class="column is-4">
                                <span class="has-text-weight-bold variable-title">(random.percent)</span>: This generates a random percentage between 0% and 100%, or any custom range you define.
                                <br><span class="has-text-weight-bold">Example:</span> <code>You have a (random.percent) chance of winning this game.</code>
                                <br><span class="has-text-weight-bold">In Twitch Chat:</span> "You have a 67% chance of winning this game."
                            </div>
                            <div class="column is-4">
                                <span class="has-text-weight-bold variable-title">(random.number)</span>: This picks a random number between two numbers you specify, or by default between 0 and 100.
                                <br><span class="has-text-weight-bold">Example:</span> <code>You've broken (random.number) hearts!</code>
                                <br><span class="has-text-weight-bold">In Twitch Chat:</span> "You've broken 42 hearts!"
                            </div>
                            <div class="column is-4">
                                <span class="has-text-weight-bold variable-title">(random.pick.*)</span>: This randomly picks an item from a list you provide. It could be used to pick random items, people, or anything else.
                                <br><span class="has-text-weight-bold">Example:</span> <code>Your spirit animal is: (random.pick.cat.dog.eagle.tiger)</code>
                                <br><span class="has-text-weight-bold">In Twitch Chat:</span> "Your spirit animal is: tiger"
                            </div>
                            <div class="column is-4">
                                <span class="has-text-weight-bold variable-title">(math.*)</span>: This solves simple math problems.
                                <br><span class="has-text-weight-bold">Example:</span> <code>2+2 = (math.2+2)</code>
                                <br><span class="has-text-weight-bold">In Twitch Chat:</span> "2+2 = 4"
                            </div>
                        </div>
                    </section>
                </div>
            </div>
        </div>
    </div>
</div>

<script src="https://code.jquery.com/jquery-2.1.4.min.js"></script>
<script>
document.getElementById("openModalButton").addEventListener("click", function() {
    document.getElementById("customVariablesModal").classList.add("is-active");
});
document.getElementById("closeModalButton").addEventListener("click", function() {
    document.getElementById("customVariablesModal").classList.remove("is-active");
});
document.getElementById("closeModalButtonFooter").addEventListener("click", function() {
    document.getElementById("customVariablesModal").classList.remove("is-active");
});
</script>
</body>
</html>