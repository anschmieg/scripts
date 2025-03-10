"""
Pinecone upload functionality
"""

import os
from datetime import datetime

from rag_processor.core.logging_setup import logger
from rag_processor.processor.file_converter import convert_document_to_text


def sanitize_id(filename):
    """Convert filename to ASCII-compatible ID."""
    import re
    import unicodedata

    # Normalize unicode characters and convert to ASCII
    normalized = unicodedata.normalize("NFKD", filename)
    ascii_id = normalized.encode("ascii", "ignore").decode("ascii")

    # Replace any remaining invalid characters with underscore
    clean_id = re.sub(r"[^\w.-]", "_", ascii_id)

    return clean_id


def upload_file_to_pinecone(file_path: str, index, namespace: str = "") -> bool:
    """
    Upload a file to Pinecone with proper error handling.

    Args:
        file_path: Path to the file to upload
        index: The Pinecone index to upload to
        namespace: Pinecone namespace for the upload

    Returns:
        bool: True if upload succeeded, False otherwise
    """
    try:
        # Get text content from the file
        file_text = convert_document_to_text(file_path)

        # Check if this is a preprocessed file
        if os.path.basename(os.path.dirname(file_path)) == "preprocessed":
            # Extract the cache filename
            original_path = file_path
            cache_filename = os.path.basename(file_path)
            base_name = os.path.splitext(cache_filename)[0]

            # For display purposes in logs
            logger.debug(f"Using preprocessed version of file: {base_name}")

            # Still use the preprocessed file's content but with original filename
            file_name = f"{base_name}.original"
        else:
            file_name = os.path.basename(file_path)

        # Get file metadata
        file_stats = os.stat(file_path)

        # Create record for Pinecone
        record = {
            "_id": file_name,
            "data": file_text,  # The field that will be embedded
            "file_path": original_path if "original_path" in locals() else file_path,
            "file_name": file_name,
            "file_extension": os.path.splitext(file_name)[1],
            "file_size": file_stats.st_size,
            "creation_date": datetime.fromtimestamp(file_stats.st_ctime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "modified_date": datetime.fromtimestamp(file_stats.st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "processed_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Upsert to Pinecone
        index.upsert(
            vectors=[record],
            namespace=namespace,
        )

        logger.info(f"Successfully uploaded {file_name} to Pinecone")
        return True

    except Exception as e:
        logger.error(f"Error uploading {os.path.basename(file_path)}: {str(e)}")
        return False
