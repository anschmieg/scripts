import subprocess
import logging


def applescript(script: str):
    logging.info("Running AppleScript...")
    subprocess.run(["osascript", "-e", script], check=True)
    logging.info("AppleScript executed successfully.")
