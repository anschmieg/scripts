#!/usr/bin/env python3

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from assets.document_processor import process_documents

# Load environment variables from .env file
load_dotenv()

# Define your Pinecone API key and other configurations
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
TARGET_FOLDER = "path_to_your_TARGET_FOLDER"
NAMESPACE = "your_namespace"
INDEX_NAME = "your_index_name"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def main():
    """Main function with error handling."""
    try:
        parser = argparse.ArgumentParser(description="Process and upload documents.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the script in dry run mode (no uploads).",
        )
        parser.add_argument(
            "--dry-run-update-cache",
            action="store_true",
            help="When used with --dry-run, updates the processed files cache as if files were processed.",
        )
        args = parser.parse_args()

        # Add the arg to sys.argv to make it accessible in the process_documents function
        if (
            args.dry_run
            and args.dry_run_update_cache
            and "--dry-run-update-cache" not in sys.argv
        ):
            sys.argv.append("--dry-run-update-cache")

        process_documents(dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"Unexpected error in document processing: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
