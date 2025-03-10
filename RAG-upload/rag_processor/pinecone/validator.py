"""
Pinecone database validation utilities
"""

import os
import time
from typing import List, Set, Tuple

from rag_processor.core.config import CONFIG
from rag_processor.core.file_utils import load_processed_files, save_processed_files
from rag_processor.core.logging_setup import logger
from rag_processor.pinecone.client import get_pinecone_index
from rag_processor.pinecone.uploader import sanitize_id, upload_file_to_pinecone


def get_pinecone_document_ids(namespace: str = "") -> Set[str]:
    """
    Retrieve all document IDs from Pinecone for the given namespace.
    Uses batching to handle large collections.

    Args:
        namespace: Pinecone namespace to check

    Returns:
        Set of document IDs in Pinecone
    """
    try:
        index = get_pinecone_index()
        if not index:
            logger.error("Failed to initialize Pinecone index")
            return set()

        # Get index statistics to determine vector dimensions and count
        stats = index.describe_index_stats()
        if not stats:
            logger.error("Failed to fetch index statistics")
            return set()

        # Check if namespace exists
        namespaces = stats.get("namespaces", {})
        if namespace and namespace not in namespaces:
            logger.warning(f"Namespace '{namespace}' does not exist in the index")
            return set()

        # Get vector dimensions from index (needed for properly formed queries)
        dimensions = stats.get("dimension")
        if not dimensions:
            logger.error("Failed to determine vector dimensions")
            return set()

        # Count of vectors in this namespace (or total if no namespace specified)
        if namespace:
            total_vectors = namespaces.get(namespace, {}).get("vector_count", 0)
        else:
            total_vectors = stats.get("total_vector_count", 0)

        logger.debug(
            f"Found {total_vectors} total vectors in namespace '{namespace or 'default'}'"
        )

        if total_vectors == 0:
            return set()

        # Collect all document IDs
        all_ids = set()

        # Pinecone has limits on how many items we can fetch at once
        # Use batching to retrieve all IDs
        BATCH_SIZE = 1000  # Pinecone's maximum limit for fetch operations
        MAX_RETRIES = 3

        # For small collections (under BATCH_SIZE), we can use a single fetch
        # Simple query to get all IDs - Pinecone will return matches with their IDs
        # We use a zero vector with proper dimensionality
        zero_vector = [0.0] * dimensions

        # Get IDs with retries for resilience
        for attempt in range(MAX_RETRIES):
            try:
                response = index.query(
                    namespace=namespace,
                    vector=zero_vector,
                    top_k=total_vectors,  # Request all vectors
                    include_metadata=False,  # We only need the IDs
                )
                all_ids.update(match.id for match in response.matches)
                break
            except Exception as e:
                logger.warning(
                    f"Error fetching IDs (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1)  # Wait before retrying
                else:
                    logger.error(f"Failed to fetch IDs after {MAX_RETRIES} attempts")
                    raise
        else:
            # For larger collections, we need to use pagination
            # Since Pinecone doesn't have direct pagination, we'll use multiple queries
            # to fetch batches of IDs

            # Total number of batches needed
            num_batches = (total_vectors + BATCH_SIZE - 1) // BATCH_SIZE
            logger.debug(f"Fetching {total_vectors} vectors in {num_batches} batches")

            # Generate a zero vector with correct dimensionality
            zero_vector = [0.0] * dimensions

            # Track already seen IDs to avoid duplicates
            seen_ids = set()
            fetched_count = 0

            for batch in range(num_batches):
                # Each attempt has multiple retries for resilience
                for attempt in range(MAX_RETRIES):
                    try:
                        # Calculate remaining vectors to fetch
                        remaining = min(BATCH_SIZE, total_vectors - fetched_count)
                        if remaining <= 0:
                            break

                        # Fetch the next batch
                        logger.debug(
                            f"Fetching batch {batch + 1}/{num_batches} ({remaining} vectors)"
                        )

                        # If we have IDs, we can use an ID filter to exclude already seen IDs
                        # This is a workaround for pagination since Pinecone doesn't support direct offset/limit
                        if seen_ids:
                            # For efficiency we'll limit to a reasonable number of IDs in the filter
                            # Too many IDs in the filter can cause performance issues
                            filter_ids = (
                                list(seen_ids)[-10000:]
                                if len(seen_ids) > 10000
                                else list(seen_ids)
                            )
                            response = index.query(
                                namespace=namespace,
                                vector=zero_vector,
                                top_k=remaining,
                                include_metadata=False,
                                filter={"id": {"$nin": filter_ids}},
                            )
                        else:
                            # First batch doesn't need a filter
                            response = index.query(
                                namespace=namespace,
                                vector=zero_vector,
                                top_k=remaining,
                                include_metadata=False,
                            )

                        # Extract the IDs from this batch
                        batch_ids = {match.id for match in response.matches}

                        # Check for progress
                        if not batch_ids:
                            # No new IDs - we might be done or have an issue
                            logger.debug(
                                f"No new IDs found in batch {batch + 1}/{num_batches}"
                            )
                            if fetched_count < total_vectors:
                                logger.warning(
                                    f"Query returned no results but only fetched {fetched_count}/{total_vectors} IDs"
                                )
                            break

                        # Update our tracking variables
                        new_ids = batch_ids - seen_ids
                        seen_ids.update(new_ids)
                        all_ids.update(new_ids)
                        fetched_count += len(new_ids)

                        logger.debug(
                            f"Fetched {len(new_ids)} new IDs (total: {fetched_count}/{total_vectors})"
                        )

                        # If we got fewer results than requested, we might be done
                        if len(response.matches) < remaining:
                            logger.debug(
                                f"Received fewer results than requested ({len(response.matches)}/{remaining})"
                            )
                            break

                        # Add a small delay between batches to avoid rate limiting
                        if batch < num_batches - 1:
                            time.sleep(0.1)

                        break  # Success - exit the retry loop
                    except Exception as e:
                        logger.warning(
                            f"Error fetching batch {batch + 1} (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                        )
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(1)  # Wait before retrying
                        else:
                            logger.error(
                                f"Failed to fetch batch {batch + 1} after {MAX_RETRIES} attempts"
                            )

            # Log completion
            if fetched_count < total_vectors:
                logger.warning(
                    f"Could only fetch {fetched_count}/{total_vectors} document IDs"
                )
            else:
                logger.debug(f"Successfully fetched all {fetched_count} document IDs")

        return all_ids

    except Exception as e:
        logger.error(f"Error retrieving document IDs from Pinecone: {e}")
        return set()


def validate_database_integrity(
    namespace: str = "", auto_reupload: bool = False
) -> Tuple[List[str], int]:
    """
    Validate that all files in the tracking JSON are still in the Pinecone database.

    Args:
        namespace: Pinecone namespace to check
        auto_reupload: If True, automatically re-upload missing files

    Returns:
        Tuple[List[str], int]: List of missing file paths and count of files re-uploaded (if auto_reupload)
    """
    # Load processed files log
    processed_files = load_processed_files()
    if not processed_files:
        logger.info("No processed files found in tracking JSON")
        return [], 0

    # Get IDs from Pinecone
    pinecone_ids = get_pinecone_document_ids(namespace)
    if not pinecone_ids:
        logger.warning("No documents found in Pinecone database")
        return list(processed_files.keys()), 0

    # Find files that are in the tracking JSON but not in Pinecone
    missing_files = []
    reuploaded_count = 0

    for file_name, file_data in processed_files.items():
        if file_name not in pinecone_ids:
            # Check if the file still exists on disk
            file_path = file_data.get("file_path")
            if not file_path:
                # Try to reconstruct path from TARGET_FOLDER
                target_folder = CONFIG["TARGET_FOLDER"]
                file_path = os.path.join(target_folder, file_name)

            if os.path.exists(file_path):
                missing_files.append(file_path)

                # Re-upload if requested
                if auto_reupload:
                    logger.info(f"Re-uploading missing file: {file_name}")
                    index = get_pinecone_index()
                    if index and upload_file_to_pinecone(file_path, index, namespace):
                        reuploaded_count += 1
                    else:
                        logger.error(f"Failed to re-upload file: {file_name}")
            else:
                logger.warning(f"File missing from both Pinecone and disk: {file_name}")
                # Consider removing from tracking JSON if file doesn't exist

    return missing_files, reuploaded_count


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
        file_path = file_data.get("file_path")
        if not file_path:
            # Try to reconstruct path from original location or TARGET_FOLDER
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


def find_untracked_pinecone_documents(namespace: str = "") -> Set[str]:
    """Find documents in Pinecone that aren't in the tracking JSON."""
    try:
        # Get all document IDs from Pinecone
        pinecone_ids = get_pinecone_document_ids(namespace)

        # Load processed files tracking data
        processed_files = load_processed_files()

        # Create mapping of sanitized IDs to original filenames
        tracked_sanitized_ids = set()

        for filename, metadata in processed_files.items():
            # If we have the sanitized_id stored, use it
            if "sanitized_id" in metadata:
                tracked_sanitized_ids.add(metadata["sanitized_id"])
            else:
                # For backward compatibility with old tracking data
                tracked_sanitized_ids.add(sanitize_id(filename))

        # Find untracked documents
        untracked = pinecone_ids - tracked_sanitized_ids

        return untracked
    except Exception as e:
        logger.error(f"Error finding untracked documents: {e}")
        return set()
