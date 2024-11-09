<?php 
// Initialize the session
session_start();

// Check if the user is logged in
if (!isset($_SESSION['access_token'])) {
    header('Location: login.php');
    exit();
}

// Page Title
$title = "Chat Protection";

// Connect to database
require_once "db_connect.php";

// Fetch the user's data from the database based on the access_token
$access_token = $_SESSION['access_token'];
$stmt = $conn->prepare("SELECT * FROM users WHERE access_token = ?");
$stmt->bind_param("s", $access_token);
$stmt->execute();
$result = $stmt->get_result();
$user = $result->fetch_assoc();
$user_id = $user['id'];
$username = $user['username'];
$broadcasterID = $user['twitch_user_id'];
$twitchDisplayName = $user['twitch_display_name'];
$twitch_profile_image_url = $user['profile_image'];
$is_admin = ($user['is_admin'] == 1);
$authToken = $access_token;
$refreshToken = $user['refresh_token'];
$timezone = 'Australia/Sydney';
date_default_timezone_set($timezone);
$greeting = 'Hello';
include 'bot_control.php';
include 'sqlite.php';
$message = '';

// Fetch protection settings
$getProtection = $db->query("SELECT * FROM protection LIMIT 1");
$settings = $getProtection->fetchAll(PDO::FETCH_ASSOC);
$currentSettings = isset($settings[0]['url_blocking']) ? $settings[0]['url_blocking'] : 'False';

// Update database with settings
if ($_SERVER["REQUEST_METHOD"] == "POST") {
    // URL Blocking Settings
    if (isset($_POST['url_blocking'])) {
        $url_blocking = $_POST['url_blocking'] == 'True' ? 'True' : 'False';
        $stmt = $db->prepare("UPDATE protection SET url_blocking = ?");
        $stmt->bindParam(1, $url_blocking, PDO::PARAM_STR);
        if ($stmt->execute()) {
            $message .= "URL Blocking setting updated successfully.<br>";
        } else {
            $message .= "Failed to update your URL Blocking settings.<br>";
            error_log("Error updating URL blocking: " . implode(", ", $stmt->errorInfo()));
        }
    } else {
        $message .= "Please select either True or False.<br>";
    }

    // Whitelist Links
    if (isset($_POST['whitelist_link'])) {
        $whitelist_link = $_POST['whitelist_link'];
        $stmt = $db->prepare("INSERT INTO link_whitelist (link) VALUES (?)");
        $stmt->bindParam(1, $whitelist_link, PDO::PARAM_STR);
        if ($stmt->execute()) {
            $message .= "Link added to the whitelist.<br>";
        } else {
            $message .= "Failed to add the link to the whitelist.<br>";
            error_log("Error inserting whitelist link: " . implode(", ", $stmt->errorInfo()));
        }
    }

    // Blacklist Links
    if (isset($_POST['blacklist_link'])) {
        $blacklist_link = $_POST['blacklist_link'];
        $stmt = $db->prepare("INSERT INTO link_blacklisting (link) VALUES (?)");
        $stmt->bindParam(1, $blacklist_link, PDO::PARAM_STR);
        if ($stmt->execute()) {
            $message .= "Link added to the blacklist.<br>";
        } else {
            $message .= "Failed to add the link to the blacklist.<br>";
            error_log("Error inserting blacklist link: " . implode(", ", $stmt->errorInfo()));
        }
    }
}
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
    <h1 class="title"><?php echo "$greeting, $twitchDisplayName <img id='profile-image' class='round-image' src='$twitch_profile_image_url' width='50px' height='50px' alt='$twitchDisplayName Profile Image'>"; ?></h1>
    <br>
    <h1 class="title">Chat Protection</h1>
    <?php if (!empty($message)): ?>
        <div class="notification is-primary has-text-black has-text-weight-bold">
            <?php echo $message; ?>
        </div>
    <?php endif; ?>
    <!-- Enable or Disable URL Blocking -->
    <form action="" method="post">
        <div class="field">
            <label for="url_blocking">Enable URL Blocking:</label>
            <div class="control">
                <div class="select">
                    <select name="url_blocking" id="url_blocking">
                        <option value="True"<?php echo $currentSettings == 'True' ? ' selected' :'';?>>True</option>
                        <option value="False"<?php echo $currentSettings == 'False' ? ' selected' :'';?>>False</option>
                    </select>
                </div>
            </div>
        </div>
        <div class="field">
            <input type="submit" name="submit" value="Update"></input>
        </div>
    </form>
    <br>
    <!-- Add a new link to the White List -->
    <form action="" method="post">
        <div class="field">
            <label for="whitelist_link">Enter Link to Whitelist:</label>
            <div class="control">
                <input class="input" type="url" name="whitelist_link" id="whitelist_link" placeholder="Enter a URL" required>
            </div>
        </div>
        <div class="field">
            <input type="submit" name="submit" value="Add to Whitelist"></input>
        </div>
    </form>
    <br>
    <!-- Add a new link to the Black List -->
    <form action="" method="post">
        <div class="field">
            <label for="blacklist_link">Enter Link to Blacklist:</label>
            <div class="control">
                <input class="input" type="url" name="blacklist_link" id="blacklist_link" placeholder="Enter a URL" required>
            </div>
        </div>
        <div class="field">
            <input type="submit" name="submit" value="Add to Blacklist"></input>
        </div>
    </form>
</div>

<script src="https://code.jquery.com/jquery-2.1.4.min.js"></script>
</body>
</html>