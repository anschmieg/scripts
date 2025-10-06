import subprocess
import logging


def start_hidden(app_name):
    logging.info(f"Starting {app_name} hidden...")
    launch_script = f"""
    on startHidden(appName)
        tell application appName
            launch without activating
        end tell
        tell application "System Events"
            set visible of application process appName to false
        end tell
    end startHidden

    startHidden("{app_name}")
    """
    subprocess.run(["osascript", "-e", launch_script], check=True)
    logging.info(f"{app_name} started hidden successfully.")


def open_foreground_app(app_config):
    logging.info(f"Opening {app_config['name']} in foreground...")
    if len(app_config) == 1 and "name" in app_config:
        script = f'tell application "{app_config["name"]}" to activate'
    else:
        app_name = app_config["name"]
        if app_name in ["Safari", "Google Chrome", "Chromium", "Firefox", "Waterfox"]:
            script = f"""
            tell application "{app_name}"
                activate
                open location "{app_config['url']}"
            end tell
            """
        elif app_name == "Arc":
            script = f"""
            tell application "Arc"
            tell front window
                tell space "{app_config['space']}"
                make new tab with properties {{URL:"{app_config['url']}"}}
                end tell
            end tell
            activate
            end tell
            """
        else:
            args = " ".join(
                [
                    f"--{key} {value}"
                    for key, value in app_config.items()
                    if key != "name"
                ]
            )
            script = f"""
            if application "{app_name}" is running then
                tell application "{app_name}"
                    activate
                end tell
            else
                do shell script "open -a {app_name} --args {args}"
            end if
            """
    subprocess.run(["osascript", "-e", script], check=True)
    logging.info(f"{app_config['name']} opened in foreground successfully.")


def close_app(app_config):
    logging.info(f"Closing {app_config['name']}...")
    if "name" not in app_config:
        logging.error("App config must contain a 'name' key.")
        raise ValueError("App config must contain a 'name' key.")

    if len(app_config) == 1:
        close_script = f"""
        tell application "{app_config['name']}"
            quit
        end tell
        """
    else:
        args = " ".join(
            [f"--{key} {value}" for key, value in app_config.items() if key != "name"]
        )
        close_script = f"""
        if application "{app_config['name']}" is running then
            tell application "{app_config['name']}"
                quit
            end tell
        else
            do shell script "open -a {app_config['name']} --args {args}"
        end if
        """
    subprocess.run(["osascript", "-e", close_script], check=True)
    logging.info(f"{app_config['name']} closed successfully.")
