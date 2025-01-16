<?php
// Initialize the session
session_start();
ini_set('max_execution_time', 300);

// Check if the user is logged in
if (!isset($_SESSION['access_token'])) {
    header('Location: login.php');
    exit();
}

// Page Title
$title = "Sound Alerts";

// Include all the information
require_once "/var/www/config/db_connect.php";
include 'userdata.php';
include 'bot_control.php';
include 'user_db.php';
foreach ($profileData as $profile) {
  $timezone = $profile['timezone'];
  $weather = $profile['weather_location'];
}
date_default_timezone_set($timezone);

// Define user-specific storage limits
$base_storage_size = 2 * 1024 * 1024; // 2MB in bytes
$tier = $_SESSION['tier'] ?? "None";

switch ($tier) {
    case "1000":
        $max_storage_size = 5 * 1024 * 1024; // 5MB
        break;
    case "2000":
        $max_storage_size = 10 * 1024 * 1024; // 10MB
        break;
    case "3000":
        $max_storage_size = 20 * 1024 * 1024; // 20MB
        break;
    case "4000":
        $max_storage_size = 50 * 1024 * 1024; // 50MB
        break;
    default:
        $max_storage_size = $base_storage_size; // Default 2MB
        break;
}

// Fetch sound alert mappings for the current user
$getSoundAlerts = $db->prepare("SELECT sound_mapping, reward_id FROM sound_alerts");
$getSoundAlerts->execute();
$soundAlerts = $getSoundAlerts->fetchAll(PDO::FETCH_ASSOC);

// Create an associative array for easy lookup: sound_mapping => reward_id
$soundAlertMappings = [];
foreach ($soundAlerts as $alert) {
    $soundAlertMappings[$alert['sound_mapping']] = $alert['reward_id'];
}

// Create an associative array for reward_id => reward_title for easy lookup
$rewardIdToTitle = [];
foreach ($channelPointRewards as $reward) {
    $rewardIdToTitle[$reward['reward_id']] = $reward['reward_title'];
}

// Define sound alert path and storage limits
$soundalert_path = "/var/www/soundalerts/" . $username;
$walkon_path = "/var/www/walkons/" . $username;
$status = '';

// Handle channel point reward mapping
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['sound_file'], $_POST['reward_id'])) {
    $status = ""; // Initialize $status
    $soundFile = $_POST['sound_file'];
    $rewardId = $_POST['reward_id'];
    $soundFile = htmlspecialchars($soundFile); 
    $db->beginTransaction();  
    // Check if a mapping already exists for this sound file
    $checkExisting = $db->prepare("SELECT 1 FROM sound_alerts WHERE sound_mapping = :sound_mapping");
    $checkExisting->bindParam(':sound_mapping', $soundFile);
    $checkExisting->execute();
    if ($checkExisting->rowCount() > 0) {
        // Update existing mapping
        if ($rewardId) {
            $updateMapping = $db->prepare("UPDATE sound_alerts SET reward_id = :reward_id WHERE sound_mapping = :sound_mapping");
            $updateMapping->bindParam(':reward_id', $rewardId);
            $updateMapping->bindParam(':sound_mapping', $soundFile);
            if (!$updateMapping->execute()) {
                $status .= "Failed to update mapping for file '" . $soundFile . "'. Database error: " . print_r($updateMapping->errorInfo(), true) . "<br>"; 
            } else {
                $status .= "Mapping for file '" . $soundFile . "' has been updated successfully.<br>";
            }
        } else {
            // Clear the mapping if no reward is selected
            $clearMapping = $db->prepare("UPDATE sound_alerts SET reward_id = NULL WHERE sound_mapping = :sound_mapping");
            $clearMapping->bindParam(':sound_mapping', $soundFile);
            if (!$clearMapping->execute()) {
                $status .= "Failed to clear mapping for file '" . $soundFile . "'. Database error: " . print_r($clearMapping->errorInfo(), true) . "<br>"; 
            } else {
                $status .= "Mapping for file '" . $soundFile . "' has been cleared.<br>";
            }
        }
    } else {
        // Create a new mapping if it doesn't exist
        if ($rewardId) {
            $insertMapping = $db->prepare("INSERT INTO sound_alerts (sound_mapping, reward_id) VALUES (:sound_mapping, :reward_id)");
            $insertMapping->bindParam(':sound_mapping', $soundFile);
            $insertMapping->bindParam(':reward_id', $rewardId);
            if (!$insertMapping->execute()) {
                $status .= "Failed to create mapping for file '" . $soundFile . "'. Database error: " . print_r($insertMapping->errorInfo(), true) . "<br>"; 
            } else {
                $status .= "Mapping for file '" . $soundFile . "' has been created successfully.<br>";
            }
        } 
    }
    // Commit transaction
    $db->commit();
}

