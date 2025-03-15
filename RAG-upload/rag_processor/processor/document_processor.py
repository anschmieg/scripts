"""
Document processing functionality for RAG Processor
"""

import os
import sys
import time
from typing import List, Tuple

from rag_processor.core.config import CONFIG, SUPPORTED_EXTENSIONS
from rag_processor.core.file_utils import (
    check_file_changed,
    load_processed_files,
    save_processed_files,
    update_processed_files_tracking,
)
from rag_processor.core.logging_setup import logger
from rag_processor.pinecone.uploader import upload_files


def get_pinecone_index():
    """Initialize and return the Pinecone index."""
    # Only needed when using Vector DB mode
    if CONFIG.get("use_assistant_api", False):
        return None

    try:
        import pinecone

        # Initialize Pinecone client
        pinecone.init(api_key=os.environ["PINECONE_API_KEY"])

        index_name = CONFIG["index_name"]
        logger.debug(f"Connecting to Pinecone index: {index_name}")

        # Get the index
        return pinecone.Index(index_name)

    except ImportError:
        logger.error(
            "Pinecone package not installed. Please run 'pip install pinecone-client'"
        )
        sys.exit(1)
    except KeyError:
        logger.error("PINECONE_API_KEY environment variable not set")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error initializing Pinecone: {e}")
        sys.exit(1)


def find_processable_files(folder_path: str, recursive: bool = True) -> List[str]:
    """Find all processable files in the given folder."""
    all_files = []

    try:
        # Check if the path is a file (not a directory)
        if os.path.isfile(folder_path):
            # If it's a single file with supported extension
            if any(folder_path.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                return [folder_path]
            else:
                logger.warning(f"Unsupported file format: {folder_path}")
                return []

        # Original directory scanning logic
        if recursive:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if any(file.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                        all_files.append(file_path)
        else:
            # Non-recursive mode, only check files in the top directory
            for item in os.listdir(folder_path):
                file_path = os.path.join(folder_path, item)
                if os.path.isfile(file_path) and any(
                    file_path.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS
                ):
                    all_files.append(file_path)

    except Exception as e:
        logger.error(f"Error scanning directory {folder_path}: {e}")

    return all_files


def process_documents(
    target_folder: str,
    dry_run: bool = False,
    recursive: bool = True,
    parallel: int = 5,  # Increased from 3 to 5 by default
    batch_size: int = 20,  # Increased from 10 to 20 by default
    show_progress: bool = True,  # Changed default to True
) -> Tuple[int, int]:
    """Process and upload documents to Pinecone."""
    start_time = time.time()

    logger.info(f"Starting document processing in {target_folder}")
    logger.info(f"Dry run mode: {dry_run}")

    # Log which API we're using
    use_assistant = CONFIG.get("use_assistant_api", True)
    logger.info(
        f"Using {'Pinecone Assistant API' if use_assistant else 'Pinecone Vector DB'}"
    )
    if use_assistant:
        assistant_name = CONFIG.get("assistant_name")
        if assistant_name:
            logger.info(f"Assistant name: {assistant_name}")
        else:
            logger.info("Using default assistant (no name specified)")

    # Get all processable files
    files = find_processable_files(target_folder, recursive)
    logger.info(f"Found {len(files)} files to process")

    # Load processed files log
    processed_files = load_processed_files()

    # Filter only files that have changed
    files_to_process = []
    unchanged_count = 0

    for file_path in files:
        filename = os.path.basename(file_path)
        if not check_file_changed(file_path, filename, processed_files):
            logger.debug(f"Skipping unchanged file: {filename}")
            unchanged_count += 1
        else:
            files_to_process.append(file_path)

    logger.info(
        f"Files to process: {len(files_to_process)} (unchanged: {unchanged_count})"
    )

    # Initialize counters
    processed_count = 0
    error_count = 0

    # Get Pinecone index if using Vector DB and not in dry run mode
    index = None
    if not dry_run and not CONFIG.get("use_assistant_api", True):
        index = get_pinecone_index()

    # Process files in optimized batch mode
    if files_to_process:
        if not dry_run:
            # Use batch upload
            batch_results = upload_files(
                files_to_process,
                index=index,
                namespace=CONFIG["namespace"],
                parallel=parallel,
                batch_size=batch_size,
                show_progress=show_progress,
            )

            # Process results and update tracking
            for file_path in files_to_process:
                filename = os.path.basename(file_path)
                result = batch_results.get(filename)

                # Check for success - different result formats depending on API used
                success = False
                if isinstance(result, dict):  # Assistant API result
                    if "id" in result and "error" not in result:
                        success = True
                        # Update file tracking
                        update_processed_files_tracking(
                            file_path, filename, processed_files
                        )
                        processed_files[filename]["assistant_file_id"] = result["id"]
                else:  # Vector DB boolean result
                    success = bool(result)
                    if success:
                        # Update file tracking
                        update_processed_files_tracking(
                            file_path, filename, processed_files
                        )

                if success:
                    processed_count += 1
                else:
                    error_count += 1

        elif "--dry-run-update-cache" in sys.argv:
            # Only update tracking in dry-run if explicitly requested
            for file_path in files_to_process:
                filename = os.path.basename(file_path)
                update_processed_files_tracking(file_path, filename, processed_files)
                processed_count += 1
        else:
            # Dry run without tracking updates
            processed_count = len(files_to_process)

    # Save updated processed files log
    if processed_count > 0 and (not dry_run or "--dry-run-update-cache" in sys.argv):
        save_processed_files(processed_files)

    # Log processing summary
    elapsed_time = time.time() - start_time
    logger.info(f"Document processing completed in {elapsed_time:.2f} seconds")
    logger.info(f"Files processed: {processed_count}")
    logger.info(f"Files unchanged: {unchanged_count}")
    logger.info(f"Files with errors: {error_count}")

    return processed_count, error_count
