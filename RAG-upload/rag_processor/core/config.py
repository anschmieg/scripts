"""
Configuration management for RAG Processor
"""

import os

from dotenv import load_dotenv

# Remove redundant code - we only need one load_dotenv call

# Load environment variables from .env file WITH override
load_dotenv(override=True)

# Handle $HOME or ~/ expansions in TARGET_FOLDER
target_folder = os.getenv("TARGET_FOLDER", "~/Nextcloud/Documents")
# First expand any $HOME or $USER type variables
target_folder = os.path.expandvars(target_folder)
# Then expand any ~ character
target_folder = os.path.expanduser(target_folder)

# Configuration from .env file
CONFIG = {
    "TARGET_FOLDER": target_folder,
    "processed_log_path": os.path.expanduser(
        "~/Library/Application Support/PineconeDocProcessor/processed_files.json"
    ),
    "log_path": os.path.expanduser("~/Library/Logs/PineconeDocProcessor.log"),
    # Pinecone Assistant options
    "pinecone_api_key": os.getenv("PINECONE_API_KEY"),
    "assistant_api_url": os.getenv(
        "ASSISTANT_API_URL", "https://assistant.api.pinecone.io/v1"
    ),
    "assistant_name": os.getenv(
        "ASSISTANT_NAME", ""
    ),  # Changed from assistant_id to assistant_name
    "use_assistant_api": os.getenv("USE_ASSISTANT_API", "true").lower()
    == "true",  # Toggle for API choice
    # Legacy options kept for backward compatibility
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
]

# PDF and other document extensions
DOCUMENT_EXTENSIONS = [".pdf", ".doc", ".ppt", ".xls", ".docx", ".pptx", ".xlsx"]

# Combine all supported extensions
SUPPORTED_EXTENSIONS = TEXT_FILE_EXTENSIONS + DOCUMENT_EXTENSIONS
