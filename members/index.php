<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

// Initialize the session
session_start();

// Initialize all variables as empty arrays or values
$commands = [];
$builtinCommands = [];
$typos = [];
$lurkers = [];
$watchTimeData = [];
$totalDeaths = [];
$gameDeaths = [];
$totalHugs = 0;
$hugCounts = [];
$totalKisses = 0;
$kissCounts = [];
$customCounts = [];
$userCounts = [];
$seenUsersData = [];
$timedMessagesData = [];
$channelPointRewards = [];
$profileData = [];
$todos = [];

// Check if the user is logged in
if (!isset($_SESSION['access_token'])) {
    $_SESSION['redirect_url'] = $_SERVER['REQUEST_URI'];
    header('Location: logout.php');
    exit();
}

// Function to sanitize input
function sanitize_input($input) {
    return htmlspecialchars(trim($input));
}

// Function to fetch usernames from Twitch API using user_id
function getTwitchUsernames($userIds) {
    $clientID = 'mrjucsmsnri89ifucl66jj1n35jkj8';
    $accessToken = sanitize_input($_SESSION['access_token']);
    $twitchApiUrl = "https://api.twitch.tv/helix/users?id=" . implode('&id=', array_map('sanitize_input', $userIds));
    $headers = [
        "Client-ID: $clientID",
        "Authorization: Bearer $accessToken",
    ];
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $twitchApiUrl);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    $response = curl_exec($ch);
    if ($response === false) {
        // Handle cURL error
        error_log('cURL Error: ' . curl_error($ch));
        curl_close($ch);
        return false;
    }
    curl_close($ch);
    $decodedResponse = json_decode($response, true);
    if (isset($decodedResponse['error'])) {
        // Handle API error
        error_log('Twitch API Error: ' . $decodedResponse['message']);
        return [];
    }
    $usernames = [];
    foreach ($decodedResponse['data'] as $user) {
        $usernames[] = $user['display_name'];
    }
    return $usernames;
}

// PAGE TITLE
$title = "Members";

// Database credentials
$dbHost = 'sql.botofthespecter.com';
$dbUsername = 'USERNAME';
$dbPassword = 'PASSWORD';

$path = trim($_SERVER['REQUEST_URI'], '/');
$path = parse_url($path, PHP_URL_PATH);
$username = isset($_GET['user']) ? sanitize_input($_GET['user']) : null;
$page = isset($_GET['page']) ? sanitize_input($_GET['page']) : null;
$buildResults = "Welcome " . $_SESSION['display_name'];
$notFound = false;

if ($username) {
    try {
        $checkDb = new mysqli($dbHost, $dbUsername, $dbPassword);
        if ($checkDb->connect_error) {
            throw new Exception("Connection failed: " . $checkDb->connect_error);
        }
        $escapedUsername = $checkDb->real_escape_string($username);
        $stmt = $checkDb->prepare("SHOW DATABASES LIKE ?");
        $stmt->bind_param('s', $escapedUsername);
        $stmt->execute();
        $result = $stmt->get_result()->fetch_all(MYSQLI_ASSOC);
        if (!$result) {
            $notFound = true;
            throw new Exception("Database does not exist", 1049);
        }
    } catch (Exception $e) {
        if ($e->getCode() == 1049) {
            $notFound = true;
        } else {
            $buildResults = "Error: " . $e->getMessage();
        }
    }
}