// Create the user's directory if it doesn't exist
if (!is_dir($soundalert_path)) {
    if (!mkdir($soundalert_path, 0755, true)) {
        exit("Failed to create directory.");
    }
}

if (!is_dir($walkon_path)) {
    if (!mkdir($walkon_path, 0755, true)) {
        exit("Failed to create directory.");
    }
}

// Calculate total storage used by the user across both directories
function calculateStorageUsed($directories) {
    $size = 0;
    foreach ($directories as $directory) {
        foreach (glob(rtrim($directory, '/').'/*', GLOB_NOSORT) as $file) {
            $size += is_file($file) ? filesize($file) : calculateStorageUsed([$file]);
        }
    }
    return $size;
}

$current_storage_used = calculateStorageUsed([$walkon_path, $soundalert_path]);
$storage_percentage = ($current_storage_used / $max_storage_size) * 100;
$remaining_storage = $max_storage_size - $current_storage_used;
$max_upload_size = $remaining_storage;
// ini_set('upload_max_filesize', $max_upload_size);
// ini_set('post_max_size', $max_upload_size);

// Handle file upload
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_FILES["filesToUpload"])) {
    foreach ($_FILES["filesToUpload"]["tmp_name"] as $key => $tmp_name) {
        $fileSize = $_FILES["filesToUpload"]["size"][$key];
        if ($current_storage_used + $fileSize > $max_storage_size) {
            $status .= "Failed to upload " . htmlspecialchars(basename($_FILES["filesToUpload"]["name"][$key])) . ". Storage limit exceeded.<br>";
            continue;
        }
        $targetFile = $soundalert_path . '/' . basename($_FILES["filesToUpload"]["name"][$key]);
        $fileType = strtolower(pathinfo($targetFile, PATHINFO_EXTENSION));
        if ($fileType != "mp3") {
            $status .= "Failed to upload " . htmlspecialchars(basename($_FILES["filesToUpload"]["name"][$key])) . ". Only MP3 files are allowed.<br>";
            continue;
        }
        if (move_uploaded_file($tmp_name, $targetFile)) {
            $current_storage_used += $fileSize;
            $status .= "The file " . htmlspecialchars(basename($_FILES["filesToUpload"]["name"][$key])) . " has been uploaded.<br>";
        } else {
            $status .= "Sorry, there was an error uploading " . htmlspecialchars(basename($_FILES["filesToUpload"]["name"][$key])) . ".<br>";
        }
    }
    $storage_percentage = ($current_storage_used / $max_storage_size) * 100; // Update percentage after upload
}

// Handle file deletion
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['delete_files'])) {
    foreach ($_POST['delete_files'] as $file_to_delete) {
        $file_to_delete = $soundalert_path . '/' . basename($file_to_delete);
        if (is_file($file_to_delete) && unlink($file_to_delete)) {
            $status .= "The file " . htmlspecialchars(basename($file_to_delete)) . " has been deleted.<br>";
        } else {
            $status .= "Failed to delete " . htmlspecialchars(basename($file_to_delete)) . ".<br>";
        }
    }
    $current_storage_used = calculateStorageUsed([$walkon_path, $soundalert_path]);
    $storage_percentage = ($current_storage_used / $max_storage_size) * 100;
}

