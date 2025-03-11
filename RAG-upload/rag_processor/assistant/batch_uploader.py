"""
Batch upload functionality for Pinecone Assistant
"""

import concurrent.futures
import os
import time
from typing import Dict, List

from rag_processor.assistant.client import PineconeAssistantClient
from rag_processor.core.logging_setup import logger

try:
    # Optional tqdm dependency for progress reporting
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


def batch_upload_files_to_assistant(
    files: List[str], batch_size: int = 10, show_progress: bool = False
) -> Dict[str, dict]:
    """
    Upload multiple files to Pinecone Assistant efficiently.

    Args:
        files: List of file paths to upload
        batch_size: Number of files to process in each batch
        show_progress: Whether to show a progress bar (requires tqdm)

    Returns:
        Dict mapping filenames to their upload results
    """
    logger.info(f"Batch uploading {len(files)} files to Pinecone Assistant")

    # Initialize the client once for all files
    try:
        client = PineconeAssistantClient()
    except Exception as e:
        logger.error(f"Failed to initialize Pinecone Assistant client: {e}")
        return {os.path.basename(f): {"error": str(e)} for f in files}

    # Process files in batches to avoid overwhelming the API
    batched_files = [
        files[i : i + batch_size] for i in range(0, len(files), batch_size)
    ]
    results = {}

    # Setup progress bar if requested and available
    if show_progress and TQDM_AVAILABLE:
        pbar = tqdm(total=len(files), desc="Uploading files")
    else:
        pbar = None

    # Process each batch
    for batch in batched_files:
        batch_results = _process_file_batch(client, batch)
        results.update(batch_results)

        # Update progress bar if available
        if pbar:
            pbar.update(len(batch))

    # Close progress bar
    if pbar:
        pbar.close()

    # Log summary
    successful = sum(1 for r in results.values() if "id" in r and "error" not in r)
    logger.info(
        f"Batch upload completed: {successful}/{len(files)} files successfully uploaded"
    )

    return results


def process_files_concurrently(
    file_list: List[str],
    max_workers: int = 3,
    batch_size: int = 10,
    show_progress: bool = False,
) -> Dict[str, dict]:
    """
    Process multiple files concurrently to improve throughput.

    Args:
        file_list: List of files to upload
        max_workers: Maximum number of concurrent workers
        batch_size: Number of files to process in each batch
        show_progress: Whether to show a progress bar (requires tqdm)

    Returns:
        Dict mapping filenames to their upload results
    """
    results = {}

    # Limit max_workers based on file count
    effective_workers = min(max_workers, len(file_list))
    if effective_workers < max_workers:
        logger.debug(
            f"Reducing workers from {max_workers} to {effective_workers} based on file count"
        )

    # Break the file list into chunks for each worker
    worker_chunks = _split_list(file_list, effective_workers)

    # Setup progress bar if requested and available
    if show_progress and TQDM_AVAILABLE:
        pbar = tqdm(total=len(file_list), desc="Processing files")
    else:
        pbar = None

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=effective_workers
    ) as executor:
        # Submit each chunk to a worker
        future_to_chunk = {
            executor.submit(
                batch_upload_files_to_assistant, chunk, batch_size, False
            ): i
            for i, chunk in enumerate(worker_chunks)
        }

        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_chunk):
            chunk_idx = future_to_chunk[future]
            try:
                chunk_results = future.result()
                results.update(chunk_results)

                # Update progress bar
                if pbar:
                    pbar.update(len(worker_chunks[chunk_idx]))

            except Exception as e:
                logger.error(f"Error in worker {chunk_idx}: {e}")
                # Mark all files in this chunk as failed
                for file_path in worker_chunks[chunk_idx]:
                    file_name = os.path.basename(file_path)
                    results[file_name] = {"error": str(e)}

    # Close progress bar
    if pbar:
        pbar.close()

    return results


def _process_file_batch(
    client: PineconeAssistantClient, files: List[str]
) -> Dict[str, dict]:
    """
    Process a batch of files using a single client instance.

    Args:
        client: Initialized PineconeAssistantClient
        files: List of file paths to upload

    Returns:
        Dict mapping filenames to their upload results
    """
    results = {}

    for file_path in files:
        file_name = os.path.basename(file_path)
        try:
            # Get file metadata
            file_stats = os.stat(file_path)
            metadata = {
                "file_name": file_name,
                "file_extension": os.path.splitext(file_name)[1],
                "file_size": file_stats.st_size,
                "upload_time": time.time(),
                "processed_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Upload the file
            response = client.upload_file(file_path, metadata)
            results[file_name] = response

            if "error" in response:
                logger.error(f"Failed to upload {file_name}: {response['error']}")
            else:
                logger.info(
                    f"Successfully uploaded {file_name} (ID: {response.get('id', 'unknown')})"
                )

        except Exception as e:
            logger.error(f"Error uploading {file_name}: {e}")
            results[file_name] = {"error": str(e)}

    return results


def _split_list(input_list: List, num_chunks: int) -> List[List]:
    """
    Split a list into approximately equal-sized chunks.

    Args:
        input_list: List to split
        num_chunks: Number of chunks to create

    Returns:
        List of list chunks
    """
    avg_size = len(input_list) / num_chunks
    result = []

    start = 0
    for i in range(num_chunks):
        end = round(start + avg_size)
        result.append(input_list[start:end])
        start = end

    return result
