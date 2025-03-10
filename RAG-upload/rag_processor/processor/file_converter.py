"""
File conversion utilities for different document types
"""

import os
import subprocess
import tempfile

from rag_processor.core.logging_setup import logger


def convert_document_to_text(file_path: str) -> str:
    """Convert document to text based on file type."""
    file_extension = os.path.splitext(file_path)[1].lower()

    try:
        # Handle different file types
        if file_extension in [".pdf"]:
            return _extract_text_from_pdf(file_path)
        elif file_extension in [".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"]:
            return _extract_text_from_doc(file_path)
        elif file_extension in [
            ".txt",
            ".md",
            ".markdown",
            ".json",
            ".yml",
            ".yaml",
            ".csv",
            ".xml",
            ".html",
            ".htm",
        ]:
            return _read_text_file(file_path)
        else:
            logger.warning(f"Unsupported file format: {file_extension}")
            return ""
    except Exception as e:
        logger.error(f"Error converting {os.path.basename(file_path)} to text: {e}")
        return ""


def _extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF files using pdftotext."""
    try:
        # Use pdftotext (from poppler) to extract text
        result = subprocess.run(
            ["pdftotext", "-layout", file_path, "-"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"PDF extraction failed: {e}")
        return ""
    except FileNotFoundError:
        logger.error("pdftotext not found. Please install poppler-utils.")
        return ""


def _extract_text_from_doc(file_path: str) -> str:
    """Extract text from Office documents using textutil."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
            temp_path = temp_file.name

        # Use macOS textutil to convert Office documents to text
        subprocess.run(
            ["textutil", "-convert", "txt", "-output", temp_path, file_path], check=True
        )

        # Read the converted text file
        with open(temp_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        # Clean up temp file
        os.unlink(temp_path)

        return text
    except subprocess.CalledProcessError as e:
        logger.error(f"Document conversion failed: {e}")
        return ""
    except FileNotFoundError:
        logger.error("textutil not found. This program requires macOS.")
        return ""


def _read_text_file(file_path: str) -> str:
    """Read text directly from text files."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading text file {os.path.basename(file_path)}: {e}")
        return ""
