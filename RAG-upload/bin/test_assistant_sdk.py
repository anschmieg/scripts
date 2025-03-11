#!/usr/bin/env python3
"""
Verify Pinecone SDK installation and functionality
"""

import importlib.util
import os
import sys

from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import logger
from rag_processor.core.logging_setup import logger


# Load environment variables safely
def load_environment_variables():
    """Load environment variables from .env file"""
    dotenv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        return True
    else:
        logger.warning(f".env file not found at {dotenv_path}")
        return False


def check_sdk_installation():
    """Check if Pinecone SDK and Assistant plugin are installed"""
    # Check for pinecone-client
    pinecone_spec = importlib.util.find_spec("pinecone")
    if pinecone_spec is None:
        logger.error("✗ pinecone-client not found")
        logger.error("  Run: pip install pinecone-client")
        return False

    # Try to import and get version
    try:
        import pinecone

        logger.info(
            f"✓ Found pinecone-client package (version: {pinecone.__version__})"
        )
    except (ImportError, AttributeError):
        logger.error("✗ Error importing pinecone package")
        return False

    # Check for assistant plugin
    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key="dummy_key_for_check")
        if hasattr(pc, "assistant"):
            logger.info("✓ Found pinecone-assistant plugin")
            return True
        else:
            logger.error("✗ pinecone assistant module not found")
            logger.error("  Run: pip install pinecone-plugin-assistant")
            return False
    except (ImportError, AttributeError):
        logger.error("✗ pinecone assistant module not found")
        logger.error("  Run: pip install pinecone-plugin-assistant")
        return False


def test_connection():
    """Test connection to Pinecone API"""
    try:
        # Load environment variables
        load_environment_variables()

        # Get API key
        api_key = os.environ.get("PINECONE_API_KEY")
        if not api_key:
            logger.error("✗ PINECONE_API_KEY environment variable not set")
            return False

        # Try to connect
        from pinecone import Pinecone

        pc = Pinecone(api_key=api_key)

        # Check if we can access the assistant module
        if hasattr(pc, "assistant"):
            logger.info("✓ Successfully connected to Pinecone API")

            # Try to list assistants
            try:
                assistants = pc.assistant.list_assistants()
                logger.info(f"✓ Found {len(assistants)} assistants")
                for asst in assistants:
                    logger.info(f"  - {asst.name}")
                return True
            except Exception as e:
                logger.error(f"✗ Error listing assistants: {e}")
                return False
        else:
            logger.error("✗ Assistant plugin not properly installed")
            return False

    except Exception as e:
        logger.error(f"✗ Error connecting to Pinecone API: {e}")
        return False


# Update the list_files function to show more details about each file


def list_files(assistant_name=None):
    """List files from a specific assistant or default assistant"""
    try:
        # Load environment variables
        load_environment_variables()

        # Get API key
        api_key = os.environ.get("PINECONE_API_KEY")
        if not api_key:
            logger.error("✗ PINECONE_API_KEY environment variable not set")
            return False

        from pinecone import Pinecone

        pc = Pinecone(api_key=api_key)

        # Use specified assistant name or get from env
        assistant_name = assistant_name or os.environ.get("ASSISTANT_NAME")

        if assistant_name:
            logger.debug(f"Initializing assistant with name: {assistant_name}")
            assistant = pc.assistant.Assistant(assistant_name=assistant_name)
        else:
            logger.warning("No assistant name specified, using default assistant")
            # Try to list assistants and use the first one
            assistants = pc.assistant.list_assistants()
            if assistants and len(assistants) > 0:
                assistant = pc.assistant.Assistant(assistant_name=assistants[0].name)
                logger.info(f"Using assistant: {assistants[0].name}")
            else:
                logger.error("No assistants found")
                return False

        logger.info("Attempting to list files from Pinecone Assistant...")

        try:
            # Try with assistant.list_files() method
            files = assistant.list_files()
            if hasattr(files, "files"):
                file_list = files.files
            else:
                file_list = files

            logger.info(f"Found {len(file_list)} files:")
            for f in file_list:
                # Try to get more details about each file
                try:
                    file_details = assistant.get_file(file_id=f.id)
                    filename = (
                        getattr(file_details, "filename", None)
                        or getattr(f, "filename", None)
                        or "Unknown"
                    )
                    file_id = getattr(f, "id", "Unknown ID")
                    file_size = getattr(file_details, "size", None) or getattr(
                        f, "size", "Unknown"
                    )
                    if isinstance(file_size, int):
                        file_size = (
                            f"{file_size / 1024:.1f} KB"
                            if file_size < 1024 * 1024
                            else f"{file_size / (1024 * 1024):.1f} MB"
                        )
                    logger.info(f"  - {filename} (ID: {file_id}, Size: {file_size})")
                except Exception:
                    # Fallback to basic info
                    logger.info(f"  - {getattr(f, 'filename', None) or f.id}")
            return True
        except Exception as e:
            logger.error(f"Error listing files from Pinecone Assistant: {e}")
            return False

    except Exception as e:
        logger.error(f"Error connecting to Pinecone API: {e}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Verify Pinecone SDK installation")
    parser.add_argument(
        "--check-sdk", action="store_true", help="Check SDK installation"
    )
    parser.add_argument(
        "--test-connection", action="store_true", help="Test connection to Pinecone API"
    )
    parser.add_argument(
        "--list", action="store_true", help="List files from the assistant"
    )
    parser.add_argument("--assistant", type=str, help="Assistant name to use")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.check_sdk or not any([args.check_sdk, args.test_connection, args.list]):
        check_sdk_installation()

    if args.test_connection:
        test_connection()

    if args.list:
        list_files(args.assistant)
