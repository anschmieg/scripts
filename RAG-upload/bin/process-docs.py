#!/usr/bin/env python3
"""
Main entry point for document processing
"""

import argparse
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

from rag_processor.core.config import CONFIG
from rag_processor.core.logging_setup import setup_logging
from rag_processor.processor.document_processor import process_documents

# Force load environment variables from .env with priority over existing env vars
load_dotenv(override=True)


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
        parser.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Enable verbose debug logging.",
        )
        parser.add_argument(
            "--debug-env",
            action="store_true",
            help="Print debug information about environment variables and paths.",
        )
        parser.add_argument(
            "--no-recursive",
            action="store_true",
            help="Don't search subdirectories recursively.",
        )
        parser.add_argument(
            "--target",
            type=str,
            help="Override target folder (default from .env)",
        )
        args = parser.parse_args()

        # Setup logging with the appropriate verbosity
        setup_logging(args.verbose)
        logger = logging.getLogger(__name__)

        # Add the arg to sys.argv to make it accessible in the process_documents function
        if (
            args.dry_run
            and args.dry_run_update_cache
            and "--dry-run-update-cache" not in sys.argv
        ):
            sys.argv.append("--dry-run-update-cache")

        # Print environment debug info if requested
        if args.debug_env:
            # Import here to avoid circular imports
            from tools.debugger import check_config, debug_environment

            debug_environment()
            check_config()
            return

        # Use target folder from args if provided, otherwise from CONFIG
        target_folder = args.target if args.target else CONFIG["TARGET_FOLDER"]

        logger.debug(f"TARGET_FOLDER: {target_folder}")
        logger.debug(f"Namespace: {CONFIG['namespace']}")
        logger.debug(f"Index Name: {CONFIG['index_name']}")

        # Pass parameters to process_documents
        process_documents(
            target_folder=target_folder,
            dry_run=args.dry_run,
            recursive=not args.no_recursive,
        )
    except Exception as e:
        logger.error(f"Unexpected error in document processing: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
