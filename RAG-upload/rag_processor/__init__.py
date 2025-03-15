"""
Pinecone Document Processor

A package for processing, tracking, and uploading documents to Pinecone
for RAG (Retrieval Augmented Generation) applications.

This package includes tools for:
- Detecting file changes with a hybrid timestamp/hash approach
- Converting various document types to text
- Tracking processed files
- Uploading documents to Pinecone
"""

# Ensure environment is loaded first
from .core import env  # noqa: F401

__version__ = "1.0.0"
