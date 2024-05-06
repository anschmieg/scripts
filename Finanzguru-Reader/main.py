import os
import argparse
from SplitterReader import main as read_split
from Bookings import main as plot_bookings


def main():
    parser = argparse.ArgumentParser(
        description="Read a JSON file and display the data as a table. Coined towards Finanzguru exported data."
    )
    parser.add_argument("file_path", help="Path to the input JSON file")
    parser.add_argument(
        "--cleanup", help="Remove all files except bookings", action="store_true"
    )
    args = parser.parse_args()
    bookings_folder = read_split(args.file_path, args.cleanup)
    bookings_file = os.path.join(bookings_folder, "bookings.csv")
    bookings = plot_bookings(bookings_file)
    return bookings


if __name__ == "__main__":
    main()
