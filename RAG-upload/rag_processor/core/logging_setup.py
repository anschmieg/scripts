"""
Logging configuration for RAG Processor
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Clear any existing handlers to avoid duplicate logging
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(console_handler)

    return logger


def debug_environment():
    """Print debug information about environment variables and paths."""
    print("\n===== ENVIRONMENT DEBUG INFORMATION =====")

    # Check if dotenv is loaded
    print("\n--- .env File Check ---")
    dotenv_path = Path(".env")
    if dotenv_path.exists():
        print(f".env file exists at: {dotenv_path.absolute()}")

        # Get original environment values before loading .env
        original_target_folder = os.environ.get("TARGET_FOLDER", "not set")
        print(f"TARGET_FOLDER before .env reload: {original_target_folder}")

        # Reload .env file to ensure it has priority
        load_dotenv(override=True)
        print("Reloaded .env file with override=True")
    else:
        print(f"WARNING: .env file NOT found at {dotenv_path.absolute()}")

    # Check TARGET_FOLDER
    print("\n--- TARGET_FOLDER Check ---")
    target_folder_raw = os.getenv("TARGET_FOLDER")
    print(f"Raw TARGET_FOLDER from env: {target_folder_raw}")

    if target_folder_raw:
        # First expand env vars like $HOME
        target_folder_expanded_vars = os.path.expandvars(target_folder_raw)
        print(f"After expandvars: {target_folder_expanded_vars}")

        # Then expand ~ if present
        target_folder_expanded = os.path.expanduser(target_folder_expanded_vars)
        print(f"Final expanded TARGET_FOLDER: {target_folder_expanded}")

        if os.path.exists(target_folder_expanded):
            print("✓ Target folder exists")
            # List some files in the target folder
            try:
                files = os.listdir(target_folder_expanded)[:5]  # List first 5 files
                print(f"Sample files in target folder: {files}")
            except Exception as e:
                print(f"Error listing target folder: {e}")
        else:
            print("✗ Target folder does NOT exist!")
    else:
        print("WARNING: TARGET_FOLDER environment variable is not set!")

    # Check other important env vars
    print("\n--- Other Important Environment Variables ---")
    print(
        f"PINECONE_API_KEY: {'Set (value hidden)' if os.getenv('PINECONE_API_KEY') else 'NOT SET!'}"
    )
    print(f"NAMESPACE: {os.getenv('NAMESPACE', 'NOT SET')}")
    print(f"INDEX_NAME: {os.getenv('INDEX_NAME', 'NOT SET')}")

    # Current working directory
    print("\n--- Script Locations ---")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script directory: {os.path.dirname(os.path.realpath(__file__))}")

    print("\n=====================================")


def check_config():
    """Check and print the CONFIG dictionary values."""
    try:
        print("\n--- CONFIG Dictionary Check ---")
        from rag_processor.core.config import CONFIG

        for key, value in CONFIG.items():
            if (
                key in ["PINECONE_API_KEY", "OPENAI_API_KEY", "MONGODB_URI"]
                or "KEY" in key
                or "SECRET" in key
            ):
                print(f"{key}: {'Set (value hidden)' if value else 'NOT SET!'}")
            else:
                print(f"{key}: {value}")
    except Exception as e:
        print(f"Error importing CONFIG: {e}")
