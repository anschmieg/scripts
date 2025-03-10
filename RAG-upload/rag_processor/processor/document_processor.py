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
)
from rag_processor.core.logging_setup import logger
from rag_processor.pinecone.uploader import upload_file_to_pinecone


def get_pinecone_index():
    """Initialize and return the Pinecone index."""
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
    target_folder: str, dry_run: bool = False, recursive: bool = True
) -> Tuple[int, int]:
    """Process and upload documents to Pinecone."""
    start_time = time.time()

    logger.info(f"Starting document processing in {target_folder}")
    logger.info(f"Dry run mode: {dry_run}")

    # Get all processable files
    files = find_processable_files(target_folder, recursive)
    logger.info(f"Found {len(files)} files to process")

    # Load processed files log
    processed_files = load_processed_files()

    # Initialize counters
    processed_count = 0
    unchanged_count = 0
    error_count = 0

    # Get Pinecone index if not in dry run mode
    if not dry_run:
        index = get_pinecone_index()

    # Process each file
    for file_path in files:
        filename = os.path.basename(file_path)

        try:
            # Check if file has changed
            if not check_file_changed(file_path, filename, processed_files):
                logger.debug(f"Skipping unchanged file: {filename}")
                unchanged_count += 1
                continue

            logger.info(f"Processing file: {filename}")

            if not dry_run:
                # Upload to Pinecone
                success = upload_file_to_pinecone(
                    file_path=file_path, index=index, namespace=CONFIG["namespace"]
                )

                if not success:
                    error_count += 1
                    continue

            # Update processed files log with new hash
            if not dry_run or "--dry-run-update-cache" in sys.argv:
                from rag_processor.core.file_utils import generate_file_hash

                file_hash = generate_file_hash(file_path)
                processed_files[filename] = {
                    "path": file_path,
                    "hash": file_hash,
                    "last_processed": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

            processed_count += 1

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
            error_count += 1

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
