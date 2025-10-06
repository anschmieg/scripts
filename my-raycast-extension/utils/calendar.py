import subprocess


def create_calendar_event(calendar_name, start_date, end_date, notes):
    calendar_script = f"""
    tell application "Calendar"
        tell calendar "{calendar_name}"
            make new event with properties {{
                summary:"Arbeitszeit", 
                start date:date "{start_date}", 
                end date:date "{end_date}", 
                description:"{notes}"
            }}
        end tell
    end tell
    """
    subprocess.run(["osascript", "-e", calendar_script], check=True)
