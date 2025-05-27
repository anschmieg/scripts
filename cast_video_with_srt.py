#!/usr/bin/env python3

# import logging
import argparse
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid  # Import uuid module
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pychromecast.models import CastInfo  # Import CastInfo

try:
    import pychromecast
    from pychromecast import Chromecast
    from pychromecast.discovery import CastBrowser  # , SimpleCastListener
    from pychromecast.error import ChromecastConnectionError
except ImportError:
    print("Error: pychromecast library not found.", file=sys.stderr)
    print("Please run: pip install pychromecast zeroconf", file=sys.stderr)
    sys.exit(1)

try:
    import webvtt
except ImportError:
    webvtt = None  # Will use fallback conversion

# --- Enable pychromecast logging ---
# Uncomment the following lines for detailed discovery debugging:
# logging.basicConfig(level=logging.DEBUG)
# logging.getLogger("pychromecast").setLevel(logging.DEBUG)
# logging.getLogger("zeroconf").setLevel(logging.DEBUG)  # Also log zeroconf


# --- Custom Listener ---
# Create a listener that stores discovered service info
class MyCastListener(pychromecast.discovery.AbstractCastListener):
    def __init__(self):
        # Store tuples of (uuid_str, service_name)
        self.found_devices_info = []
        self.found_uuids = set()

    def add_cast(self, uuid_str, service_name):
        # This is called by the CastBrowser when zeroconf adds a service
        if uuid_str not in self.found_uuids:
            self.found_devices_info.append((uuid_str, service_name))
            self.found_uuids.add(uuid_str)

    def remove_cast(self, uuid_str, service_name, cast_info):
        # This is called by the CastBrowser when zeroconf removes a service
        if uuid_str in self.found_uuids:
            self.found_uuids.remove(uuid_str)
            # Remove matching tuple from list
            self.found_devices_info = [
                info for info in self.found_devices_info if info[0] != uuid_str
            ]


