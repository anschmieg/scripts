"""
Pinecone Assistant API client using the official SDK
"""

import os
from typing import Any, Dict, List, Optional, Union

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

    def get_assistant(self):
        """Get or create the assistant object if not already initialized"""
        if self.assistant is not None:
            return self.assistant

        try:
            # First try to get the assistant with the configured name
            if self.assistant_name:
                self.assistant = self.pc.assistant.Assistant(
                    assistant_name=self.assistant_name
                )
                return self.assistant

            # Try to use a default assistant
            try:
                default_name = "default"
                self.assistant = self.pc.assistant.Assistant(
                    assistant_name=default_name
                )
                self.assistant_name = default_name
                return self.assistant
            except Exception:
                # Get the first available assistant
                assistants = self.pc.assistant.list_assistants()
                if assistants:
                    self.assistant = self.pc.assistant.Assistant(
                        assistant_name=assistants[0].name
                    )
                    self.assistant_name = assistants[0].name
                    return self.assistant

                # As a last resort, create a default assistant
                self.assistant = self.pc.assistant.Assistant.create(name="default")
                self.assistant_name = "default"
                return self.assistant

        except Exception as e:
            logger.error(f"Failed to get or create assistant: {e}")
            return None

    def upload_file(self, file_path: str, metadata: Optional[Dict] = None) -> Dict:
        """Upload a file to Pinecone Assistant."""
        try:
            if not os.path.exists(file_path):
                return {"error": f"File not found: {file_path}"}

            # Note: We're not reinitializing self.pc here as it was already done in __init__

            # Check if we have an assistant name
            if not self.assistant:
                self.get_assistant()

            if not self.assistant:
                return {"error": "Could not get assistant for upload"}

            logger.debug(
                f"Uploading file {file_path} to assistant: {self.assistant_name}"
            )
            response = self.assistant.upload_file(
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
            if not self.assistant:
                self.get_assistant()

            if not self.assistant:
                return {"error": "Could not get assistant"}

            response = self.assistant.get_file(file_id=file_id)
            return self._convert_response_to_dict(response)
        except Exception as e:
            logger.error(f"Error retrieving file from Pinecone Assistant: {e}")
            return {"error": str(e)}

    def list_files(self) -> Dict[str, Union[List[Dict[str, Any]], str]]:
        """
        List files in Pinecone Assistant using the most compatible approach.

        Returns:
            Dict with 'files' key containing list of files
        """
        try:
            if not self.assistant:
                self.get_assistant()

            if not self.assistant:
                return {"error": "Could not get assistant", "files": []}

            # First try to directly access the files attribute
            files_attr = getattr(self.assistant, "files", None)
            if files_attr is not None and isinstance(files_attr, list):
                logger.debug(f"Got files attribute with {len(files_attr)} files")
                return {
                    "files": [self._convert_response_to_dict(f) for f in files_attr]
                }

            # Second, try to call list_files() without parameters
            try:
                response = self.assistant.list_files()
                if response is not None:
                    # Handle different response formats
                    if hasattr(response, "files"):
                        files = response.files
                        if files is not None:
                            return {
                                "files": [
                                    self._convert_response_to_dict(f) for f in files
                                ]
                            }
                    elif isinstance(response, list):
                        return {
                            "files": [
                                self._convert_response_to_dict(f) for f in response
                            ]
                        }
                    elif isinstance(response, dict) and "files" in response:
                        return response

                    # Fall back to returning the response directly
                    return {"files": [self._convert_response_to_dict(response)]}
            except Exception as e:
                logger.debug(f"Error calling list_files(): {e}")
                pass

            # If we get here, all attempts failed
            logger.warning("Failed to list files using all known methods")
            return {"error": "Failed to list files", "files": []}

        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return {"error": str(e), "files": []}

    def delete_file(self, file_id: str) -> Dict:
        """
        Delete a file from Pinecone Assistant.

        Args:
            file_id: ID of the file to delete

        Returns:
            Dict: Response from the API
        """
        try:
            if not self.assistant:
                self.get_assistant()

            if not self.assistant:
                return {"error": "Could not get assistant"}

            self.assistant.delete_file(file_id=file_id)
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
