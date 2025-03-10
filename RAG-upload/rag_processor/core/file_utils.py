"""
File utility functions for RAG Processor
"""

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict

from rag_processor.core.config import CONFIG
from rag_processor.pinecone.uploader import sanitize_id


def generate_file_hash(file_path: str) -> str:
    """Generate a SHA-256 hash for a given file."""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def load_processed_files() -> Dict[str, Dict[str, Any]]:
    """Load log of processed files, creating if not exists."""
    os.makedirs(os.path.dirname(CONFIG["processed_log_path"]), exist_ok=True)

    try:
        with open(CONFIG["processed_log_path"], "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_processed_files(processed_files: Dict[str, Dict[str, Any]]):
    """Save log of processed files."""
    with open(CONFIG["processed_log_path"], "w") as f:
        json.dump(processed_files, f, indent=2)


def check_file_changed(
    file_path: str, filename: str, processed_files: Dict[str, Dict[str, Any]]
) -> bool:
    """Check if a file has changed since last processing."""
    if filename not in processed_files:
        return True

    current_hash = generate_file_hash(file_path)
    return processed_files[filename].get("hash") != current_hash


def update_processed_files_tracking(file_path, file_name, processed_files):
    """
    Update tracking information for a processed file.

    Args:
        file_path: Path to the processed file
        file_name: Original filename (may contain non-ASCII characters)
        processed_files: The tracking dictionary to update
    """
    # Generate sanitized ID same as used for Pinecone
    sanitized_id = sanitize_id(file_name)

    # Store entry with both original and sanitized names
    processed_files[file_name] = {
        "hash": generate_file_hash(file_path),
        "mtime": os.path.getmtime(file_path),
        "last_processed": datetime.now().isoformat(),
        "sanitized_id": sanitized_id,  # Store the sanitized ID used in Pinecone
    }
