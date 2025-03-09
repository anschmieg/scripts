import argparse
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from pinecone import Pinecone  # Updated Pinecone import

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Text file extensions to include
TEXT_FILE_EXTENSIONS = [
    ".txt",
    ".md",
    ".markdown",
    ".config",
    ".ini",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".log",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".py",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".sh",
    ".bat",
    ".ps1",
    ".cfg",
    ".conf",
    ".env",
]


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Upload text files to Pinecone for RAG applications.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload files from a specific folder
  python uploader.py --folder /path/to/docs

  # Use a specific Pinecone API key
  python uploader.py --api-key YOUR_API_KEY --folder /path/to/docs

  # Specify the index name
  python uploader.py --index personal-files --folder /path/to/docs

  # Add specific file extensions
  python uploader.py --folder /path/to/docs --add-extensions .rst .tex .pdf
        """,
    )

    # Required arguments
    parser.add_argument(
        "--folder", "-f", help="Path to the folder containing text files to upload"
    )

    # Optional arguments
    parser.add_argument(
        "--api-key",
        "-k",
        help="Pinecone API key (can also be set via PINECONE_API_KEY environment variable)",
    )
    parser.add_argument(
        "--index",
        "-i",
        default="personal-files",
        help="Pinecone index name (default: personal-files)",
    )
    parser.add_argument(
        "--model",
        "-m",
        default="multilingual-e5-large",
        help="The embedding model to use (default: multilingual-e5-large)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "--list-extensions",
        "-l",
        action="store_true",
        help="List all supported file extensions and exit",
    )
    parser.add_argument(
        "--add-extensions",
        "-a",
        nargs="+",
        help="Additional file extensions to include (e.g. .rst .tex)",
    )
    parser.add_argument(
        "--namespace",
        "-n",
        default="",
        help="Namespace to use in Pinecone (default: empty string)",
    )

    return parser.parse_args()


# Validation for required configuration
def validate_config(folder_path, pinecone_api_key, index_name):
    """Validate configuration parameters before proceeding."""
    errors = []

    if not pinecone_api_key:
        errors.append(
            "Pinecone API key is missing. Provide it using --api-key or PINECONE_API_KEY in .env"
        )

    if not index_name:
        errors.append("Pinecone index name is missing")

    if not folder_path:
        errors.append("Folder path is missing. Please specify using --folder")
    elif not os.path.exists(folder_path):
        errors.append(f"Folder path does not exist: {folder_path}")
    elif not os.path.isdir(folder_path):
        errors.append(f"Path is not a directory: {folder_path}")

    if errors:
        for error in errors:
            logger.error(error)
        logger.error("Configuration validation failed. Please fix the issues above.")
        sys.exit(1)

    return True


# Function to upload files to Pinecone
def upload_file_to_pinecone(file_path, index, model_name, namespace=""):
    """Upload a file to Pinecone with proper error handling using the Pinecone SDK."""
    try:
        # Basic file validation
        if not os.path.isfile(file_path):
            logger.error(f"File does not exist: {file_path}")
            return False

        # Read file with error handling
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                file_text = file.read()
        except UnicodeDecodeError:
            logger.error(
                f"File encoding issue for {file_path}. Try different encoding."
            )
            return False
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return False

        # Get file metadata
        file_name = os.path.basename(file_path)

        # Create record for Pinecone
        record = {
            "_id": file_name,
            "data": file_text,  # The field that will be embedded
            "file_path": file_path,
            "uploaded_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Upsert to Pinecone
        index.upsert_records(namespace=namespace, records=[record])
        logger.info(f"Successfully uploaded {file_name} to Pinecone.")
        return True

    except Exception as e:
        logger.error(f"Error uploading {os.path.basename(file_path)}: {e}")
        return False


def has_text_extension(filename, extensions):
    """Check if the file has a text file extension."""
    _, ext = os.path.splitext(filename)
    return ext.lower() in extensions


def main():
    """Main function to process files and provide operation summary."""
    args = parse_arguments()

    # Set logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # List extensions if requested
    if args.list_extensions:
        print("Supported text file extensions:")
        for ext in sorted(TEXT_FILE_EXTENSIONS):
            print(f"  {ext}")
        return

    # Get configuration from arguments or environment variables
    folder_path = args.folder
    pinecone_api_key = args.api_key or os.getenv("PINECONE_API_KEY")
    index_name = args.index
    model_name = args.model
    namespace = args.namespace

    # Create the extensions list, adding any additional ones
    extensions = TEXT_FILE_EXTENSIONS.copy()
    if args.add_extensions:
        for ext in args.add_extensions:
            if not ext.startswith("."):
                ext = f".{ext}"
            if ext.lower() not in extensions:
                extensions.append(ext.lower())
                logger.info(f"Added additional extension: {ext}")

    logger.info("Starting Pinecone file upload process")

    # Validate configuration
    validate_config(folder_path, pinecone_api_key, index_name)

    try:
        # Initialize Pinecone client using the new style
        logger.info("Initializing Pinecone client")
        pc = Pinecone(api_key=pinecone_api_key)

        # Connect to index
        logger.info(f"Connecting to index: {index_name}")

        # Check if the index exists
        if index_name not in pc.list_indexes().names():
            logger.error(
                f"Index '{index_name}' not found. Available indexes: {pc.list_indexes().names()}"
            )
            sys.exit(1)

        # Get the index
        index = pc.Index(index_name)

        # Check if index is ready
        try:
            stats = index.describe_index_stats()
            logger.debug(f"Index stats: {stats}")
            logger.info(f"Successfully connected to Pinecone index: {index_name}")
        except Exception as e:
            logger.error(f"Failed to connect to Pinecone index: {e}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to initialize Pinecone client: {e}")
        sys.exit(1)

    # Check for text files in the folder
    all_files = os.listdir(folder_path)
    text_files = [f for f in all_files if has_text_extension(f, extensions)]

    if not text_files:
        logger.warning(f"No text files found in the folder: {folder_path}")
        logger.info(f"Supported extensions: {', '.join(extensions)}")
        return

    logger.info(f"Found {len(text_files)} text files to process")

    # Track results
    success_count = 0
    failed_files = []

    # Iterate through all text files in the folder
    for filename in text_files:
        file_path = os.path.join(folder_path, filename)
        logger.info(f"Processing file: {filename}")

        if upload_file_to_pinecone(file_path, index, model_name, namespace):
            success_count += 1
        else:
            failed_files.append(filename)

    # Summary
    logger.info("\n--- UPLOAD SUMMARY ---")
    logger.info(f"Total files processed: {len(text_files)}")
    logger.info(f"Successfully uploaded: {success_count}")

    if failed_files:
        logger.error(f"Failed uploads: {len(failed_files)}")
        logger.error("Failed files:")
        for failed_file in failed_files:
            logger.error(f"  - {failed_file}")
    else:
        logger.info("All files uploaded successfully!")


if __name__ == "__main__":
    main()
