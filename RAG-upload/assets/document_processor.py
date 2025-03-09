import hashlib
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict

import dotenv
from pinecone import Pinecone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
dotenv.load_dotenv()

# Configuration from .env file
CONFIG = {
    "TARGET_FOLDER": os.getenv(
        "TARGET_FOLDER", os.path.expanduser("~/Nextcloud/Documents")
    ),
    "processed_log_path": os.path.expanduser(
        "~/Library/Application Support/PineconeDocProcessor/processed_files.json"
    ),
    "log_path": os.path.expanduser("~/Library/Logs/PineconeDocProcessor.log"),
    "namespace": os.getenv("NAMESPACE", ""),
    "index_name": os.getenv("INDEX_NAME", "personal-files"),
    "model_name": os.getenv("MODEL_NAME", "multilingual-e5-large"),
}

# Text file extensions to include
TEXT_FILE_EXTENSIONS = [
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".xml",
    ".html",
    ".htm",
    ".sh",
]

# PDF and other document extensions
DOCUMENT_EXTENSIONS = [".pdf", ".doc", ".ppt", ".xls", ".docx", ".pptx", ".xlsx"]

# Combine all supported extensions
SUPPORTED_EXTENSIONS = TEXT_FILE_EXTENSIONS + DOCUMENT_EXTENSIONS


