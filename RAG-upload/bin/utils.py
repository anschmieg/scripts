#!/usr/bin/env python3
"""
Utility functions for RAG Processor
"""

import argparse
import logging
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

from rag_processor.core.config import CONFIG
from rag_processor.core.logging_setup import setup_logging
from rag_processor.pinecone.client import get_pinecone_index
from rag_processor.pinecone.uploader import upload_file_to_pinecone
from rag_processor.processor.document_processor import process_documents

# Force load environment variables from .env with priority over existing env vars
load_dotenv(override=True)

# Get logger
logger = logging.getLogger(__name__)


def upload_single_file(file_path: str, dry_run: bool = False):
    """Upload a single file to Pinecone."""
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        logger.error("Pinecone API key not found in .env file")
        return False

    try:
        if dry_run:
            logger.info(f"DRY RUN: Would upload file {file_path} to Pinecone")
            logger.debug(
                f"DRY RUN: File metadata - Size: {os.path.getsize(file_path)} bytes"
            )
            return True

        index = get_pinecone_index()
        if not index:
            logger.error("Failed to initialize Pinecone index")
            return False

        # Upload the file
        if upload_file_to_pinecone(file_path, index, CONFIG["namespace"]):
            logger.info(f"Successfully uploaded {file_path} to Pinecone.")
            return True
        else:
            logger.error(f"Failed to upload {file_path} to Pinecone.")
            if logging.getLogger().level == logging.DEBUG:
                logger.debug(f"File details for {file_path}:")
                logger.debug(f"  - Size: {os.path.getsize(file_path)} bytes")
                logger.debug(
                    f"  - Created: {datetime.fromtimestamp(os.path.getctime(file_path)).strftime('%Y-%m-%d %H:%M:%S')}"
                )
                logger.debug(
                    f"  - Modified: {datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')}"
                )
            return False
    except Exception as e:
        logger.error(f"Failed to process file: {e}")
        return False


def validate_database(
    reupload=False, check_disk=False, clean=False, check_untracked=False
):
    """Validate the database against processed files tracking."""
    from rag_processor.pinecone.validator import (
        cleanup_tracking_json,
        find_untracked_pinecone_documents,
        validate_database_integrity,
    )

    namespace = CONFIG["namespace"]
    logger.info(
        f"Validating database integrity for namespace: '{namespace or 'default'}'"
    )

    # Check for files missing from Pinecone
    missing_files, _ = validate_database_integrity(
        namespace=namespace, auto_reupload=False
    )

    if missing_files:
        logger.warning(
            f"Found {len(missing_files)} files missing from Pinecone database"
        )
        for file in missing_files[:10]:  # Show first 10 files only
            logger.info(f"Missing: {os.path.basename(file)}")

        if len(missing_files) > 10:
            logger.info(f"... and {len(missing_files) - 10} more files")

        if reupload:
            logger.info("Re-uploading missing files...")
            _, reuploaded = validate_database_integrity(
                namespace=namespace, auto_reupload=True
            )
            logger.info(f"Re-uploaded {reuploaded} of {len(missing_files)} files")
    else:
        logger.info("All tracked files are present in Pinecone database")

    # Check for files missing from disk
    if check_disk:
        logger.info("Checking for tracked files missing from disk...")
        missing_count = cleanup_tracking_json(remove_missing=clean)

        if missing_count > 0:
            logger.warning(
                f"Found {missing_count} files in tracking JSON that don't exist on disk"
            )
            if clean:
                logger.info(f"Removed {missing_count} entries from tracking JSON")
        else:
            logger.info("All tracked files exist on disk")

    # Check for untracked Pinecone documents
    if check_untracked:
        logger.info("Checking for untracked Pinecone documents...")
        untracked = find_untracked_pinecone_documents(namespace=namespace)

        if untracked:
            logger.warning(
                f"Found {len(untracked)} documents in Pinecone that aren't in tracking JSON"
            )
            for doc in untracked[:10]:  # Show first 10
                logger.info(f"Untracked: {doc}")

            if len(untracked) > 10:
                logger.info(f"... and {len(untracked) - 10} more documents")
        else:
            logger.info("All Pinecone documents are tracked in JSON")


def main():
    parser = argparse.ArgumentParser(description="Utility functions for RAG Processor")

    # Define subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Process command
    process_parser = subparsers.add_parser(
        "process", help="Process documents in the target folder"
    )
    process_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry run mode (no actual uploads).",
    )
    process_parser.add_argument(
        "--dry-run-update-cache",
        action="store_true",
        help="When used with --dry-run, updates the processed files cache.",
    )
    process_parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Don't search subdirectories recursively.",
    )
    process_parser.add_argument(
        "--target",
        type=str,
        help="Override target folder (default from .env)",
    )

    # Upload command
    upload_parser = subparsers.add_parser(
        "upload", help="Upload a single file to Pinecone"
    )
    upload_parser.add_argument(
        "file_path",
        type=str,
        help="Path to the file to upload",
    )
    upload_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry run mode (no actual upload).",
    )

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate database against processed files tracking"
    )
    validate_parser.add_argument(
        "--reupload", action="store_true", help="Re-upload missing files"
    )
    validate_parser.add_argument(
        "--check-disk", action="store_true", help="Check if tracked files exist on disk"
    )
    validate_parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove entries from tracking JSON for files that don't exist on disk",
    )
    validate_parser.add_argument(
        "--check-untracked",
        action="store_true",
        help="Check for documents in Pinecone that aren't in tracking JSON",
    )

    # Global options
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    parser.add_argument(
        "--debug-env",
        action="store_true",
        help="Print debug information about environment variables.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force processing of large files without confirmation.",
    )

    args = parser.parse_args()

    # Setup logging based on verbosity
    setup_logging(args.verbose)

    # Handle debug environment request
    if args.debug_env:
        # Import here to avoid circular imports
        from tools.debugger import check_config, debug_environment

        debug_environment()
        check_config()
        return

    # Log the current operation mode
    logger.debug(f"Command line arguments: {sys.argv}")

    # Add force flag to sys.argv if specified
    if args.force and "--force" not in sys.argv:
        sys.argv.append("--force")

    # Handle the chosen command
    if args.command == "process":
        # Add cache update to sys.argv if needed
        if (
            getattr(args, "dry_run", False)
            and getattr(args, "dry_run_update_cache", False)
            and "--dry-run-update-cache" not in sys.argv
        ):
            sys.argv.append("--dry-run-update-cache")

        logger.info(
            f"{'DRY RUN: ' if getattr(args, 'dry_run', False) else ''}Processing documents..."
        )
        target_folder = (
            args.target
            if hasattr(args, "target") and args.target
            else CONFIG["TARGET_FOLDER"]
        )
        process_documents(
            target_folder=target_folder,
            dry_run=getattr(args, "dry_run", False),
            recursive=not getattr(args, "no_recursive", False),
        )
    elif args.command == "upload":
        if os.path.exists(args.file_path):
            upload_single_file(args.file_path, dry_run=args.dry_run)
        else:
            logger.error(f"File not found: {args.file_path}")
            sys.exit(1)
    elif args.command == "validate":
        validate_database(
            reupload=args.reupload,
            check_disk=args.check_disk,
            clean=args.clean,
            check_untracked=args.check_untracked,
        )
    else:
        # If no command specified, show help
        parser.print_help()


if __name__ == "__main__":
    main()