$soundalert_files = array_diff(scandir($soundalert_path), array('.', '..'));
function formatFileName($fileName) { return basename($fileName, '.mp3'); }
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
    <div class="notification is-danger">
        <div class="columns is-vcentered">
            <div class="column is-narrow">
                <span class="icon is-large">
                    <i class="fas fa-bell fa-2x"></i> 
                </span>
            </div>
            <div class="column">
                <p><strong>Setting up Channel Point Sound Alerts</strong></p>
                <ul>
                    <li><span class="icon"><i class="fas fa-upload"></i></span> Upload your audio file.  Click 'Upload MP3 Files' and choose the channel point to trigger it.</li>
                    <li><span class="icon"><i class="fab fa-twitch"></i></span> Make sure your rewards are created on Twitch and synced with Specter to see them in the dropdown.</li>
                    <li><span class="icon"><i class="fas fa-play-circle"></i></span> Sound alerts will play through Specter Overlays when the channel point is redeemed.</li>
                    <li><span class="icon"><i class="fas fa-headphones"></i></span> Start your streaming software and enable the overlay with audio <span class="has-text-weight-bold">before</span> testing.</li> 
                </ul>
            </div>
        </div>
    </div>
    <div class="columns is-desktop is-multiline box-container is-centered" style="width: 100%;">
        <div class="column is-4" id="walkon-upload" style="position: relative;">
            <h1 class="title is-4">Upload MP3 Files:</h1>
            <form action="" method="POST" enctype="multipart/form-data" id="uploadForm">
                <label for="filesToUpload" class="drag-area" id="drag-area">
                    <span>Drag & Drop files here or</span>
                    <span>Browse Files</span>
                    <input type="file" name="filesToUpload[]" id="filesToUpload" multiple>
                </label>
                <br>
                <div id="file-list"></div>
                <br>
                <input type="submit" value="Upload MP3 Files" name="submit">
            </form>
            <br>
            <div class="upload-progress-bar-container">
                <div class="upload-progress-bar has-text-black-bis" style="width: 0%;">0%</div>
            </div>
            <br>
            <div class="progress-bar-container">
                <div class="progress-bar has-text-black-bis" style="width: <?php echo $storage_percentage; ?>%;"><?php echo round($storage_percentage, 2); ?>%</div>
            </div>
            <p><?php echo round($current_storage_used / 1024 / 1024, 2); ?>MB of <?php echo round($max_storage_size / 1024 / 1024, 2); ?>MB used</p>
            <?php if (!empty($status)) : ?>
                <div class="message"><?php echo $status; ?></div>
            <?php endif; ?>
        </div>
        <div class="column is-7 bot-box" id="walkon-upload" style="position: relative;">
            <?php $walkon_files = array_diff(scandir($soundalert_path), array('.', '..')); if (!empty($walkon_files)) : ?>
            <h1 class="title is-4">Your Sound Alerts</h1>
            <form action="" method="POST" id="deleteForm">
                <table class="table is-striped" style="width: 100%; text-align: center;">
                    <thead>
                        <tr>
                            <th style="width: 70px;">Select</th>
                            <th>File Name</th>
                            <th>Channel Point Reward</th>
                            <th style="width: 100px;">Action</th>
                            <th style="width: 100px;">Test Audio</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($walkon_files as $file): ?>
                        <tr>
                            <td>
                                <input type="checkbox" name="delete_files[]" value="<?php echo htmlspecialchars($file); ?>">
                            </td>
                            <td>
                                <?php echo htmlspecialchars(pathinfo($file, PATHINFO_FILENAME)); ?>
                            </td>
                            <td>
                                <?php
                                // Determine the current mapped reward (if any)
                                $current_reward_id = isset($soundAlertMappings[$file]) ? $soundAlertMappings[$file] : null;
                                $current_reward_title = $current_reward_id ? htmlspecialchars($rewardIdToTitle[$current_reward_id]) : "Not Mapped";
                                ?>
                                <?php if ($current_reward_id): ?>
                                    <em><?php echo $current_reward_title; ?></em>
                                <?php else: ?>
                                    <em>Not Mapped</em>
                                <?php endif; ?>
                                <br>
                                <form action="" method="POST" class="mapping-form">
                                    <input type="hidden" name="sound_file" value="<?php echo htmlspecialchars($file); ?>">
                                    <select name="reward_id" class="mapping-select" onchange="this.form.submit()">
                                        <option value="">-- Select Reward --</option>
                                        <?php 
                                        foreach ($channelPointRewards as $reward): 
                                            $isMapped = in_array($reward['reward_id'], $soundAlertMappings);
                                            $isCurrent = ($current_reward_id === $reward['reward_id']);
                                            // Skip rewards that are already mapped to other sounds, unless it's the current mapping
                                            if ($isMapped && !$isCurrent) continue; 
                                        ?>
                                            <option value="<?php echo htmlspecialchars($reward['reward_id']); ?>" 
                                                <?php 
                                                if ($isCurrent) {
                                                    echo 'selected';
                                                }
                                                ?>
                                            >
                                                <?php echo htmlspecialchars($reward['reward_title']); ?>
                                            </option>
                                        <?php endforeach; ?>
                                    </select>
                                </form>
                            </td>
                            <td>
                                <button type="button" class="delete-single button is-danger" data-file="<?php echo htmlspecialchars($file); ?>">Delete</button>
                            </td>
                            <td>
                                <button type="button" class="test-sound button is-primary" data-file="<?php echo htmlspecialchars($file); ?>">Test</button>
                            </td>
                        </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
                <input type="submit" value="Delete Selected" class="button is-danger" name="submit_delete" style="margin-top: 10px;">
            </form>
            <?php else: ?>
                <h1 class="title is-4">No sound alert files uploaded.</h1>
            <?php endif; ?>
        </div>
    </div>