if (isset($_GET['user'])) {
    $username = $_GET['user'];
    $_SESSION['username'] = $username;
    $buildResults = "Welcome " . $_SESSION['display_name'] . ". You're viewing information for: " . (isset($_SESSION['username']) ? $_SESSION['username'] : 'unknown user');
    include "/var/www/dashboard/user_db.php";
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BotOfTheSpecter - <?php echo $title; ?></title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bulma@1.0.0/css/bulma.min.css">
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/toastify-js/src/toastify.min.css">
    <link rel="stylesheet" href="../custom.css">
    <link rel="icon" href="https://cdn.botofthespecter.com/logo.png">
    <link rel="apple-touch-icon" href="https://cdn.botofthespecter.com/logo.png">
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:site" content="@Tools4Streaming" />
    <meta name="twitter:title" content="BotOfTheSpecter" />
    <meta name="twitter:description" content="BotOfTheSpecter is an advanced Twitch bot designed to enhance your streaming experience, offering a suite of tools for community interaction, channel management, and analytics." />
    <meta name="twitter:image" content="https://cdn.botofthespecter.com/BotOfTheSpecter.jpeg" />
    <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/toastify-js"></script>
    <script type="text/javascript">
        // Pass PHP data to JavaScript
        const customCommands = <?php echo json_encode($commands); ?>;
        const lurkers = <?php echo json_encode($lurkers); ?>;
        const typos = <?php echo json_encode($typos); ?>;
        const gameDeaths = <?php echo json_encode($gameDeaths); ?>;
        const hugCounts = <?php echo json_encode($hugCounts); ?>;
        const kissCounts = <?php echo json_encode($kissCounts); ?>;
        const customCounts = <?php echo json_encode($customCounts); ?>;
        const userCounts = <?php echo json_encode($userCounts); ?>;
        const watchTimeData = <?php echo json_encode($watchTimeData); ?>;
        const todos = <?php echo json_encode($todos); ?>;
    </script>
</head>
<body>
<div class="navbar is-fixed-top" role="navigation" aria-label="main navigation" style="height: 75px;">
    <div class="navbar-brand">
        <img src="https://cdn.botofthespecter.com/logo.png" height="175px" alt="BotOfTheSpecter Logo Image">
        <p class="navbar-item" style="font-size: 24px;">BotOfTheSpecter</p>
    </div>
    <div id="navbarMenu" class="navbar-menu">
        <div class="navbar-end">
            <div class="navbar-item">
                <img class="is-rounded" id="profile-image" src="<?php echo $_SESSION['profile_image_url']; ?>" alt="Profile Image">&nbsp;&nbsp;<span class="display-name"><?php echo $_SESSION['display_name']; ?></span>
            </div>
        </div>
    </div>
</div>

<div class="container mt-6">
    <br><br>
    <div class="columns is-centered">
        <div class="column is-three-quarters">
            <?php if (!$username): ?> 
                <br>
                <div class="box">
                    <h2 class="title">Enter the Twitch Username:</h2>
                    <form id="usernameForm" class="field is-grouped" onsubmit="redirectToUser(event)">
                        <div class="control is-expanded">
                            <input type="text" id="user_search" name="user" class="input" placeholder="Enter username" required>
                        </div>
                        <div class="control">
                            <input type="submit" value="Search" class="button is-link">
                        </div>
                    </form>
                </div>
            <?php else: ?> 
                <div class="notification is-info"><?php echo "Welcome " . $_SESSION['display_name'] . ". You're viewing information for: " . $_SESSION['username']; ?> </div>
                <div class="buttons">
                    <button class="button is-link" onclick="loadData('customCommands')">Custom Commands</button>
                    <button class="button is-info" onclick="loadData('lurkers')">Lurkers</button>
                    <button class="button is-info" onclick="loadData('typos')">Typo Counts</button>
                    <button class="button is-info" onclick="loadData('deaths')">Deaths Overview</button>
                    <button class="button is-info" onclick="loadData('hugs')">Hug Counts</button>
                    <button class="button is-info" onclick="loadData('kisses')">Kiss Counts</button>
                    <button class="button is-info" onclick="loadData('custom')">Custom Counts</button>
                    <button class="button is-info" onclick="loadData('userCounts')">User Counts</button>
                    <button class="button is-info" onclick="loadData('watchTime')">Watch Time</button>
                    <button class="button is-link" onclick="loadData('todos')">To-Do Items</button>
                </div>
                <div class="content">
                    <div class="box">
                        <h3 id="table-title" class="title" style="color: white;"></h3>
                        <table class="table is-striped is-fullwidth" style="table-layout: fixed; width: 100%;">
                            <thead>
                                <tr>
                                    <th id="info-column-data" style="color: white; width: 33%;"></th>
                                    <th id="data-column-info" style="color: white; width: 33%;"></th>
                                    <th id="additional-column1" style="color: white; width: 33%; display: none;"></th>
                                </tr>
                            </thead>
                            <tbody id="table-body">
                                <!-- Content will be dynamically injected here -->
                            </tbody>
                        </table>
                    </div>
                </div>
            <?php endif; ?> 
        </div>
    </div>
</div>
<br><br>
<footer class="footer">
    <div class="content has-text-centered">
        &copy; 2023-<?php echo date("Y"); ?> BotOfTheSpecter - All Rights Reserved.
    </div>
</footer>
<script>
function redirectToUser(event) {
    event.preventDefault();
    const username = document.getElementById('user_search').value.trim();
    if (username) {
        window.location.href = '/' + encodeURIComponent(username) + '/';
    }
}

function loadData(type) {
    let data;
    let title;
    let dataColumn;
    let infoColumn;
    let additionalColumnName;
    let dataColumnVisible = true;
    let infoColumnVisible = true;
    let additionalColumnVisible = false;
    let output = '';
    switch(type) {
        case 'customCommands':
            data = customCommands;
            dataColumnVisible = false;
            title = 'Custom Commands';
            infoColumn = 'Command';
            break;
        case 'lurkers':
            data = lurkers;
            title = 'Currently Lurking Users';
            infoColumn = 'Username';
            dataColumn = 'Time';
            break;
        case 'typos':
            data = typos;
            title = 'Typo Counts';
            infoColumn = 'Username';
            dataColumn = 'Typo Count';
            break;
        case 'deaths':
            data = gameDeaths;
            title = 'Deaths Overview';
            infoColumn = 'Game'; 
            dataColumn = 'Death Count';
            break;
        case 'hugs':
            data = hugCounts;
            title = 'Hug Counts';
            infoColumn = 'Username';
            dataColumn = 'Hug Count';
            break;
        case 'kisses':
            data = kissCounts;
            title = 'Kiss Counts';
            infoColumn = 'Username';
            dataColumn = 'Kiss Count';
            break;
        case 'custom':
            data = customCounts;
            title = 'Custom Counts';
            infoColumn = 'Command';
            dataColumn = 'Used';
            break;
        case 'userCounts':
            data = userCounts;
            additionalColumnVisible = true;
            title = 'User Counts for Commands';
            additionalColumnName = 'Count';
            infoColumn = 'User';
            dataColumn = 'Command';
            break;
        case 'watchTime': 
            data = watchTimeData;
            additionalColumnVisible = true;
            title = 'Watch Time';
            infoColumn = 'Username';
            dataColumn = 'Online Watch Time';
            additionalColumnName = 'Offline Watch Time';
            data.sort((a, b) => b.total_watch_time_live - a.total_watch_time_live || b.total_watch_time_offline - a.total_watch_time_offline);
            break;
        case 'todos':
            data = todos;
            title = 'To-Do Items';
            infoColumn = 'Task';
            dataColumn = 'Status';
            break;
    }
    document.getElementById('data-column-info').innerText = dataColumn;
    document.getElementById('info-column-data').innerText = infoColumn;
    document.getElementById('additional-column1').innerText = additionalColumnName;
    document.getElementById('additional-column1').style.display = additionalColumnVisible ? '' : 'none';
    document.getElementById('data-column-info').style.display = dataColumnVisible ? '' : 'none';
    document.getElementById('info-column-data').style.display = infoColumnVisible ? '' : 'none';
    if (Array.isArray(data)) {
        data.forEach(item => {
            output += `<tr>`;
            if (type === 'customCommands') {
                output += `<td>${item.command}</td>`; 
            } else if (type === 'lurkers') {
                output += `<td>${item.user_id}</td><td><span class='has-text-success'>${item.start_time}</span></td>`; 
            } else if (type === 'typos') {
                output += `<td>${item.username}</td><td><span class='has-text-success'>${item.typo_count}</span></td>`; 
            } else if (type === 'deaths') {
                output += `<td>${item.game_name}</td><td><span class='has-text-success'>${item.death_count}</span></td>`; 
            } else if (type === 'hugs') {
                output += `<td>${item.username}</td><td><span class='has-text-success'>${item.hug_count}</span></td>`; 
            } else if (type === 'kisses') {
                output += `<td>${item.username}</td><td><span class='has-text-success'>${item.kiss_count}</span></td>`; 
            } else if (type === 'custom') {
                output += `<td>${item.command}</td><td><span class='has-text-success'>${item.count}</span></td>`; 
            } else if (type === 'userCounts') {
                output += `<td>${item.user}</td><td><span class='has-text-success'>${item.command}</td><td><span class='has-text-success'>${item.count}</span></td>`; 
            } else if (type === 'watchTime') { 
                output += `<td>${item.username}</td><td>${formatWatchTime(item.total_watch_time_live)}</td><td>${formatWatchTime(item.total_watch_time_offline)}</td>`;
            } else if (type === 'todos') {
                output += `<td>${item.id}</td><td>${item.objective}</td><td>${item.category}</td><td>${item.completed}</td><td>${item.created_at}</td><td>${item.updated_at}</td>`;
            }
            output += `</tr>`;
        });
    }
    document.getElementById('table-title').innerText = title;
    document.getElementById('table-body').innerHTML = output;
}

function formatWatchTime(seconds) {
    if (seconds === 0) {
        return "<span class='has-text-danger'>Not Recorded</span>";
    }
    const units = {
        year: 31536000,
        month: 2592000,
        day: 86400,
        hour: 3600,
        minute: 60
    };
    const parts = [];
    for (const [name, divisor] of Object.entries(units)) {
        const quotient = Math.floor(seconds / divisor);
        if (quotient > 0) {
            parts.push(`${quotient} ${name}${quotient > 1 ? 's' : ''}`);
            seconds -= quotient * divisor;
        }
    }
    return `<span class='has-text-success'>${parts.join(', ')}</span>`;
}

document.addEventListener('DOMContentLoaded', function() {
        loadData('customCommands');
    });
</script>
</body>
</html>