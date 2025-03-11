#!/usr/bin/env python3
"""
Migration script to transition from Pinecone Vector DB to Pinecone Assistant
"""

import argparse
import logging
import os
import sys
import time
from typing import Dict, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

from rag_processor.core.config import CONFIG
from rag_processor.core.file_utils import load_processed_files, save_processed_files
from rag_processor.core.logging_setup import setup_logging
from rag_processor.pinecone.uploader import upload_file_to_assistant

# Force load environment variables from .env with priority over existing env vars
load_dotenv(override=True)

# Get logger
logger = logging.getLogger(__name__)


def get_files_to_migrate(check_path: bool = True) -> List[Dict]:
    """
    Get files from tracking JSON that need to be migrated to Assistant.

    Args:
        check_path: If True, verify that files still exist on disk

    Returns:
        List of file entries to migrate
    """
    processed_files = load_processed_files()

    if not processed_files:
        logger.warning("No processed files found in tracking JSON")
        return []

    # Filter files that don't have an Assistant ID yet
    to_migrate = []

    for filename, data in processed_files.items():
        # Skip if already has Assistant ID
        if "assistant_file_id" in data:
            continue

        # Get file path
        file_path = data.get("path")
        if not file_path:
            # Try to reconstruct from TARGET_FOLDER
            file_path = os.path.join(CONFIG["TARGET_FOLDER"], filename)

        # Check if file exists if requested
        if check_path and not os.path.exists(file_path):
            logger.warning(f"File not found, skipping: {file_path}")
            continue

        # Add to migration list
        to_migrate.append({"filename": filename, "path": file_path, "data": data})

    return to_migrate


def migrate_files(
    files_to_migrate: List[Dict],
    dry_run: bool = False,
    batch_size: int = 10,
    delay: int = 1,
) -> int:
    """
    Migrate files from tracking JSON to Pinecone Assistant.

    Args:
        files_to_migrate: List of files to migrate
        dry_run: If True, don't actually migrate files
        batch_size: Number of files to process before saving tracking JSON
        delay: Delay in seconds between file uploads

    Returns:
        Number of files successfully migrated
    """
    if not files_to_migrate:
        logger.info("No files to migrate")
        return 0

    logger.info(f"Found {len(files_to_migrate)} files to migrate to Pinecone Assistant")

    if dry_run:
        logger.info("Dry run mode - no files will be uploaded")
        for i, file_info in enumerate(files_to_migrate[:5]):
            logger.info(f" {i + 1}. Would migrate: {file_info['path']}")
        if len(files_to_migrate) > 5:
            logger.info(f" ... and {len(files_to_migrate) - 5} more files")
        return 0

    # Load processed files for updating
    processed_files = load_processed_files()

    # Track migration
    migrated_count = 0
    error_count = 0

    # Process files in batches
    for i, file_info in enumerate(files_to_migrate):
        filename = file_info["filename"]
        file_path = file_info["path"]

        logger.info(f"Migrating {i + 1}/{len(files_to_migrate)}: {filename}")

        try:
            # Upload to Assistant using SDK
            result = upload_file_to_assistant(file_path)

            if result and ("id" in result or hasattr(result, "id")):
                # Get the ID regardless of whether result is a dict or SDK object
                result_id = (
                    result.get("id")
                    if isinstance(result, dict)
                    else getattr(result, "id")
                )
                logger.info(f"Successfully uploaded to Assistant with ID: {result_id}")

                # Update tracking with Assistant file ID
                if filename in processed_files:
                    processed_files[filename]["assistant_file_id"] = result_id
                    processed_files[filename]["path"] = (
                        file_path  # Ensure path is stored
                    )
                    migrated_count += 1
                else:
                    logger.warning(f"File not found in tracking JSON: {filename}")
            else:
                logger.error(f"Failed to upload {filename} to Assistant")
                error_count += 1

            # Save tracking JSON periodically
            if (i + 1) % batch_size == 0 or i == len(files_to_migrate) - 1:
                save_processed_files(processed_files)
                logger.info(f"Saved tracking JSON after processing {i + 1} files")

            # Add delay between uploads to avoid rate limits
            if i < len(files_to_migrate) - 1 and delay > 0:
                time.sleep(delay)

        except Exception as e:
            logger.error(f"Error migrating file {filename}: {e}")
            error_count += 1

    # Final stats
    logger.info(
        f"Migration complete: {migrated_count} files migrated, {error_count} errors"
    )
    return migrated_count


def main():
    parser = argparse.ArgumentParser(
        description="Migrate from Pinecone Vector DB to Pinecone Assistant"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry run mode (no actual uploads).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    parser.add_argument(
        "--skip-path-check",
        action="store_true",
        help="Skip checking if files exist on disk.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of files to process before saving tracking JSON (default: 10).",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=1,
        help="Delay in seconds between file uploads (default: 1).",
    )

    args = parser.parse_args()

    # Setup logging based on verbosity
    setup_logging(args.verbose)

    # Get files to migrate
    files_to_migrate = get_files_to_migrate(check_path=not args.skip_path_check)

    # Migrate files
    migrate_files(
        files_to_migrate,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