# --- Utility Functions ---
def get_local_ip():
    """Attempts to get the local IP address connected to the internet."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't actually send packets
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"  # Fallback
    finally:
        s.close()
    if ip.startswith("127."):
        print(
            "Warning: Could not determine non-localhost IP. Casting might fail.",
            file=sys.stderr,
        )
        print(
            "Ensure you are connected to the same network as the Google TV.",
            file=sys.stderr,
        )
    return ip


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
    else:
        if not Path(srt_path).exists():
            print(f"Error: SRT file not found at {srt_path}", file=sys.stderr)
            return None
        print("webvtt-py not found. Using simple conversion.", file=sys.stderr)
        print("For better results: pip install webvtt-py", file=sys.stderr)

    # Fallback / If webvtt not installed or failed
    if convert_srt_to_vtt_simple(srt_path, vtt_path):
        return vtt_path
    else:
        print("Subtitle conversion failed.", file=sys.stderr)
        return None


# --- Main Logic ---
def main():
    parser = argparse.ArgumentParser(
        description="Cast local video file to Google TV / Chromecast."
    )
    parser.add_argument("video", help="Path to the video file (e.g., MP4, MKV).")
    parser.add_argument("-s", "--srt", help="Path to SRT subtitle file (optional).")
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8080,
        help="Port for the local HTTP server (default: 8080).",
    )
    parser.add_argument(
        "--list-devices", action="store_true", help="List available devices and exit."
    )
    parser.add_argument(
        "--device-name",
        help="Specify the exact name of the device to cast to via discovery.",
    )
    parser.add_argument(
        "--host",
        help="Specify the IP address of the device to connect to directly, skipping discovery.",
    )

    args = parser.parse_args()

    cast_device = None
    browser = None
    listener = None
    zc = None  # Define zeroconf instance here

    # --- Device Selection/Connection ---
    if args.host:
        # --- Direct Connection ---
        print(f"Attempting direct connection to host: {args.host}")
        try:
            # Default port is 8009, usually correct
            cast_device = Chromecast(args.host)
            # Wait for connection validation. This might take a few seconds.
            cast_device.wait()
            print(
                f"Successfully connected to: {cast_device.name} ({cast_device.cast_type} @ {cast_device.host})"
            )
        except ChromecastConnectionError as e:
            print(f"Error: Failed to connect directly to {args.host}.", file=sys.stderr)
            print(f"Details: {e}", file=sys.stderr)
            print(
                "Please ensure the IP address is correct and the device is reachable.",
                file=sys.stderr,
            )
            sys.exit(1)

    else:
        # --- Discovery Method using CastBrowser ---
        print("Discovering devices using CastBrowser (waiting up to 15 seconds)...")

        listener = MyCastListener()  # Use custom listener
        # Create a zeroconf instance to pass to browser and use later
        zc = pychromecast.zeroconf.Zeroconf()
        browser = CastBrowser(listener, zc)

        try:
            browser.start_discovery()
            print("Waiting for devices...")
            time.sleep(15)
            print("Finished waiting.")
        finally:
            if browser:
                print("Stopping discovery...")
                browser.stop_discovery()
                print("Discovery stopped.")

        # Get discovered devices by processing the listener's info and zeroconf instance
        chromecasts = []
        if listener.found_devices_info:
            for uuid_str, service_name in listener.found_devices_info:
                # Get the ServiceInfo object from the zeroconf instance
                service_info = zc.get_service_info(
                    "_googlecast._tcp.local.", service_name
                )
                if service_info:
                    try:
                        # Create CastInfo from ServiceInfo
                        properties = service_info.properties_as_dict()
                        host = service_info.first_address_as_string()
                        port = service_info.port
                        uuid_obj = uuid.UUID(uuid_str)
                        friendly_name = properties.get("fn", service_name.split(".")[0])
                        model_name = properties.get("md", "Unknown Model")
                        cast_type = properties.get(
                            "ca", pychromecast.const.CAST_TYPE_CHROMECAST
                        )

                        cast_info = CastInfo(
                            service=service_name,
                            uuid=uuid_obj,
                            model_name=model_name,
                            friendly_name=friendly_name,
                            host=host,
                            port=port,
                            cast_type=cast_type,
                            manufacturer="Unknown",
                        )
                        # Create Chromecast object using the shared zeroconf instance
                        cc = pychromecast.get_chromecast_from_cast_info(cast_info, zc)
                        chromecasts.append(cc)
                    except Exception as e:
                        print(
                            f"Warning: Could not process discovered device {service_name}: {e}",
                            file=sys.stderr,
                        )
                else:
                    print(
                        f"Warning: Could not get ServiceInfo for {service_name} from zeroconf instance after discovery.",
                        file=sys.stderr,
                    )

        # Close the zeroconf instance now that we're done with it for discovery
        if zc:
            zc.close()

        # Filter by name if provided *after* discovery
        if args.device_name:
            filtered_casts = [
                cast for cast in chromecasts if cast.name == args.device_name
            ]
            if not filtered_casts:
                print(
                    f"Error: Device named '{args.device_name}' not found among discovered devices.",
                    file=sys.stderr,
                )
                sys.exit(1)
            chromecasts = filtered_casts  # Use the filtered list

        if args.list_devices:
            if not chromecasts:
                print("No devices found on the network.")
            else:
                print("Available devices:")
                sorted_casts = sorted(chromecasts, key=lambda cast: cast.name)
                for i, cast in enumerate(sorted_casts):
                    try:
                        cast.wait(timeout=1)
                        print(
                            f"  [{i}] {cast.name} ({cast.cast_type} @ {cast.host}:{cast.port})"
                        )
                    except ChromecastConnectionError:
                        print(f"  [{i}] {cast.name} (Unable to connect for details)")

            sys.exit(0)

        if not chromecasts:
            print("Error: No Google Cast devices found via discovery.", file=sys.stderr)
            print(
                "Ensure your device is on and connected to the same Wi-Fi network.",
                file=sys.stderr,
            )
            print(
                "Alternatively, try specifying the device IP using --host <ip_address>",
                file=sys.stderr,
            )
            sys.exit(1)

        # --- Select Device from Discovery List ---
        sorted_casts = sorted(chromecasts, key=lambda cast: cast.name)

        if len(sorted_casts) == 1:
            cast_device = sorted_casts[0]
            print(f"Found one device via discovery: {cast_device.name}")
        else:
            print("Multiple devices found. Please select one:")
            for i, cast in enumerate(sorted_casts):
                try:
                    cast.wait(timeout=1)
                    print(f"  [{i}] {cast.name} ({cast.cast_type})")
                except ChromecastConnectionError:
                    print(f"  [{i}] {cast.name} (Unable to connect for details)")

            while cast_device is None:
                try:
                    choice = input("Enter the number of the device: ")
                    index = int(choice.strip())
                    if 0 <= index < len(sorted_casts):
                        cast_device = sorted_casts[index]
                    else:
                        print("Invalid number.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
                except EOFError:
                    print("\nSelection cancelled.")
                    sys.exit(1)

        print(f"Connecting to selected device: {cast_device.name}")
        try:
            cast_device.wait()
            print("Connected.")
        except ChromecastConnectionError as e:
            print(
                f"Error: Failed to connect to selected device {cast_device.name}.",
                file=sys.stderr,
            )
            print(f"Details: {e}", file=sys.stderr)
            sys.exit(1)

    # --- Prepare Files and Server ---
    video_path_orig = Path(args.video).resolve()
    srt_path_orig = Path(args.srt).resolve() if args.srt else None
    temp_dir_path = None
    original_cwd = Path.cwd()
    httpd = None
    server_thread = None

    if not video_path_orig.exists():
        sys.exit(f"Error: Video file not found: {video_path_orig}")
    if srt_path_orig and not srt_path_orig.exists():
        sys.exit(f"Error: Subtitle file not found: {srt_path_orig}")

    try:
        temp_dir_path = Path(tempfile.mkdtemp(prefix="pycast_"))
        print(f"Created temporary directory: {temp_dir_path}")

        video_filename = video_path_orig.name
        video_path_temp = temp_dir_path / video_filename
        try:
            os.symlink(video_path_orig, video_path_temp)
        except OSError:
            print("Symlink failed, copying video...")
            shutil.copy(video_path_orig, video_path_temp)

        vtt_path_temp = None
        vtt_filename = None
        if srt_path_orig:
            vtt_path_temp = convert_srt_to_vtt(srt_path_orig, temp_dir_path)
            if not vtt_path_temp:
                raise Exception("Subtitle conversion failed")
            vtt_filename = vtt_path_temp.name

        local_ip = get_local_ip()
        port = args.port
        video_url = f"http://{local_ip}:{port}/{video_filename}"
        subtitle_url = (
            f"http://{local_ip}:{port}/{vtt_filename}" if vtt_filename else None
        )

        os.chdir(temp_dir_path)
        handler = SimpleHTTPRequestHandler
        httpd = ThreadingHTTPServer(("", port), handler)
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        print(f"Local HTTP server running at http://{local_ip}:{port}/")
        print(f"Serving files from: {temp_dir_path}")

        print(f"Preparing to cast on {cast_device.name}...")
        cast_device.wait()

        mc = cast_device.media_controller
        print(f"Casting {video_filename}...")

        content_type = "video/mp4"
        if video_path_orig.suffix.lower() == ".mkv":
            content_type = "video/x-matroska"
        elif video_path_orig.suffix.lower() == ".webm":
            content_type = "video/webm"

        mc.play_media(
            video_url,
            content_type,
            title=video_filename,
            thumb=None,
            subtitles=subtitle_url,
            subtitles_lang="en-US",
            subtitles_mime="text/vtt",
            autoplay=True,
        )

        mc.block_until_active()
        print(f"Playback started on {cast_device.name}. Press Ctrl+C to stop server.")

        while server_thread.is_alive():
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt received. Stopping server and cast...")
        if cast_device and cast_device.media_controller:
            try:
                cast_device.media_controller.stop()
                print("Sent stop command to device.")
            except Exception as e:
                print(f"Could not send stop command: {e}", file=sys.stderr)
        if httpd:
            httpd.shutdown()
            httpd.server_close()
        if server_thread:
            server_thread.join(timeout=2)

    except Exception as e:
        print(f"\nAn error occurred: {e}", file=sys.stderr)

    finally:
        os.chdir(original_cwd)
        if temp_dir_path and temp_dir_path.exists():
            try:
                shutil.rmtree(temp_dir_path)
                print(f"Removed temporary directory: {temp_dir_path}")
            except OSError as e:
                print(
                    f"Error removing temporary directory {temp_dir_path}: {e}",
                    file=sys.stderr,
                )
        print("Exiting.")


if __name__ == "__main__":
    main()
