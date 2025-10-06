# My Raycast Extension

This project is a Raycast extension that allows users to log their work hours efficiently. It includes scripts for logging on and off, managing applications, and creating calendar entries.

## Features

- **Log On**: Starts tracking time, launches Slack, Mail, and "sipgate CLINQ", and opens a specified Jira board in the Arc browser using the "work" profile.
- **Log Off**: Stops tracking time, creates a calendar entry named "Arbeitszeit" with the start and end times, closes Slack, "sipgate CLINQ", and all Arc windows in the work profile. Prompts the user for input regarding their work to append to the calendar entry.

## Setup Instructions

1. Clone the repository to your local machine.
2. Ensure you have Python installed.
3. Install any necessary dependencies for the scripts.
4. Configure Raycast to run the scripts located in the `scripts` directory.

## Usage

- To log on, run the `log_on.py` script.
- To log off, run the `log_off.py` script.
- Follow the prompts to enter any additional notes when logging off.

## License

This project is licensed under the MIT License.