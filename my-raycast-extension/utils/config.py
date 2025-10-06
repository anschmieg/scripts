import json
import logging

CONFIG_FILE = "config.json"  # Default path


def set_config_file(path):
    global CONFIG_FILE
    CONFIG_FILE = path


def load_config():
    logging.info("Loading configuration...")
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    logging.info("Configuration loaded successfully.")
    return config


def save_logon_time(config, timestamp):
    logging.info("Saving logon time...")
    config["session_logon_time"] = timestamp
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
    logging.info("Logon time saved successfully.")


def validate_config(config, required_keys):
    logging.info("Validating configuration...")
    for key in required_keys:
        if key not in config:
            logging.error(f"Missing required config key: {key}")
            raise ValueError(f"Missing required config key: {key}")
    logging.info("Configuration validated successfully.")
