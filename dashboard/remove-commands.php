<?php 
// Initialize the session
session_start();

// Check if the user is logged in
if (!isset($_SESSION['access_token'])) {
    header('Location: login.php');
    exit();
}

// Page Title
$title = "Remove Custom Commands";

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
$greeting = 'Hello';

// Fetch all custom commands from the database
$commands = [];
try {
    $stmt = $db->query("SELECT command FROM custom_commands");
    $commands = $stmt->fetchAll(PDO::FETCH_ASSOC);
} catch (PDOException $e) {
    $status = "Error fetching commands: " . $e->getMessage();
}

// Check if the form was submitted
if ($_SERVER['REQUEST_METHOD'] == 'POST' && isset($_POST['remove_command'])) {
    $commandToRemove = $_POST['remove_command'];

    // Prepare a delete statement
    $deleteStmt = $db->prepare("DELETE FROM custom_commands WHERE command = ?");
    $deleteStmt->bindParam(1, $commandToRemove, PDO::PARAM_STR);

    // Execute the delete statement
    try {
        $deleteStmt->execute();
        // Success message 
        $status = "Command removed successfully";

        // Reload the page after 1 seconds
        header("Refresh: 1; url={$_SERVER['PHP_SELF']}");
        exit();
    } catch (PDOException $e) {
        // Handle potential errors here
        $status = "Error removing command: " . $e->getMessage();
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
  <?php if (!empty($commands)): ?>
    <p class="has-text-white">Select the command you want to remove:</p>
    <form method="post" action="">
        <div class="field">
            <label class="label" for="remove_command">Command to Remove:</label>
            <div class="control">
                <div class="select">
                    <select name="remove_command" id="remove_command" required>
                        <?php foreach ($commands as $command): ?>
                            <option value="<?php echo htmlspecialchars($command['command']); ?>">!<?php echo htmlspecialchars($command['command']); ?></option>
                        <?php endforeach; ?>
                    </select>
                </div>
            </div>
        </div>
        <div class="control"><button type="submit" class="button is-danger">Remove Command</button></div>
    </form>
  <?php else: ?>
    <p>No commands to remove.</p>
  <?php endif; ?>
  <?php if (!empty($status)): ?>
    <div class="notification is-primary">
      <?php echo htmlspecialchars($status); ?>
    </div>
  <?php endif; ?>
</div>

<script src="https://code.jquery.com/jquery-2.1.4.min.js"></script>
</body>
</html>