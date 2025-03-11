"""
Pinecone Assistant API client using the official SDK
"""

import os
from typing import Dict, Optional

from pinecone import Pinecone

from rag_processor.core.config import CONFIG
from rag_processor.core.logging_setup import logger


class PineconeAssistantClient:
    """Client for interacting with Pinecone Assistant API using the official SDK."""

    def __init__(self, api_key: str = None, assistant_name: str = None):
        """Initialize the Pinecone Assistant client."""
        self.api_key = api_key or os.environ.get("PINECONE_API_KEY")
        if not self.api_key:
            raise ValueError("Pinecone API key is required")

        self.assistant_name = assistant_name or CONFIG.get("assistant_name")
        if not self.assistant_name:
            logger.info("No specific assistant_name provided, using default assistant")

        try:
            # Initialize the Pinecone client
            self.pc = Pinecone(api_key=self.api_key)

            # Initialize the Assistant object if a name is provided
            if self.assistant_name:
                logger.debug(f"Initializing assistant with name: {self.assistant_name}")
                self.assistant = self.pc.assistant.Assistant(
                    assistant_name=self.assistant_name
                )
            else:
                logger.debug(
                    "No assistant name provided, using default assistant capabilities"
                )
                self.assistant = None

        except Exception as e:
            logger.error(f"Failed to initialize Pinecone Assistant client: {e}")
            raise

    def upload_file(self, file_path: str, metadata: Optional[Dict] = None) -> Dict:
        """Upload a file to Pinecone Assistant."""
        try:
            if not os.path.exists(file_path):
                return {"error": f"File not found: {file_path}"}

            # Note: We're not reinitializing self.pc here as it was already done in __init__

            # Check if we have an assistant name
            if self.assistant:
                logger.debug(
                    f"Uploading file {file_path} to assistant: {self.assistant_name}"
                )
                response = self.assistant.upload_file(
                    file_path=file_path, metadata=metadata
                )
            else:
                # No assistant name provided - create one with a default name
                logger.info(
                    "No specific assistant_name provided, using 'default' assistant"
                )
                default_name = "default"
                try:
                    default_assistant = self.pc.assistant.Assistant(
                        assistant_name=default_name
                    )
                    logger.debug(f"Using assistant with name: {default_name}")
                    response = default_assistant.upload_file(
                        file_path=file_path, metadata=metadata
                    )
                except Exception as e:
                    # If default assistant doesn't exist, create it
                    logger.warning(f"Error with default assistant: {e}")
                    logger.info("Creating new assistant named 'default'")
                    default_assistant = self.pc.assistant.Assistant.create(
                        name=default_name
                    )
                    response = default_assistant.upload_file(
                        file_path=file_path, metadata=metadata
                    )

            # Convert response to dict if necessary
            return self._convert_response_to_dict(response)

        except Exception as e:
            logger.error(f"Error uploading file to Pinecone Assistant: {e}")
            return {"error": str(e)}

    def get_file(self, file_id: str) -> Dict:
        """
        Get file information from Pinecone Assistant.

        Args:
            file_id: ID of the file to retrieve

        Returns:
            Dict: File information
        """
        try:
            if self.assistant:
                response = self.assistant.get_file(file_id=file_id)
            else:
                # Try different approaches based on SDK version
                try:
                    response = self.pc.assistant.get_file(file_id=file_id)
                except AttributeError:
                    default_assistant = self.pc.assistant.Assistant()
                    response = default_assistant.get_file(file_id=file_id)

            return self._convert_response_to_dict(response)
        except Exception as e:
            logger.error(f"Error retrieving file from Pinecone Assistant: {e}")
            return {"error": str(e)}

    def list_files(self, limit: int = 100, offset: int = 0) -> Dict:
        """
        List files in Pinecone Assistant.

        Args:
            limit: Maximum number of files to return
            offset: Pagination offset

        Returns:
            Dict: List of files
        """
        try:
            # Simplified logic with clear fallback paths
            if self.assistant:
                # Try accessing methods in order of likelihood
                try:
                    response = self.assistant.list_files(limit=limit, offset=offset)
                    return self._convert_response_to_dict(response)
                except AttributeError:
                    # Try files attribute
                    files = getattr(self.assistant, "files", None)
                    if files is not None:
                        return {"files": files, "total": len(files)}

            # Try on the pc.assistant directly
            try:
                response = self.pc.assistant.list_files(limit=limit, offset=offset)
                return self._convert_response_to_dict(response)
            except AttributeError:
                # Fall back to creating a default assistant for listing
                default_assistant = self.pc.assistant.Assistant()
                try:
                    files = default_assistant.files
                    if isinstance(files, list):
                        return {"files": files, "total": len(files)}
                    else:
                        return self._convert_response_to_dict(files)
                except Exception as inner_e:
                    logger.error(f"Error accessing files attribute: {inner_e}")
                    return {"error": str(inner_e), "files": [], "total": 0}

        except Exception as e:
            logger.error(f"Error listing files from Pinecone Assistant: {e}")
            return {"error": str(e), "files": [], "total": 0}

    def delete_file(self, file_id: str) -> Dict:
        """
        Delete a file from Pinecone Assistant.

        Args:
            file_id: ID of the file to delete

        Returns:
            Dict: Response from the API
        """
        try:
            if self.assistant and self.assistant_name:
                self.assistant.delete_file(file_id=file_id)
            else:
                try:
                    self.pc.assistant.delete_file(file_id=file_id)
                except AttributeError:
                    default_assistant = self.pc.assistant.Assistant()
                    default_assistant.delete_file(file_id=file_id)

            return {"success": True}
        except Exception as e:
            logger.error(f"Error deleting file from Pinecone Assistant: {e}")
            return {"error": str(e)}

    def _convert_response_to_dict(self, response):
        """Convert SDK response object to dict."""
        if response is None:
            return {}

        if isinstance(response, dict):
            return response

        if hasattr(response, "__dict__"):
            # Some SDK objects have a __dict__ attribute we can use
            return response.__dict__

        if hasattr(response, "to_dict"):
            # Some SDK objects have a to_dict method
            return response.to_dict()

        # Convert object to dictionary comprehensively
        try:
            # Try to access object attributes
            result = {}
            for attr in dir(response):
                if not attr.startswith("_"):  # Skip private attributes
                    try:
                        value = getattr(response, attr)
                        if not callable(value):  # Skip methods
                            result[attr] = value
                    except Exception:
                        pass
            return result
        except Exception:
            # If all else fails, return as string representation
            return {"raw_response": str(response)}
