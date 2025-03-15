"""
Validator for Pinecone Assistant files
"""

import os
from datetime import datetime
from typing import Dict, List, Set, Tuple

from rag_processor.assistant.client import PineconeAssistantClient
from rag_processor.core.config import CONFIG
from rag_processor.core.file_utils import load_processed_files, save_processed_files
from rag_processor.core.logging_setup import logger
from rag_processor.pinecone.uploader import upload_file_to_assistant


def get_assistant_file_ids() -> Set[str]:
    """
    Retrieve all file IDs from Pinecone Assistant.

    Returns:
        Set of file IDs in Pinecone Assistant
    """
    try:
        client = PineconeAssistantClient()
        all_files = set()

        # Use the compatibility wrapper without parameters
        response = client.list_files()

        if isinstance(response, dict) and "error" in response:
            logger.error(
                f"Failed to fetch files from Pinecone Assistant: {response['error']}"
            )
            return set()

        # Handle different response formats
        files = []
        if isinstance(response, dict) and "files" in response:
            files = response["files"]
        elif isinstance(response, list):
            files = response
        elif hasattr(response, "files"):
            files = response.files

        # Add IDs from the files list
        for file in files:
            if isinstance(file, dict) and "id" in file:
                all_files.add(file["id"])
            elif hasattr(file, "id"):
                all_files.add(file.id)

        logger.debug(f"Found {len(all_files)} files in Pinecone Assistant")
        return all_files

    except Exception as e:
        logger.error(f"Error retrieving file IDs from Pinecone Assistant: {e}")
        return set()


def validate_assistant_integrity(
    auto_reupload: bool = False,
) -> Tuple[List[str], int, int]:
    """
    Validate that all files in the tracking JSON are still in Pinecone Assistant.

    Args:
        auto_reupload: If True, automatically re-upload missing files

    Returns:
        Tuple[List[str], int, int]: List of missing file paths, count of files re-uploaded, count of errors
    """
    # Load processed files log
    processed_files = load_processed_files()
    if not processed_files:
        logger.info("No processed files found in tracking JSON")
        return [], 0, 0

    # Get file IDs from Pinecone Assistant
    assistant_file_ids = get_assistant_file_ids()
    if not assistant_file_ids:
        logger.warning("No files found in Pinecone Assistant")
        return list(processed_files.keys()), 0, 0

    # Find files that are in tracking JSON but not in Assistant
    missing_files = []
    reuploaded_count = 0
    error_count = 0  # Initialize error count

    for file_name, file_data in processed_files.items():
        # Get the file ID used in Assistant
        file_id = file_data.get("assistant_file_id")

        if not file_id or file_id not in assistant_file_ids:
            # Check if the file still exists on disk
            file_path = file_data.get("path", "")
            if not file_path or not os.path.exists(file_path):
                # Try to reconstruct path from TARGET_FOLDER
                target_folder = CONFIG["TARGET_FOLDER"]
                file_path = os.path.join(target_folder, file_name)

            if os.path.exists(file_path):
                missing_files.append(file_path)

                # Re-upload if requested
                if auto_reupload:
                    logger.info(f"Re-uploading missing file: {file_name}")
                    result = upload_file_to_assistant(file_path)

                    if result and "id" in result and "error" not in result:
                        # Update the tracking with new file ID
                        processed_files[file_name]["assistant_file_id"] = result["id"]
                        processed_files[file_name]["last_processed"] = (
                            datetime.now().isoformat()
                        )
                        reuploaded_count += 1
                    else:
                        logger.error(f"Failed to re-upload file: {file_name}")
                        error_count += 1  # Increment error count
            else:
                logger.warning(
                    f"File missing from both Assistant and disk: {file_name}"
                )

    # Save updated tracking if files were re-uploaded
    if reuploaded_count > 0:
        save_processed_files(processed_files)

    return missing_files, reuploaded_count, error_count


def cleanup_tracking_json(remove_missing: bool = False) -> int:
    """
    Clean up the tracking JSON by removing entries for files that don't exist.

    Args:
        remove_missing: If True, remove entries for files that don't exist on disk

    Returns:
        int: Number of entries removed
    """
    processed_files = load_processed_files()
    if not processed_files:
        return 0

    entries_to_remove = []

    for file_name, file_data in processed_files.items():
        # Check if file exists
        file_path = file_data.get("path", "")
        if not file_path:
            # Try to reconstruct path from TARGET_FOLDER
            target_folder = CONFIG["TARGET_FOLDER"]
            file_path = os.path.join(target_folder, file_name)

        if not os.path.exists(file_path):
            entries_to_remove.append(file_name)

    # Remove entries if requested
    if remove_missing and entries_to_remove:
        for file_name in entries_to_remove:
            del processed_files[file_name]

        # Save the updated processed files log
        save_processed_files(processed_files)
        logger.info(f"Removed {len(entries_to_remove)} entries from tracking JSON")

    return len(entries_to_remove)


def find_untracked_assistant_files() -> Dict[str, Dict]:
    """
    Find files in Pinecone Assistant that aren't in the tracking JSON.

    Returns:
        Dict: Dictionary of untracked file IDs and their metadata
    """
    try:
        # Get all files from Assistant
        client = PineconeAssistantClient()
        response = client.list_files()  # Use the parameterless version

        # Handle different response formats
        files_list = []
        if isinstance(response, dict) and "files" in response:
            files_list = response["files"]
        elif isinstance(response, list):
            files_list = response
        elif hasattr(response, "files"):
            files_list = response.files

        if not files_list:
            if isinstance(response, dict) and "error" in response:
                logger.error(f"Failed to list files: {response['error']}")
            return {}

        # Convert to dictionary by ID
        assistant_files = {}
        for file in files_list:
            # Handle both dict and object formats
            if isinstance(file, dict):
                file_id = file.get("id")
                assistant_files[file_id] = file
            else:
                file_id = getattr(file, "id", None)
                if file_id:
                    # Convert object to dict
                    assistant_files[file_id] = {
                        "id": file_id,
                        "name": getattr(
                            file, "filename", getattr(file, "name", file_id)
                        ),
                        "size": getattr(file, "size", None),
                        "created_at": getattr(file, "created_at", None),
                    }

        # Load processed files tracking data
        processed_files = load_processed_files()

        # Create set of tracked Assistant file IDs
        tracked_ids = set()
        for _, metadata in processed_files.items():
            if "assistant_file_id" in metadata:
                tracked_ids.add(metadata["assistant_file_id"])

        # Find untracked files
        untracked = {
            file_id: file_data
            for file_id, file_data in assistant_files.items()
            if file_id not in tracked_ids
        }

        return untracked

    except Exception as e:
        logger.error(f"Error finding untracked Assistant files: {e}")
        return {}
