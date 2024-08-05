<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

session_start();

if (!isset($_SESSION['access_token'])) {
    exit();
}

$access_token = $_SESSION['access_token'];
$broadcasterID = $_SESSION['twitch_user_id'];
$cacheUsername = $_SESSION['username'];
$clientID = 'mrjucsmsnri89ifucl66jj1n35jkj8';

function getTwitchUserId($username, $accessToken, $clientID) {
    $url = "https://api.twitch.tv/helix/users?login=$username";
    $headers = [
        "Authorization: Bearer $accessToken",
        "Client-Id: $clientID"
    ];
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    $response = curl_exec($ch);
    curl_close($ch);
    $data = json_decode($response, true);
    return $data['data'][0]['id'] ?? null;
}

function isUserBanned($userId, $accessToken, $broadcasterID, $clientID) {
    $url = "https://api.twitch.tv/helix/moderation/banned?broadcaster_id=$broadcasterID&user_id=$userId";
    $headers = [
        "Authorization: Bearer $accessToken",
        "Client-Id: $clientID"
    ];
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    $response = curl_exec($ch);
    curl_close($ch);
    $data = json_decode($response, true);
    return !empty($data['data']);
}

if ($_SERVER["REQUEST_METHOD"] == "POST" && isset($_POST['usernameToCheck'])) {
    $username = $_POST['usernameToCheck'];

    $cacheDirectory = "cache/$cacheUsername";
    $cacheFile = "$cacheDirectory/bannedUsers.json";
    $tempCacheFile = "$cacheFile.tmp";
    $cacheExpiration = 600; // Cache expires after 10 minutes

    $bannedUsersCache = [];
    if (file_exists($cacheFile) && time() - filemtime($cacheFile) < $cacheExpiration) {
        $cacheContent = file_get_contents($cacheFile);
        if ($cacheContent) {
            $bannedUsersCache = json_decode($cacheContent, true);
        }
    }

    if (isset($bannedUsersCache[$username])) {
        $banned = $bannedUsersCache[$username];
    } else {
        $userId = getTwitchUserId($username, $access_token, $clientID);
        if ($userId) {
            $banned = isUserBanned($userId, $access_token, $broadcasterID, $clientID);
            $bannedUsersCache[$username] = $banned;

            if (!is_dir($cacheDirectory)) {
                mkdir($cacheDirectory, 0755, true);
            }

            // Write to a temporary file first
            if (!empty($bannedUsersCache) && $tempFileHandle = fopen($tempCacheFile, 'w')) {
                if (flock($tempFileHandle, LOCK_EX)) {
                    fwrite($tempFileHandle, json_encode($bannedUsersCache));
                    fflush($tempFileHandle); // flush output before releasing the lock
                    flock($tempFileHandle, LOCK_UN);
                }
                fclose($tempFileHandle);
                rename($tempCacheFile, $cacheFile);
            }
        } else {
            $banned = false;
        }
    }

    echo json_encode(['banned' => $banned]);

} else {
    http_response_code(400);
    echo json_encode(['error' => 'Bad request']);
}
?>