def generate_file_hash(file_path: str) -> str:
    """Generate a SHA-256 hash for a given file."""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def convert_document_to_text(file_path: str) -> str:
    """
    Convert various document types to plain text using macOS native tools.

    Uses:
    - pdftotext for PDFs
    - textutil for Microsoft Office formats
    - cat for plain text files
    """
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == ".pdf":
            # Use pdftotext (from Poppler, installable via Homebrew)
            result = subprocess.run(
                ["pdftotext", file_path, "-"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout

        elif ext in [".docx", ".pptx", ".xlsx"]:
            # Use textutil for Office formats
            result = subprocess.run(
                ["textutil", "-convert", "txt", "-stdout", file_path],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout

        elif ext in TEXT_FILE_EXTENSIONS:
            # Simply read plain text files
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()

        else:
            logger.warning(f"Unsupported file type: {file_path}")
            return ""

    except subprocess.CalledProcessError as e:
        logger.error(f"Conversion error for {file_path}: {e}")
        return ""
    except Exception as e:
        logger.error(f"Unexpected error converting {file_path}: {e}")
        return ""


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
    """
    Hybrid approach to detect if a file has changed:
    1. Check modification timestamp first (fast)
    2. If timestamp changed, verify with hash calculation (moderate)
    3. Return True only if content actually changed

    Returns:
        bool: True if file has changed or is new, False otherwise
    """
    # If file not in processed records, it's new
    if filename not in processed_files:
        logger.debug(f"New file detected: {filename}")
        return True

    # Get last modified time of file
    current_mtime = os.path.getmtime(file_path)

    # If we have stored the modification time previously
    if "mtime" in processed_files[filename]:
        stored_mtime = processed_files[filename]["mtime"]

        # If modification time hasn't changed, skip further checks
        if (
            abs(current_mtime - stored_mtime) < 0.001
        ):  # Small epsilon for float comparison
            logger.debug(f"File unchanged (timestamp match): {filename}")
            return False

        # Timestamp changed, now check hash (more expensive)
        logger.debug(f"Timestamp changed for {filename}, verifying with hash...")
        file_hash = generate_file_hash(file_path)

        if processed_files[filename].get("hash") == file_hash:
            # Update timestamp but mark as unchanged
            processed_files[filename]["mtime"] = current_mtime
            logger.debug(
                f"File unchanged (hash match despite timestamp change): {filename}"
            )
            return False

        # Both timestamp and hash differ, file has changed
        logger.debug(f"File changed (timestamp and hash differ): {filename}")
        return True

    # No timestamp record, fall back to hash check
    logger.debug(f"No timestamp record for {filename}, checking hash...")
    file_hash = generate_file_hash(file_path)

    if processed_files[filename].get("hash") == file_hash:
        # Add timestamp but mark as unchanged
        processed_files[filename]["mtime"] = current_mtime
        logger.debug(f"File unchanged (hash match): {filename}")
        return False

    # Hash differs, file has changed
    logger.debug(f"File changed (hash differs): {filename}")
    return True


def upload_file_to_pinecone(file_path: str, index, namespace: str = "") -> bool:
    """
    Upload a file to Pinecone with proper error handling.

    Uses similar approach to the uploader.py script.
    """
    try:
        # Basic file validation
        if not os.path.isfile(file_path):
            logger.error(f"File does not exist: {file_path}")
            return False

        # Read file with error handling
        try:
            file_text = convert_document_to_text(file_path)
            if not file_text:
                logger.error(f"No text extracted from {file_path}")
                return False
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return False

        # Get file metadata
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
            "modification_date": datetime.fromtimestamp(file_stats.st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "uploaded_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Upsert to Pinecone
        index.upsert_records(namespace=namespace, records=[record])
        logger.info(f"Successfully uploaded {file_name} to Pinecone.")
        return True

    except Exception as e:
        logger.error(f"Error uploading {os.path.basename(file_path)}: {e}")
        return False


def process_documents(dry_run: bool = True):  # TODO: Change to False for production
    """
    Main workflow to process new/modified documents in Nextcloud folder.
    """
    # Get Pinecone API key from environment
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        logger.error("Pinecone API key not found in .env file")
        sys.exit(1)

    # Track processed files
    processed_files = load_processed_files()

    try:
        # Initialize Pinecone client
        pc = Pinecone(api_key=pinecone_api_key)

        # Verify index exists
        if CONFIG["index_name"] not in pc.list_indexes().names():
            logger.error(f"Index '{CONFIG['index_name']}' not found.")
            sys.exit(1)

        # Get the index
        index = pc.Index(CONFIG["index_name"])

    except Exception as e:
        logger.error(f"Failed to initialize Pinecone client: {e}")
        sys.exit(1)

    # Track results
    success_count = 0
    failed_files = []

    # Walk through Nextcloud folder
    for root, _, files in os.walk(CONFIG["TARGET_FOLDER"]):
        for filename in files:
            file_path = os.path.join(root, filename)

            # Check file extension
            if not any(file_path.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                continue

            # Hybrid approach for change detection
            if not check_file_changed(file_path, filename, processed_files):
                logger.info(f"Skipping unchanged file: {filename}")
                continue

            # File is new or changed, generate hash (if not already calculated in check_file_changed)
            file_hash = generate_file_hash(file_path)
            file_stats = os.stat(file_path)

            # Upload to Pinecone
            if not dry_run:
                if upload_file_to_pinecone(file_path, index, CONFIG["namespace"]):
                    success_count += 1

                    # Update processed files log with comprehensive metadata
                    processed_files[filename] = {
                        "path": file_path,
                        "hash": file_hash,
                        "mtime": file_stats.st_mtime,  # Store modification time
                        "ctime": file_stats.st_ctime,  # Store creation time
                        "size": file_stats.st_size,  # Store file size
                        "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                else:
                    failed_files.append(filename)
            else:
                logger.info(f"Dry run: {filename} would be uploaded.")

                # Log file details in verbose mode
                logger.debug(f"File: {filename}")
                logger.debug(f"  - Hash: {file_hash}")
                logger.debug(f"  - Size: {file_stats.st_size} bytes")
                logger.debug(
                    f"  - Created: {datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')}"
                )
                logger.debug(
                    f"  - Modified: {datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}"
                )

                # Update processed files even in dry run to demonstrate caching
                if dry_run and "--dry-run-update-cache" in sys.argv:
                    processed_files[filename] = {
                        "path": file_path,
                        "hash": file_hash,
                        "mtime": file_stats.st_mtime,
                        "ctime": file_stats.st_ctime,
                        "size": file_stats.st_size,
                        "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }

    # Save processed files log
    if not dry_run:
        save_processed_files(processed_files)

    # Summary
    logger.info("\n--- DOCUMENT PROCESSING SUMMARY ---")
    logger.info(f"Total files processed: {success_count + len(failed_files)}")
    logger.info(f"Successfully uploaded: {success_count}")

    if failed_files:
        logger.error(f"Failed uploads: {len(failed_files)}")
        logger.error("Failed files:")
        for failed_file in failed_files:
            logger.error(f"  - {failed_file}")
    else:
        logger.info("All files uploaded successfully!")
