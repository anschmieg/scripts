import csv
import io
import json
import argparse
import os
import shutil
from datetime import datetime


def print_table(json_data, base_file_name):
    subsequent_dicts = []
    for key, value in json_data.items():
        if isinstance(value, dict):
            subsequent_dicts.append((key, value))
        elif isinstance(value, list):
            os.makedirs(base_file_name, exist_ok=True)
            with open(os.path.join(base_file_name, f"{key}.csv"), "w", newline="") as f:
                writer = csv.writer(f)
                if value and all(isinstance(i, dict) for i in value):
                    headers = value[0].keys()
                    writer.writerow(headers)
                    for row in value:
                        writer.writerow(row.values())
                else:
                    writer.writerows(value)
        else:
            os.makedirs(base_file_name, exist_ok=True)
            with open(os.path.join(base_file_name, f"{key}.txt"), "w") as f:
                f.write(str(value))
    for key, value in subsequent_dicts:
        print_table(value, os.path.join(base_file_name, key))


def read_json_file(file_path):
    with open(file_path) as file:
        data = json.load(file)
    return data


def cleanup(output_folder):
    # Move analysis/bookings.csv to the root folder, then remove all folders
    bookings_file = os.path.join(output_folder, "analysis", "bookings.csv")
    if os.path.exists(bookings_file):
        os.rename(bookings_file, os.path.join(output_folder, "bookings.csv"))
    for root, dirs, files in os.walk(output_folder, topdown=False):
        for name in dirs:
            shutil.rmtree(os.path.join(root, name))
    return


def main():
    parser = argparse.ArgumentParser(
        description="Read a JSON file and display the data as a table. Coined towards Finanzguru exported data."
    )
    parser.add_argument("file_path", help="Path to the input JSON file")
    parser.add_argument("--cleanup", help="Remove all files except bookings", action="store_true")
    args = parser.parse_args()
    json_data = read_json_file(args.file_path)
    output_folder = "Finanzguru_data_" + datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    print_table(json_data, output_folder)
    if args.cleanup:
        print("Removing all read files except bookings.csv")
        cleanup(output_folder)
    print("Data has been written to the folder: " + output_folder)
    return output_folder


if __name__ == "__main__":
    main()
