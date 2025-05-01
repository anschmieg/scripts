#!/usr/bin/env python3
import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from pymediainfo import MediaInfo
except ImportError:
    MediaInfo = None
try:
    import webvtt
except ImportError:
    webvtt = None


class SuppressBrokenPipeHandler(SimpleHTTPRequestHandler):
    # Override handle to suppress BrokenPipeError during request handling
    def handle(self) -> None:
        try:
            super().handle()
        except BrokenPipeError:
            # Client disconnected early, ignore error
            self.log_message("Client disconnected early")
        except ConnectionResetError:
            # Client reset connection, ignore error
            self.log_message("Connection reset by peer")

    # Override finish to prevent BrokenPipeError during finish if socket is already closed
    def finish(self) -> None:
        try:
            super().finish()
        except (BrokenPipeError, ConnectionResetError):
            pass  # Ignore errors if the socket is already closed

    # Override copyfile to handle BrokenPipeError during file transfer
    def copyfile(self, source, outputfile):
        try:
            shutil.copyfileobj(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected during transfer, ignore error
            self.log_message("Client disconnected during file transfer")


def convert_srt_to_vtt_simple(srt_path: Path, vtt_path: Path):
    """Basic SRT to VTT conversion (fallback)."""
    try:
        with open(srt_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        vtt_content = "WEBVTT\n\n" + content.replace(",", ".")
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write(vtt_content)
        print(f"Converted SRT to VTT (simple): {vtt_path.name}")
        return True
    except Exception as e:
        print(f"Error during simple SRT conversion: {e}", file=sys.stderr)
        return False


def convert_srt_to_vtt(srt_path: Path, temp_dir: Path) -> Path | None:
    """Convert SRT to VTT, preferably using webvtt-py, into the temp_dir."""
    # Define target path within the temp directory
    vtt_filename = srt_path.stem + ".vtt"
    vtt_path = temp_dir / vtt_filename

    if webvtt:
        try:
            vtt = webvtt.from_srt(str(srt_path))
            vtt.save(str(vtt_path))
            print(f"Converted SRT to VTT (webvtt-py): {vtt_path.name}")
            return vtt_path
        except FileNotFoundError:
            print(f"Error: SRT file not found at {srt_path}", file=sys.stderr)
            return None
        except Exception as e:
            print(
                f"Error converting subtitles with webvtt-py: {str(e)}", file=sys.stderr
            )
            print("Falling back to simple conversion...")
            # Fall through to simple conversion if webvtt fails
    else:
        print("webvtt-py not found. Using simple conversion.", file=sys.stderr)

    # Fallback / If webvtt not installed or failed
    if convert_srt_to_vtt_simple(srt_path, vtt_path):
        return vtt_path
    else:
        print("Subtitle conversion failed.", file=sys.stderr)
        return None


def generate_html(video_name: str, subtitle_name: str):
    """Generate minimal HTML player with video and subtitles"""
    return f"""
<!DOCTYPE html>
<html>

<head>
  <meta charset="utf-8">
  <style>
    body {{
      background-color: black;
      margin: 0;
      display: flex;        /* Use flexbox for centering */
      justify-content: center; /* Center horizontally */
      align-items: center;    /* Center vertically */
      height: 100vh;        /* Full viewport height */
      overflow: hidden;     /* Hide scrollbars if video slightly overflows */
    }}
    video {{
      max-width: 100vw;     /* Max width is viewport width */
      max-height: 100vh;    /* Max height is viewport height */
      display: block;       /* Prevents potential extra space below */
      /* Optional: use 'contain' to ensure the whole video fits, potentially adding black bars */
      /* object-fit: contain; */
      /* Optional: use 'cover' to fill the space, potentially cropping the video */
      /* object-fit: cover; */
    }}
  </style>
</head>

<body>
  <video controls>
    <source src="{video_name}" type="video/mp4">
    <track src="{subtitle_name}" kind="subtitles" srclang="en" label="English" default>
  </video>
</body>

</html>"""


def get_video_dimensions_mdls(video_path: Path) -> tuple[int | None, int | None]:
    """Fallback to get video dimensions using macOS mdls."""
    if platform.system() != "Darwin":
        return None, None  # mdls is macOS specific
    try:
        cmd = [
            "mdls",
            "-name",
            "kMDItemPixelWidth",
            "-name",
            "kMDItemPixelHeight",
            str(video_path),
        ]
        process = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=5
        )
        output = process.stdout
        width_match = re.search(r"kMDItemPixelWidth\s*=\s*(\d+)", output)
        height_match = re.search(r"kMDItemPixelHeight\s*=\s*(\d+)", output)
        width = int(width_match.group(1)) if width_match else None
        height = int(height_match.group(1)) if height_match else None
        if width and height:
            print("Used mdls to get dimensions.")
            return width, height
        else:
            print("mdls output did not contain dimensions.", file=sys.stderr)
            return None, None
    except FileNotFoundError:
        print("mdls command not found.", file=sys.stderr)
        return None, None
    except subprocess.CalledProcessError as e:
        print(f"mdls command failed: {e.stderr}", file=sys.stderr)
        return None, None
    except subprocess.TimeoutExpired:
        print("mdls command timed out.", file=sys.stderr)
        return None, None
    except Exception as e:
        print(f"Error running mdls: {e}", file=sys.stderr)
        return None, None


def get_video_dimensions(video_path: Path) -> tuple[int | None, int | None]:
    """Get video width and height using pymediainfo, fallback to mdls."""
    width, height = None, None
    if MediaInfo:
        try:
            media_info = MediaInfo.parse(str(video_path))
            for track in media_info.tracks:
                if track.track_type == "Video":
                    width = int(track.width) if track.width else None
                    height = int(track.height) if track.height else None
                    if width and height:
                        print("Used pymediainfo to get dimensions.")
                        return width, height
            print("pymediainfo did not find video track dimensions.", file=sys.stderr)
        except Exception as e:
            print(f"pymediainfo error: {e}", file=sys.stderr)
            # Fall through to mdls if pymediainfo fails

    # Fallback to mdls if pymediainfo not installed, failed, or didn't find dimensions
    if not (width and height):
        print("Trying mdls fallback...")
        width, height = get_video_dimensions_mdls(video_path)

    if not (width and height):
        print(
            "Warning: Could not determine video dimensions using pymediainfo or mdls.",
            file=sys.stderr,
        )

    return width, height


def resize_browser_macos(
    width: int, height: int, url: str, browsers: list[str]
) -> bool:
    """Use AppleScript to resize the browser window on macOS, trying browsers in order."""
    if platform.system() != "Darwin":
        return False  # Only run on macOS

    # Add space for browser chrome (title bar, etc.) - adjust as needed
    window_height = height + 80  # Heuristic adjustment
    window_width = width

    for browser_name in browsers:
        print(f"Attempting resize with {browser_name}...")
        apple_script = """
        on run {winWidth, winHeight, targetURL, browserName}
            set winWidthNum to winWidth as integer
            set winHeightNum to winHeight as integer
            set windowResized to false
            set retryCount to 0
            set maxRetries to 10 -- Try for 5 seconds (10 * 0.5s delay)

            -- Check if the application exists first
            if application id (do shell script "mdls -name kMDItemCFBundleIdentifier -r " & quoted form of ("/Applications/" & browserName & ".app")) is "" then
                 log browserName & " application not found."
                 return false
            end if

            log "Trying to resize " & browserName & " window for URL: " & targetURL & " to " & winWidth & "x" & winHeight

            repeat while not windowResized and retryCount < maxRetries
                try
                    tell application browserName
                        if not running then
                            log browserName & " not running, launching..."
                            launch
                            delay 1.5 -- Give more time to launch fully
                        end if
                        activate

                        set targetWindow to missing value
                        repeat with w in windows
                            try
                                -- Try to get URL of the frontmost tab
                                set currentURL to URL of current tab of w
                                if currentURL starts with targetURL then
                                    set targetWindow to w
                                    exit repeat
                                end if
                            on error errMsg number errorNum
                                -- Ignore errors if window/tab doesn't have a URL or browser is busy
                                log " Minor error checking window URL: " & errMsg
                            end try
                        end repeat

                        if targetWindow is not missing value then
                            log " Found target window, setting bounds..."
                            -- Bounds are {x_min, y_min, x_max, y_max}
                            -- Position at top-left (adjust y_min for menu bar)
                            set bounds of targetWindow to {0, 25, winWidthNum, winHeightNum + 25}
                            set windowResized to true
                            log " Window resized successfully for " & browserName & "."
                        else
                            log " Target window not found yet for " & browserName & " (Retry " & (retryCount + 1) & "/" & maxRetries & ")"
                        end if
                    end tell
                on error errMsg number errorNum
                    log " Major AppleScript Error for " & browserName & " (" & errorNum & "): " & errMsg
                    -- If browser is not scriptable or other major error, stop trying this browser
                    exit repeat
                end try

                if not windowResized then
                    set retryCount to retryCount + 1
                    delay 0.5
                end if
            end repeat

            if windowResized then
                return true -- Success with this browser
            else
                 log " Failed to find and resize window for " & browserName & " after " & maxRetries & " retries."
            end if
        end try -- End outer try for application check/major errors
        -- If loop continues, it means resizing failed for this browser
    end repeat -- End browser loop

    log "Failed to resize window with any specified browser."
    return false -- Failed for all browsers
    end run
    """
        try:
            process = subprocess.run(
                [
                    "osascript",
                    "-e",
                    apple_script,
                    str(window_width),
                    str(window_height),
                    url,
                    browser_name,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,  # Increased timeout slightly
            )
            # Check AppleScript's explicit return value (true/false)
            script_output = process.stdout.strip()
            if process.returncode == 0 and script_output.endswith("true"):
                print(f"Successfully resized window using {browser_name}.")
                return True  # Stop trying other browsers
            else:
                print(f"AppleScript failed or did not resize for {browser_name}.")
                # print(f"AS Output:\n{process.stdout}") # Debugging
                # print(f"AS Error:\n{process.stderr}") # Debugging

        except subprocess.TimeoutExpired:
            print(f"AppleScript timed out for {browser_name}.", file=sys.stderr)
        except Exception as e:
            print(f"Failed to run AppleScript for {browser_name}: {e}", file=sys.stderr)

    # If loop completes without returning True
    print("Could not resize window using any of the preferred browsers.")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Play MP4 with SRT subtitles, resizing Arc or Chrome window"
    )
    parser.add_argument("video", help="Path to MP4 video file")
    parser.add_argument("srt", help="Path to SRT subtitle file")
    args = parser.parse_args()

    video_path_orig = Path(args.video).resolve()
    srt_path_orig = Path(args.srt).resolve()
    temp_dir_path = None  # Initialize
    original_cwd = Path.cwd()

    # Validate inputs before creating temp dir
    if not video_path_orig.exists():
        sys.exit(f"Video file not found: {video_path_orig}")
    if not srt_path_orig.exists():
        sys.exit(f"Subtitle file not found: {srt_path_orig}")

    try:
        # Create a dedicated temporary directory
        temp_dir_path = Path(tempfile.mkdtemp(prefix="play_video_"))
        print(f"Created temporary directory: {temp_dir_path}")

        # --- Files will now be relative to temp_dir_path ---

        # Symlink or copy video into temp dir (Symlink preferred, Copy as fallback)
        video_filename = video_path_orig.name
        video_path_temp = temp_dir_path / video_filename
        try:
            os.symlink(video_path_orig, video_path_temp)
            print(f"Symlinked video into temp dir: {video_filename}")
        except OSError:
            print(f"Symlink failed, copying video into temp dir: {video_filename}...")
            shutil.copy(video_path_orig, video_path_temp)
            print("Video copied.")

        # Get video dimensions (use original path for metadata)
        video_width, video_height = get_video_dimensions(video_path_orig)

        # Convert subtitles into the temporary directory
        temp_vtt_path = convert_srt_to_vtt(srt_path_orig, temp_dir_path)
        if not temp_vtt_path:
            sys.exit("Failed to convert subtitles. Exiting.")

        # Generate HTML inside the temporary directory
        player_filename = "player.html"
        player_path_temp = temp_dir_path / player_filename
        # Pass only the *filenames* to generate_html, as they are relative to the server root (temp_dir)
        html_content = generate_html(video_path_temp.name, temp_vtt_path.name)
        with open(player_path_temp, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Start web server from the temporary directory
        port = 8000
        os.chdir(temp_dir_path)  # Change to temp dir for serving

        server_address = ("", port)
        httpd = ThreadingHTTPServer(server_address, SuppressBrokenPipeHandler)

        # URL uses only the player filename, relative to the temp dir root
        server_url = f"http://localhost:{port}/{player_filename}"
        print(f"Serving content from {temp_dir_path} at {server_url}")

        # Open browser first
        webbrowser.open(server_url)

        # Attempt to resize browser window on macOS
        browser_priority = ["Arc", "Google Chrome"]
        if video_width and video_height and platform.system() == "Darwin":
            print(
                f"Attempting to resize browser window ({'/'.join(browser_priority)}) to ~{video_width}x{video_height}..."
            )
            resize_browser_macos(
                video_width, video_height, server_url, browser_priority
            )
        elif platform.system() == "Darwin":
            print("Could not get video dimensions, skipping resize.")

        # Keep server running
        httpd.serve_forever()

    except KeyboardInterrupt:
        print("\nShutting down server...")
        # Server is already stopped by serve_forever() exiting

    finally:
        # Change back to original directory *before* cleaning up temp dir
        os.chdir(original_cwd)
        print(f"Changed back to: {original_cwd}")

        # Clean up the temporary directory and its contents
        if temp_dir_path and temp_dir_path.exists():
            try:
                shutil.rmtree(temp_dir_path)
                print(f"Removed temporary directory: {temp_dir_path}")
            except OSError as e:
                print(
                    f"Error removing temporary directory {temp_dir_path}: {e}",
                    file=sys.stderr,
                )
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
