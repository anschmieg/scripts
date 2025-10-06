#!/usr/bin/env python3

import time
import sys
import logging
import argparse
import subprocess
from datetime import datetime
from typing import Optional
from utils.config import load_config, save_logon_time, validate_config, set_config_file
from utils.app_manager import start_hidden, open_foreground_app, close_app
from utils.calendar import create_calendar_event

RETRY_LIMIT = 3

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def start_session():
    config = load_config()
    validate_config(config, ["apps_to_open", "foreground_app"])

    start_time = int(time.time())
    save_logon_time(config, start_time)
    logging.info("Tracking time started...")

    try:
        for app in config["apps_to_open"]:
            for attempt in range(RETRY_LIMIT):
                try:
                    start_hidden(app)
                    break
                except subprocess.CalledProcessError as e:
                    logging.error(f"Error launching {app}: {e}")
                    if attempt < RETRY_LIMIT - 1:
                        logging.info(f"Retrying to launch {app}...")
                    else:
                        raise

        # Launch the foreground app last to stay on top
        open_foreground_app(config["foreground_app"])

        # Hide all other apps again to ensure they stay hidden
        for app in config["apps_to_open"]:
            hide_script = f"""
            tell application "System Events"
                set visible of application process "{app}" to false
            end tell
            """
            subprocess.run(["osascript", "-e", hide_script], check=True)

        # Display a centered toast notification
        notification_script = """
        display notification "Ready to go!" with title "Session Started"
        """
        subprocess.run(["osascript", "-e", notification_script], check=True)

    except subprocess.CalledProcessError as e:
        logging.error(f"Error during log on: {e}")
        sys.exit(1)


def get_user_input(prompt: str) -> Optional[str]:
    try:
        return input(prompt)
    except KeyboardInterrupt:
        return None


def stop_session() -> None:
    config = load_config()
    validate_config(config, ["calendar_name", "session_logon_time"])
    calendar_name = config["calendar_name"]

    logging.info("Tracking time stopped...")

    try:
        for app in config["apps_to_open"]:
            for attempt in range(RETRY_LIMIT):
                try:
                    close_app(app)
                    break
                except subprocess.CalledProcessError as e:
                    logging.error(f"Error closing {app}: {e}")
                    if attempt < RETRY_LIMIT - 1:
                        logging.info(f"Retrying to close {app}...")
                    else:
                        raise

        start_timestamp = config["session_logon_time"]
        if start_timestamp is None:
            raise ValueError("Starting time not found in config file.")
        start_time = datetime.fromtimestamp(start_timestamp)
        end_time = datetime.now()

        notes = get_user_input("Woran hast du gearbeitet? ")

        create_calendar_event(calendar_name, start_time, end_time, notes or "")

        logging.info("Successfully logged off!")

    except subprocess.CalledProcessError as e:
        logging.error(f"Error during log off: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        sys.exit(1)


def shutdown():
    logging.info("Shutting down gracefully...")
    # Add any necessary cleanup code here


if __name__ == "__main__":
    logging.info("Script started.")
    parser = argparse.ArgumentParser(description="Main script")
    parser.add_argument(
        "action",
        choices=["start", "stop"],
        help="Action to perform: start or stop",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to the configuration file",
        default="config.json",  # Updated to current directory
    )
    args = parser.parse_args()

    logging.info(f"Action: {args.action}")
    logging.info(f"Config file: {args.config}")

    set_config_file(args.config)

    try:
        if args.action == "start":
            start_session()
        elif args.action == "stop":
            stop_session()
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        shutdown()
        sys.exit(1)
