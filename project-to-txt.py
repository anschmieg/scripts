import argparse
import os
import sys

# Default blacklist of files and directories to ignore
DEFAULT_BLACKLIST = [
    ".*",
    "__pycache__",
    "venv",
    "node_modules",
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.code-workspace",
    "go.sum",
]


def is_blacklisted(path, blacklist):
    """Check if a file or directory should be ignored based on the blacklist."""
    # Only use the basename (filename) for comparison, not the full path
    basename = os.path.basename(path)

    # Check exact matches
    if basename in blacklist:
        return True

    # Check wildcard patterns (simple implementation)
    for pattern in blacklist:
        if pattern.startswith("*") and basename.endswith(pattern[1:]):
            return True
        elif pattern.endswith("*") and basename.startswith(pattern[:-1]):
            return True

    return False


def list_files_and_contents(root_dir=".", blacklist=None):
    if blacklist is None:
        blacklist = DEFAULT_BLACKLIST

    # Fix: Add proper handling for the root directory path
    root_dir_name = os.path.basename(os.path.abspath(root_dir))
    parent_dir = os.path.dirname(os.path.abspath(root_dir))
    print(f"# Files in the project directory {root_dir_name} ({parent_dir})")

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Filter out blacklisted directories
        dirnames[:] = [
            d
            for d in dirnames
            if not is_blacklisted(os.path.join(dirpath, d), blacklist)
        ]

        for filename in filenames:
            if filename.startswith(".") or is_blacklisted(
                os.path.join(dirpath, filename), blacklist
            ):
                continue

            file_path = os.path.join(dirpath, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    file_contents = file.read()
                relative_path = os.path.relpath(file_path, start=root_dir)
                print(f"{relative_path}\n```\n{file_contents}\n```")
            except Exception as e:
                print(f"Could not read {file_path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List files and their contents in a project directory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all files in current directory, using default blacklist
  python project-to-txt.py
  
  # List all files in a specific directory
  python project-to-txt.py /path/to/project
  
  # Override the default blacklist with custom patterns
  python project-to-txt.py --ignore "*.txt" "*.md" "build"
""",
    )
    parser.add_argument(
        "root_folder",
        nargs="?",
        default=".",
        help="Root folder to start scanning (default: current directory)",
    )
    parser.add_argument(
        "--ignore",
        "-i",
        nargs="+",
        help=f"Blacklist of files and directories to ignore (overrides default blacklist: {', '.join(DEFAULT_BLACKLIST)})",
    )

    # Add an option to show the default blacklist
    parser.add_argument(
        "--show-default-blacklist",
        action="store_true",
        help="Show the default blacklist and exit",
    )

    args = parser.parse_args()

    # Show default blacklist if requested
    if hasattr(args, "show_default_blacklist") and args.show_default_blacklist:
        print("Default blacklist patterns:")
        for pattern in DEFAULT_BLACKLIST:
            print(f"  - {pattern}")
        sys.exit(0)

    # Use custom blacklist if provided, otherwise use default
    blacklist = args.ignore if args.ignore else DEFAULT_BLACKLIST

    list_files_and_contents(args.root_folder, blacklist)
