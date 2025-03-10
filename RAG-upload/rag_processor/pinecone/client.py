"""
Pinecone client initialization
"""

import os

from pinecone import Pinecone

from rag_processor.core.config import CONFIG
from rag_processor.core.logging_setup import logger


def get_pinecone_index():
    """Get the Pinecone index for uploads."""
    try:
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        pc = Pinecone(api_key=pinecone_api_key)
        index = pc.Index(CONFIG["index_name"])
        return index
    except Exception as e:
        logger.error(f"Failed to initialize Pinecone client: {e}")
        return None
