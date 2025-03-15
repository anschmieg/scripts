#!/usr/bin/env python3
"""
Verify Pinecone SDK installation and functionality
"""

import argparse
import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from project
from rag_processor.core.env import load_environment_variables
from rag_processor.core.logging_setup import logger


def check_sdk_installation():
    """Check if Pinecone SDK and Assistant plugin are installed"""
    pinecone_installed = False
    assistant_installed = False

    # Check Pinecone SDK
    try:
        import pinecone

        logger.info(
            f"✓ Found pinecone-client package (version: {pinecone.__version__})"
        )
        pinecone_installed = True
    except (ImportError, AttributeError):
        logger.error("✗ pinecone-client not found")
        logger.error("  Run: pip install pinecone-client")
        return False

    # Check Assistant plugin
    if pinecone_installed:
        try:
            from pinecone import Pinecone

            pc = Pinecone(api_key="dummy_key_for_check")
            if hasattr(pc, "assistant"):
                logger.info("✓ Found pinecone-assistant plugin")
                assistant_installed = True
            else:
                raise AttributeError("Assistant attribute not found")
        except (ImportError, AttributeError):
            logger.error("✗ pinecone assistant module not found")
            logger.error("  Run: pip install pinecone-plugin-assistant")
            return False

    return pinecone_installed and assistant_installed


def test_connection():
    """Test connection to Pinecone API"""
    # Load environment variables
    load_environment_variables()

    # Get API key
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        logger.error("✗ PINECONE_API_KEY environment variable not set")
        return False

    try:
        # Initialize Pinecone client
        from pinecone import Pinecone

        pc = Pinecone(api_key=api_key)

        # Test listing assistants
        assistants = pc.assistant.list_assistants()
        logger.info("✓ Successfully connected to Pinecone API")
        logger.info(f"✓ Found {len(assistants)} assistants")
        for asst in assistants:
            logger.info(f"  - {asst.name}")
        return True
    except Exception as e:
        logger.error(f"✗ Error connecting to Pinecone API: {e}")
        return False


def list_files(assistant_name=None):
    """List files from an assistant with improved display"""
    # Load environment variables
    load_environment_variables(override=True)

    # Get API key
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        logger.error("✗ PINECONE_API_KEY environment variable not set")
        return False

    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=api_key)

        # Get assistant name from args or environment
        assistant_name = assistant_name or os.environ.get("ASSISTANT_NAME")

        # Get the right assistant
        if assistant_name:
            logger.info(f"Using specified assistant: {assistant_name}")
            assistant = pc.assistant.Assistant(assistant_name=assistant_name)
        else:
            # Use first available assistant
            assistants = pc.assistant.list_assistants()
            if not assistants:
                logger.error("No assistants found")
                return False
            assistant = pc.assistant.Assistant(assistant_name=assistants[0].name)
            logger.info(f"Using first available assistant: {assistants[0].name}")

        # List files - try without parameters first for compatibility
        logger.info("Attempting to list files from Pinecone Assistant...")
        try:
            files = assistant.list_files()
        except TypeError:
            # This might be an older SDK that requires parameters
            try:
                logger.debug("Trying list_files with parameters (older SDK)")
                files = assistant.list_files(limit=100, offset=0)
            except Exception as e:
                logger.debug(f"Could not use parameters with list_files: {e}")
                # Try files attribute directly
                logger.debug("Trying to access files attribute directly")
                files = getattr(assistant, "files", [])

        # Extract file list from response
        file_list = getattr(files, "files", files) if files else []
        if isinstance(file_list, dict) and "files" in file_list:
            file_list = file_list["files"]

        # Display files with more details
        logger.info(f"Found {len(file_list)} files:")
        for f in file_list:
            file_id = getattr(f, "id", None)
            if not file_id and isinstance(f, dict):
                file_id = f.get("id", "Unknown")

            # Try to get more information about the file
            try:
                # Get more details about the file
                file_details = assistant.get_file(file_id)

                # Extract available information
                filename = getattr(file_details, "filename", None)
                if not filename and isinstance(file_details, dict):
                    filename = file_details.get("filename") or file_details.get("name")
                if not filename:
                    # Try different attribute paths
                    filename = getattr(f, "filename", None)
                    if not filename and isinstance(f, dict):
                        filename = f.get("filename") or f.get("name", file_id)
                    if not filename:
                        filename = getattr(f, "name", file_id)

                # Try to get creation date
                created_at = getattr(file_details, "created_at", "Unknown date")
                if isinstance(file_details, dict):
                    created_at = file_details.get("created_at", "Unknown date")

                # Try to get size information
                size_bytes = getattr(file_details, "size", 0)
                if isinstance(file_details, dict):
                    size_bytes = file_details.get("size", 0)

                if size_bytes:
                    if size_bytes < 1024:
                        size_str = f"{size_bytes} B"
                    elif size_bytes < 1024 * 1024:
                        size_str = f"{size_bytes / 1024:.1f} KB"
                    else:
                        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                else:
                    size_str = "Unknown size"

                # Display enhanced information
                logger.info(
                    f"  - {filename} (ID: {file_id}, Size: {size_str}, Created: {created_at})"
                )
            except Exception as e:
                # Fallback to basic info if get_file fails
                logger.debug(f"Could not get detailed info for file: {e}")
                if isinstance(f, dict):
                    filename = f.get("filename") or f.get("name", file_id)
                else:
                    filename = getattr(f, "filename", None) or getattr(
                        f, "name", file_id
                    )
                logger.info(f"  - {filename} (ID: {file_id})")

        return bool(file_list)
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Pinecone SDK installation")
    parser.add_argument(
        "--check-sdk", action="store_true", help="Check SDK installation"
    )
    parser.add_argument(
        "--test-connection", action="store_true", help="Test connection to Pinecone API"
    )
    parser.add_argument(
        "--list", action="store_true", help="List files from an assistant"
    )
    parser.add_argument("--assistant", type=str, help="Assistant name to use")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # If no specific actions are requested, run check-sdk by default
    if not any([args.check_sdk, args.test_connection, args.list]):
        args.check_sdk = True

    if args.check_sdk:
        check_sdk_installation()

    if args.test_connection:
        test_connection()

    if args.list:
        list_files(args.assistant)
