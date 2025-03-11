"""
Pinecone upload functionality - supports both Assistant API and Vector DB
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Union

from rag_processor.core.config import CONFIG
from rag_processor.core.logging_setup import logger

# Remove circular import and import inside function instead


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


def upload_file_to_assistant(file_path: str) -> Optional[Dict]:
    """
    Upload a file to Pinecone Assistant.

    Args:
        file_path: Path to the file to upload

    Returns:
        Dict: Response from the API or None if failed
    """
    try:
        # Import here to avoid circular imports
        from rag_processor.assistant.client import PineconeAssistantClient

        # Get file metadata
        file_name = os.path.basename(file_path)
        file_stats = os.stat(file_path)

        # Create metadata for the file
        metadata = {
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

        # Initialize the client and upload the file
        client = PineconeAssistantClient()
        response = client.upload_file(file_path, metadata)

        if "error" in response:
            logger.error(f"Failed to upload {file_name}: {response['error']}")
            return None

        logger.info(
            f"Successfully uploaded {file_name} to Pinecone Assistant (ID: {response.get('id', 'unknown')})"
        )
        return response

    except Exception as e:
        logger.error(f"Error uploading {os.path.basename(file_path)}: {str(e)}")
        return None


def upload_multiple_files_to_assistant(
    file_paths: List[str],
    parallel: int = 3,
    batch_size: int = 10,
    show_progress: bool = False,
) -> Dict[str, dict]:
    """
    Upload multiple files to Pinecone Assistant with optimized performance.

    Args:
        file_paths: List of file paths to upload
        parallel: Number of parallel workers (default: 3)
        batch_size: Number of files in each batch (default: 10)
        show_progress: Whether to show progress bar (requires tqdm)

    Returns:
        Dict mapping filenames to their upload results
    """
    # Import here to avoid circular imports
    from rag_processor.assistant.batch_uploader import process_files_concurrently

    if len(file_paths) == 1:
        # For a single file, use the regular upload function
        result = upload_file_to_assistant(file_paths[0])
        file_name = os.path.basename(file_paths[0])
        return {file_name: result or {"error": "Upload failed"}}

    # For multiple files, use concurrent processing
    return process_files_concurrently(
        file_paths,
        max_workers=parallel,
        batch_size=batch_size,
        show_progress=show_progress,
    )


def upload_file_to_vector_db(file_path: str, index, namespace: str = "") -> bool:
    """
    Upload a file to Pinecone Vector DB.

    Args:
        file_path: Path to the file to upload
        index: Pinecone index to use
        namespace: Namespace for the upload

    Returns:
        bool: True if upload succeeded, False otherwise
    """
    try:
        # The original vector DB upload implementation
        from rag_processor.processor.file_converter import convert_document_to_text

        # Get text content from the file
        file_text = convert_document_to_text(file_path)

        file_name = os.path.basename(file_path)
        file_stats = os.stat(file_path)

        # Create record for Pinecone
        record = {
            "_id": file_name,
            "data": file_text,  # The field that will be embedded
            "file_path": file_path,
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

        # Upsert to Pinecone Vector DB
        index.upsert(
            vectors=[record],
            namespace=namespace,
        )

        logger.info(f"Successfully uploaded {file_name} to Pinecone Vector DB")
        return True

    except Exception as e:
        logger.error(
            f"Error uploading {os.path.basename(file_path)} to Vector DB: {str(e)}"
        )
        return False


# Function to handle uploads to either system
def upload_file(
    file_path: str,
    index=None,
    namespace: str = "",
    use_assistant: Optional[bool] = None,
) -> Union[Dict, bool]:
    """
    Upload a file to either Pinecone Assistant or Vector DB based on configuration.

    Args:
        file_path: Path to the file to upload
        index: Pinecone index (for Vector DB only)
        namespace: Namespace (for Vector DB only)
        use_assistant: Override config setting for which API to use

    Returns:
        Union[Dict, bool]: Response from the appropriate API
    """
    # Determine which API to use
    should_use_assistant = (
        use_assistant
        if use_assistant is not None
        else CONFIG.get("use_assistant_api", True)
    )

    if should_use_assistant:
        logger.debug(f"Using Pinecone Assistant API for {os.path.basename(file_path)}")
        return upload_file_to_assistant(file_path)
    else:
        logger.debug(f"Using Pinecone Vector DB for {os.path.basename(file_path)}")
        if index is None:
            from rag_processor.pinecone.client import get_pinecone_index

            index = get_pinecone_index()
        return upload_file_to_vector_db(file_path, index, namespace)


def upload_files(
    file_paths: List[str],
    index=None,
    namespace: str = "",
    use_assistant: Optional[bool] = None,
    parallel: int = 3,
    batch_size: int = 10,
    show_progress: bool = False,
) -> Dict[str, Union[Dict, bool]]:
    """
    Upload multiple files with optimized performance.

    Args:
        file_paths: List of paths to upload
        index: Pinecone index (for Vector DB only)
        namespace: Namespace (for Vector DB only)
        use_assistant: Override config setting for which API to use
        parallel: Number of parallel workers
        batch_size: Number of files in each batch
        show_progress: Whether to show progress bar

    Returns:
        Dict mapping filenames to upload results
    """
    # Determine which API to use
    should_use_assistant = (
        use_assistant
        if use_assistant is not None
        else CONFIG.get("use_assistant_api", True)
    )

    if should_use_assistant:
        logger.debug(
            f"Using Pinecone Assistant API for batch upload of {len(file_paths)} files"
        )
        return upload_multiple_files_to_assistant(
            file_paths,
            parallel=parallel,
            batch_size=batch_size,
            show_progress=show_progress,
        )
    else:
        logger.debug(
            f"Using Pinecone Vector DB for batch upload of {len(file_paths)} files"
        )
        # For Vector DB, we don't have a batch uploader yet, so process files individually
        results = {}
        for file_path in file_paths:
            file_name = os.path.basename(file_path)
            if index is None:
                from rag_processor.pinecone.client import get_pinecone_index

                index = get_pinecone_index()
            result = upload_file_to_vector_db(file_path, index, namespace)
            results[file_name] = result
        return results


# Keep the old function signature for backward compatibility
def upload_file_to_pinecone(file_path: str, index=None, namespace: str = "") -> bool:
    """
    Legacy function that redirects to the appropriate uploader.

    Args:
        file_path: Path to the file to upload
        index: Pinecone index (for Vector DB only)
        namespace: Namespace (for Vector DB only)

    Returns:
        bool: True if upload succeeded, False otherwise
    """
    try:
        result = upload_file(file_path, index, namespace)

        # Handle different return types
        if isinstance(result, dict):
            return "id" in result and "error" not in result
        return bool(result)
    except Exception as e:
        logger.error(f"Error uploading {os.path.basename(file_path)}: {str(e)}")
        return False