</div>

<script src="https://code.jquery.com/jquery-2.1.4.min.js"></script>
<script>
$(document).ready(function() {
    let dropArea = $('#drag-area');
    let fileInput = $('#filesToUpload');
    let fileList = $('#file-list');
    let uploadProgressBar = $('.upload-progress-bar');

    dropArea.on('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropArea.addClass('dragging');
    });
    dropArea.on('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropArea.removeClass('dragging');
    });
    dropArea.on('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropArea.removeClass('dragging');
        let files = e.originalEvent.dataTransfer.files;
        fileInput.prop('files', files);
        fileList.empty();
        $.each(files, function(index, file) {
            fileList.append('<div>' + file.name + '</div>');
        });
        uploadFiles(files);
    });
    dropArea.on('click', function() {
        fileInput.click();
    });
    fileInput.on('change', function() {
        let files = fileInput.prop('files');
        fileList.empty();
        $.each(files, function(index, file) {
            fileList.append('<div>' + file.name + '</div>');
        });
        uploadFiles(files);
    });

    function uploadFiles(files) {
        let formData = new FormData();
        $.each(files, function(index, file) {
            formData.append('filesToUpload[]', file);
        });
        $.ajax({
            url: '',
            type: 'POST',
            data: formData,
            contentType: false,
            processData: false,
            xhr: function() {
                let xhr = new window.XMLHttpRequest();
                xhr.upload.addEventListener('progress', function(e) {
                    if (e.lengthComputable) {
                        let percentComplete = (e.loaded / e.total) * 100;
                        uploadProgressBar.css('width', percentComplete + '%');
                        uploadProgressBar.text(Math.round(percentComplete) + '%');
                    }
                }, false);
                return xhr;
            },
            success: function(response) {
                location.reload(); // Reload the page to update the file list and storage usage
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.error('Upload failed: ' + textStatus + ' - ' + errorThrown);
            }
        });
    }

    $('.delete-single').on('click', function() {
        let fileName = $(this).data('file');
        if (confirm('Are you sure you want to delete "' + fileName + '"?')) {
            $('<input>').attr({
                type: 'hidden',
                name: 'delete_files[]',
                value: fileName
            }).appendTo('#deleteForm');
            $('#deleteForm').submit();
        }
    });
});

document.addEventListener("DOMContentLoaded", function () {
    // Attach click event listeners to all Test buttons
    document.querySelectorAll(".test-sound").forEach(function (button) {
        button.addEventListener("click", function () {
            const fileName = this.getAttribute("data-file");
            sendStreamEvent("SOUND_ALERT", fileName);
        });
    });
});

// Function to send a stream event
function sendStreamEvent(eventType, fileName) {
    const xhr = new XMLHttpRequest();
    const url = "notify_event.php";
    const params = `event=${eventType}&sound=${encodeURIComponent(fileName)}&channel_name=<?php echo $username; ?>&api_key=<?php echo $api_key; ?>`;
    xhr.open("POST", url, true);
    xhr.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
    xhr.onreadystatechange = function () {
        if (xhr.readyState === 4 && xhr.status === 200) {
            try {
                const response = JSON.parse(xhr.responseText);
                if (response.success) {
                    console.log(`${eventType} event for ${fileName} sent successfully.`);
                } else {
                    console.error(`Error sending ${eventType} event: ${response.message}`);
                }
            } catch (e) {
                console.error("Error parsing JSON response:", e);
                console.error("Response:", xhr.responseText);
            }
        } else if (xhr.readyState === 4) {
            console.error(`Error sending ${eventType} event: ${xhr.responseText}`);
        }
    };
    xhr.send(params);
}
</script>
</body>
</html>