<?php ini_set('display_errors', 1); ini_set('display_startup_errors', 1); error_reporting(E_ALL); ?>
<?php
// Initialize the session
session_start();

// check if user is logged in
if (!isset($_SESSION['access_token'])) {
    header('Location: login.php');
    exit();
}

// Page Title
$title = "Bot Counters";

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
$webhookPort = $user['webhook_port'];
$websocketPort = $user['websocket_port'];
$timezone = 'Australia/Sydney';
date_default_timezone_set($timezone);
$greeting = 'Hello';
include 'bot_control.php';
include 'sqlite.php';
$countType = '';
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
  <div class="tabs is-boxed is-centered" id="countTabs">
    <ul>
      <li class="<?php echo $countType === 'lurking' ? 'is-active' : ''; ?>"><a href="?countType=lurking#lurking">Currently Lurking Users</a></li>
      <li class="<?php echo $countType === 'typo' ? 'is-active' : ''; ?>"><a href="?countType=typo#typo">Typo Counts</a></li>
      <li class="<?php echo $countType === 'deaths' ? 'is-active' : ''; ?>"><a href="?countType=deaths#deaths">Deaths Overview</a></li>
      <li class="<?php echo $countType === 'hugs' ? 'is-active' : ''; ?>"><a href="?countType=hugs#hugs">Hug Counts</a></li>
      <li class="<?php echo $countType === 'kisses' ? 'is-active' : ''; ?>"><a href="?countType=kisses#kisses">Kiss Counts</a></li>
      <li class="<?php echo $countType === 'custom' ? 'is-active' : ''; ?>"><a href="?countType=custom#custom">Custom Counts</a></li>
    </ul>
  </div>
  <div class="content">
    <div class="tabs-content">
      <div class="tab-content <?php echo $countType === 'lurking' ? 'is-active' : ''; ?>" id="lurking">
        <h3>Currently Lurking Users</h3>
        <table class="table is-striped is-fullwidth">
          <thead>
            <tr>
              <th>Username</th>
              <th>Lurk Duration</th>
            </tr>
          </thead>
          <tbody>
            <?php foreach ($lurkers as $lurker): $displayName = $usernames[$lurker['user_id']] ?? $lurker['user_id']; ?>
            <tr>
              <td id="<?php echo $lurker['user_id']; ?>"><?php echo htmlspecialchars($displayName); ?></td>
              <td id="lurk_duration"><?php echo htmlspecialchars($lurker['lurk_duration']); ?></td>
            </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </div>
      <div class="tab-content <?php echo $countType === 'typo' ? 'is-active' : ''; ?>" id="typo">
        <h3>Typo Counts</h3>
        <table class="table is-striped is-fullwidth">
          <thead>
            <tr>
              <th>Username</th>
              <th>Typo Count</th>
            </tr>
          </thead>
          <tbody>
            <?php foreach ($typos as $typo): ?>
            <tr>
              <td><?php echo htmlspecialchars($typo['username']); ?></td>
              <td><?php echo htmlspecialchars($typo['typo_count']); ?></td>
            </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </div>
      <div class="tab-content <?php echo $countType === 'deaths' ? 'is-active' : ''; ?>" id="deaths">
        <h3>Deaths Overview</h3>
        <table class="table is-striped is-fullwidth">
          <thead>
            <tr>
              <th>Category</th>
              <th>Count</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Total Deaths</td>
              <td><?php echo htmlspecialchars($totalDeaths['death_count'] ?? '0'); ?></td>
            </tr>
            <?php foreach ($gameDeaths as $gameDeath): ?>
            <tr>
              <td><?php echo htmlspecialchars($gameDeath['game_name']); ?></td>
              <td><?php echo htmlspecialchars($gameDeath['death_count']); ?></td>
            </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </div>
      <div class="tab-content <?php echo $countType === 'hugs' ? 'is-active' : ''; ?>" id="hugs">
        <h3>Hug Counts</h3>
        <table class="table is-striped is-fullwidth">
          <thead>
            <tr>
              <th>Username</th>
              <th>Hug Count</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Total Hugs</td>
              <td><?php echo htmlspecialchars($totalHugs['total_hug_count'] ?? '0'); ?></td>
            </tr>
            <?php foreach ($hugCounts as $hugCount): ?>
            <tr>
              <td><?php echo htmlspecialchars($hugCount['username']); ?></td>
              <td><?php echo htmlspecialchars($hugCount['hug_count']); ?></td>
            </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </div>
      <div class="tab-content <?php echo $countType === 'kisses' ? 'is-active' : ''; ?>" id="kisses">
        <h3>Kiss Counts</h3>
        <table class="table is-striped is-fullwidth">
          <thead>
            <tr>
              <th>Username</th>
              <th>Kiss Count</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Total Kisses</td>
              <td><?php echo htmlspecialchars($totalKisses['total_kiss_count'] ?? '0'); ?></td>
            </tr>
            <?php foreach ($kissCounts as $kissCount): ?>
            <tr>
              <td><?php echo htmlspecialchars($kissCount['username']); ?></td>
              <td><?php echo htmlspecialchars($kissCount['kiss_count']); ?></td>
            </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </div>
      <div class="tab-content <?php echo $countType === 'custom' ? 'is-active' : ''; ?>" id="custom">
        <h3>Custom Counts</h3>
        <table class="table is-striped is-fullwidth">
          <thead>
            <tr>
              <th>Command</th>
              <th>Count</th>
            </tr>
          </thead>
          <tbody>
            <?php foreach ($customCounts as $customCount): ?>
            <tr>
              <td><?php echo htmlspecialchars($customCount['command']); ?></td>
              <td><?php echo htmlspecialchars($customCount['count']); ?></td>
            </tr>
            <?php endforeach; ?>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', () => {
  // Get all "navbar-burger" elements
  const $navbarBurgers = Array.prototype.slice.call(document.querySelectorAll('.navbar-burger'), 0);
  // Check if there are any navbar burgers
  if ($navbarBurgers.length > 0) {
    // Add a click event on each of them
    $navbarBurgers.forEach(el => {
      el.addEventListener('click', () => {
        // Get the target from the "data-target" attribute
        const target = el.dataset.target;
        const $target = document.getElementById(target);
        // Toggle the "is-active" class on both the "navbar-burger" and the "navbar-menu"
        el.classList.toggle('is-active');
        $target.classList.toggle('is-active');
      });
    });
  }
});
document.addEventListener('DOMContentLoaded', () => {
  const tabs = document.querySelectorAll('#countTabs li a');
  const tabContents = document.querySelectorAll('.tab-content');
  tabs.forEach(tab => {
    tab.addEventListener('click', (event) => {
      event.preventDefault();
      const target = tab.getAttribute('href').substring(1);
      tabs.forEach(item => item.parentElement.classList.remove('is-active'));
      tabContents.forEach(content => content.classList.remove('is-active'));
      tab.parentElement.classList.add('is-active');
      document.getElementById(target).classList.add('is-active');
      history.pushState(null, null, `?countType=${target}#${target}`);
    });
  });

  // Activate the tab based on the URL parameter
  if (window.location.search) {
    const params = new URLSearchParams(window.location.search);
    const countType = params.get('countType');
    if (countType) {
      const initialTab = document.querySelector(`#countTabs li a[href="#${countType}"]`).parentElement;
      initialTab.classList.add('is-active');
      document.getElementById(countType).classList.add('is-active');
    }
  } else {
    // Default to the first tab
    const defaultTab = tabs[0].parentElement;
    defaultTab.classList.add('is-active');
    document.getElementById(defaultTab.querySelector('a').getAttribute('href').substring(1)).classList.add('is-active');
  }
});
</script>
<script src="https://code.jquery.com/jquery-2.1.4.min.js"></script>
</body>
</html>