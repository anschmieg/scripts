#!/usr/bin/env python3
"""
Utility functions for RAG Processor
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import List

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rag_processor.core.config import CONFIG
from rag_processor.core.env import load_environment_variables
from rag_processor.core.logging_setup import (
    check_config,
    debug_environment,
    setup_logging,
)

# Import the client module directly and use the appropriate class inside the functions
from rag_processor.pinecone import client as pinecone_client
from rag_processor.processor.document_processor import process_documents

# Force load environment variables from .env with priority over existing env vars
load_environment_variables(override=True)

# Get logger
logger = logging.getLogger(__name__)


def upload_single_file(file_path: str, dry_run: bool = False):
    """Upload a single file to Pinecone Assistant."""
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        logger.error("Pinecone API key not found in .env file")
        return False

    try:
        if dry_run:
            logger.info(f"DRY RUN: Would upload file {file_path} to Pinecone Assistant")
            logger.debug(
                f"DRY RUN: File metadata - Size: {os.path.getsize(file_path)} bytes"
            )
            return True

        # Import here to avoid circular imports
        from rag_processor.pinecone.uploader import upload_file_to_assistant

        # Upload the file
        result = upload_file_to_assistant(file_path)
        if result and "id" in result:
            logger.info(
                f"Successfully uploaded {file_path} to Pinecone Assistant (ID: {result['id']})."
            )

            # Update tracking with new Assistant file ID
            from rag_processor.core.file_utils import (
                load_processed_files,
                save_processed_files,
                update_processed_files_tracking,
            )

            processed_files = load_processed_files()
            filename = os.path.basename(file_path)
            update_processed_files_tracking(file_path, filename, processed_files)
            processed_files[filename]["assistant_file_id"] = result["id"]
            save_processed_files(processed_files)

            return True
        else:
            logger.error(f"Failed to upload {file_path} to Pinecone Assistant.")
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


def upload_multiple_files(
    file_paths: List[str],
    dry_run: bool = False,
    parallel: int = 3,
    batch_size: int = 10,
    show_progress: bool = False,
):
    """Upload multiple files to Pinecone Assistant with optimized batch processing."""
    if dry_run:
        for file_path in file_paths:
            logger.info(f"DRY RUN: Would upload file {file_path} to Pinecone Assistant")
            logger.debug(
                f"DRY RUN: File metadata - Size: {os.path.getsize(file_path)} bytes"
            )
        return True

    # Import here to avoid circular imports
    from rag_processor.core.file_utils import (
        load_processed_files,
        save_processed_files,
        update_processed_files_tracking,
    )
    from rag_processor.pinecone.uploader import upload_files

    processed_files = load_processed_files()

    # Upload files using batch uploader
    results = upload_files(
        file_paths,
        parallel=parallel,
        batch_size=batch_size,
        show_progress=show_progress,
    )

    # Process results and update tracking
    success_count = 0
    error_count = 0

    for file_path in file_paths:
        filename = os.path.basename(file_path)
        result = results.get(filename)

        if (
            result
            and isinstance(result, dict)
            and "id" in result
            and "error" not in result
        ):
            # Update tracking
            update_processed_files_tracking(file_path, filename, processed_files)
            processed_files[filename]["assistant_file_id"] = result["id"]
            logger.info(f"Successfully uploaded {filename} (ID: {result['id']})")
            success_count += 1
        else:
            error_msg = (
                result.get("error", "Unknown error")
                if isinstance(result, dict)
                else "Upload failed"
            )
            logger.error(f"Failed to upload {filename}: {error_msg}")
            error_count += 1

    # Save updated tracking
    if success_count > 0:
        save_processed_files(processed_files)

    logger.info(
        f"Batch upload complete: {success_count} successful, {error_count} failed"
    )
    return success_count > 0


def validate_database(
    reupload=False, check_disk=False, clean=False, check_untracked=False
):
    """Validate the database against processed files tracking."""
    from rag_processor.assistant.validator import (
        cleanup_tracking_json,
        find_untracked_assistant_files,
        validate_assistant_integrity,
    )

    logger.info("Validating Pinecone Assistant integration")

    # Check for files missing from Assistant
    missing_files, _, _ = validate_assistant_integrity(auto_reupload=False)

    if missing_files:
        logger.warning(
            f"Found {len(missing_files)} files missing from Pinecone Assistant"
        )
        for file in missing_files[:10]:  # Show first 10 files only
            logger.info(f"Missing: {os.path.basename(file)}")

        if len(missing_files) > 10:
            logger.info(f"... and {len(missing_files) - 10} more files")

        if reupload:
            logger.info("Re-uploading missing files...")
            _, reuploaded, errors = validate_assistant_integrity(auto_reupload=True)
            logger.info(f"Re-uploaded {reuploaded} of {len(missing_files)} files")
            if errors > 0:
                logger.warning(f"Failed to re-upload {errors} files")
    else:
        logger.info("All tracked files are present in Pinecone Assistant")

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

    # Check for untracked Assistant files
    if check_untracked:
        logger.info("Checking for untracked Pinecone Assistant files...")
        untracked = find_untracked_assistant_files()

        if untracked:
            logger.warning(
                f"Found {len(untracked)} files in Pinecone Assistant that aren't in tracking JSON"
            )
            for file_id, file_data in list(untracked.items())[:10]:
                logger.info(f"Untracked: {file_data.get('name', file_id)}")

            if len(untracked) > 10:
                logger.info(f"... and {len(untracked) - 10} more files")
        else:
            logger.info("All Pinecone Assistant files are tracked in JSON")


def delete_files_from_assistant(file_ids, force=False, by_name=False):
    """
    Delete files from Pinecone Assistant by ID or name.

    Args:
        file_ids: List of file IDs or names to delete
        force: If True, skip confirmation prompt
        by_name: If True, delete files by name instead of ID
    """
    # Import here to avoid circular imports
    from rag_processor.core.file_utils import load_processed_files, save_processed_files

    # Look for the appropriate client class in the module
    if hasattr(pinecone_client, "AssistantClient"):
        client = pinecone_client.AssistantClient()
    elif hasattr(pinecone_client, "PineconeAssistantClient"):
        client = pinecone_client.PineconeAssistantClient()
    else:
        # Use whatever client class is available in the module
        client_classes = [
            cls
            for cls in dir(pinecone_client)
            if "client" in cls.lower() and not cls.startswith("_")
        ]
        if client_classes:
            client_class = getattr(pinecone_client, client_classes[0])
            client = client_class()
            logger.info(f"Using client class: {client_classes[0]}")
        else:
            logger.error(
                "Could not find an appropriate client class in the pinecone client module"
            )
            return

    files_to_delete = []

    # If deleting by name, get all files and filter by name
    if by_name:
        response = client.list_files()
        if "error" in response:
            logger.error(f"Failed to list files: {response['error']}")
            return

        all_files = response.get("files", [])

        # Find files matching the names
        for name_to_delete in file_ids:  # file_ids actually contains names in this case
            matching_files = []

            for file in all_files:
                # Extract filename from file object or dict
                filename = (
                    file.get("filename")
                    if isinstance(file, dict)
                    else getattr(file, "filename", None)
                )

                if filename == name_to_delete:
                    file_id = (
                        file.get("id")
                        if isinstance(file, dict)
                        else getattr(file, "id", None)
                    )
                    if file_id:
                        matching_files.append((file_id, filename))

            if matching_files:
                files_to_delete.extend(matching_files)
                logger.info(
                    f"Found {len(matching_files)} files matching name: {name_to_delete}"
                )
            else:
                logger.warning(f"No files found with name: {name_to_delete}")
    else:
        # Use the provided IDs directly
        for file_id in file_ids:
            # Try to get the file details to confirm it exists
            file_info = client.get_file(file_id)
            if "error" in file_info:
                logger.warning(f"File ID not found: {file_id}")
                continue

            filename = file_info.get("filename", "Unknown")
            files_to_delete.append((file_id, filename))

    # Confirm deletion unless forced
    if files_to_delete:
        logger.info(f"Found {len(files_to_delete)} files to delete:")
        for file_id, filename in files_to_delete:
            logger.info(f"  - {filename} (ID: {file_id})")

        if not force:
            confirm = input(f"Delete {len(files_to_delete)} files? (y/n): ")
            if confirm.lower() != "y":
                logger.info("Deletion cancelled")
                return
    else:
        logger.warning("No files found to delete")
        return

    # Delete the files
    deleted = 0
    for file_id, filename in files_to_delete:
        result = client.delete_file(file_id)

        if "success" in result and result["success"]:
            logger.info(f"Successfully deleted file: {filename} (ID: {file_id})")
            deleted += 1
        else:
            error = result.get("error", "Unknown error")
            logger.error(f"Failed to delete file {filename} (ID: {file_id}): {error}")

    # Update tracking.json to remove deleted files
    if deleted > 0:
        processed_files = load_processed_files()
        updated_processed_files = {}

        # Create set of deleted file IDs for faster lookup
        deleted_ids = {file_id for file_id, _ in files_to_delete}

        # Keep only the entries that weren't deleted
        for filepath, metadata in processed_files.items():
            file_id = metadata.get("assistant_file_id")
            if file_id not in deleted_ids:
                updated_processed_files[filepath] = metadata

        # Save the updated tracking data
        save_processed_files(updated_processed_files)
        logger.info(
            f"Updated tracking.json, removed {len(processed_files) - len(updated_processed_files)} entries"
        )


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
    # Add performance options
    process_parser.add_argument(
        "--parallel",
        "-p",
        type=int,
        default=5,  # Changed from 3 to 5
        help="Number of concurrent upload workers (default: 5)",
    )
    process_parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=20,  # Changed from 10 to 20
        help="Number of files to batch into a single request (default: 20)",
    )
    process_parser.add_argument(
        "--progress",
        action="store_true",
        default=True,  # Added default=True
        help="Show progress bar during processing (requires tqdm)",
    )
    # Add no-progress option to disable progress bar if needed
    process_parser.add_argument(
        "--no-progress",
        action="store_false",
        dest="progress",
        help="Disable progress bar",
    )

    # Upload command
    upload_parser = subparsers.add_parser(
        "upload", help="Upload a single file to Pinecone"
    )
    upload_parser.add_argument(
        "file_path",
        type=str,
        nargs="+",  # Allow multiple file paths
        help="Path to the file(s) to upload",
    )
    upload_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry run mode (no actual upload).",
    )
    # Add performance options for upload command too
    upload_parser.add_argument(
        "--parallel",
        "-p",
        type=int,
        default=5,  # Changed from 3 to 5
        help="Number of concurrent upload workers (default: 5)",
    )
    upload_parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=20,  # Changed from 10 to 20
        help="Number of files to batch into a single request (default: 20)",
    )
    upload_parser.add_argument(
        "--progress",
        action="store_true",
        default=True,  # Added default=True
        help="Show progress bar during processing (requires tqdm)",
    )
    # Add no-progress option to disable progress bar if needed
    upload_parser.add_argument(
        "--no-progress",
        action="store_false",
        dest="progress",
        help="Disable progress bar",
    )

    # Delete command
    delete_parser = subparsers.add_parser(
        "delete", help="Delete files from Pinecone Assistant"
    )
    delete_parser.add_argument(
        "file_ids", nargs="+", help="IDs of files to delete from Pinecone Assistant"
    )
    delete_parser.add_argument(
        "--force", action="store_true", help="Skip confirmation prompt"
    )
    delete_parser.add_argument(
        "--by-name",
        action="store_true",
        help="Delete files by name instead of ID (will delete all matching names)",
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
        # Import directly from logging_setup instead of tools.debugger
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
            parallel=getattr(args, "parallel", 3),
            batch_size=getattr(args, "batch_size", 10),
            show_progress=getattr(args, "progress", False),
        )
    elif args.command == "upload":
        # Handle single or multiple file uploads
        file_paths = args.file_path

        # Check if all files exist
        missing_files = [p for p in file_paths if not os.path.exists(p)]
        if missing_files:
            for missing in missing_files:
                logger.error(f"File not found: {missing}")
            sys.exit(1)

        # Handle uploads
        if len(file_paths) == 1:
            # Use the existing single file upload function for just one file
            upload_single_file(file_paths[0], dry_run=args.dry_run)
        else:
            # Use the new batch upload function for multiple files
            logger.info(f"Batch uploading {len(file_paths)} files")
            upload_multiple_files(
                file_paths,
                dry_run=args.dry_run,
                parallel=args.parallel,
                batch_size=args.batch_size,
                show_progress=args.progress,
            )
    elif args.command == "validate":
        validate_database(
            reupload=args.reupload,
            check_disk=args.check_disk,
            clean=args.clean,
            check_untracked=args.check_untracked,
        )
    elif args.command == "delete":
        delete_files_from_assistant(
            args.file_ids, force=args.force, by_name=args.by_name
        )
    else:
        # If no command specified, show help
        parser.print_help()


if __name__ == "__main__":
    main()
