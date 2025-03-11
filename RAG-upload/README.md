# RAG Processor

A document processing system for creating and maintaining a Retrieval-Augmented Generation (RAG) index using Pinecone Assistant.

## Overview

This tool scans a directory for supported document types, processes them, and uploads them to Pinecone Assistant for use in RAG applications.

## Features

- Recursive directory scanning
- Automatic detection of modified files
- Support for various document formats (PDF, DOCX, TXT, PPTX, etc.)
- Preprocessing of large documents with file format conversion
- Efficient caching to avoid reprocessing unchanged files
- Integration with Pinecone Assistant API

## Directory Structure

```
/
├── bin/                    # Command line scripts
│   ├── process-docs.py     # Main document processing script
│   └── utils.py            # Utility commands
├── tools/                  # Debugging and utility tools
│   └── debugger.py         # Environment debugging tools
├── rag_processor/          # Core package
│   ├── core/               # Core functionality
│   │   ├── config.py       # Configuration handling
│   │   ├── file_utils.py   # File utility functions
│   │   └── logging_setup.py # Logging configuration
│   ├── processor/          # Document processing
│   │   ├── document_processor.py # Main document processor
│   │   ├── preprocessing.py # File preprocessing logic
│   │   └── file_converter.py # Document text extraction
│   ├── pinecone/           # Pinecone integration 
│   │   ├── uploader.py     # Document upload logic
│   └── assistant/          # Pinecone Assistant integration
│       ├── client.py       # Assistant API client
│       └── validator.py    # Assistant validation utilities
├── backward_compat.py      # Backward compatibility script
├── .env                    # Environment configuration
└── README.md               # This file
```

## Installation

1. Clone the repository
2. Create a virtual environment: `python -m venv .venv`
3. Activate the virtual environment: `source .venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`

## Configuration

Create a `.env` file with the following variables:

```
PINECONE_API_KEY=your_api_key_here
TARGET_FOLDER=$HOME/path/to/documents
ASSISTANT_NAME=your_assistant_name_here
```

## Usage

### Process Documents

```bash
# Process all documents in the target folder
./bin/process-docs.py

# Dry run (no actual uploads)
./bin/process-docs.py --dry-run

# Verbose output
./bin/process-docs.py -v

# Override target folder
./bin/process-docs.py --target ~/Documents/some-other-folder

# Process without recursion (top-level files only)
./bin/process-docs.py --no-recursive

# Display environment debug info
./bin/process-docs.py --debug-env
```

### Utilities

```bash
# Upload a specific file
./bin/utils.py upload /path/to/file.pdf

# Process all documents like process-docs.py
./bin/utils.py process

# Validate database against tracking JSON
./bin/utils.py validate

# Re-upload files missing from database
./bin/utils.py validate --reupload

# Show help
./bin/utils.py --help
```

### Debugging

```bash
# Check environment variables
./tools/debugger.py env

# List directories and files in the target folder
./tools/debugger.py list

# Validate database against tracking JSON (with detailed output)
./tools/debugger.py validate

# Run a command with clean environment
./tools/debugger.py reset ./bin/process-docs.py --debug-env

# Show help
./tools/debugger.py --help
```

## Backward Compatibility

If you previously used the old script names, a backward compatibility layer is available. Run:

```bash
python backward_compat.py
```

This will create symlinks from old script names to the new ones, allowing you to continue using the old names if needed.

## Prerequisites

- Python 3.8+
- Pandoc (for document preprocessing)
- pdftotext (optional, for better PDF text extraction)

## Scheduled Database Validation

To ensure your database integrity, you can set up a scheduled task to validate that all tracked files are still present in the Pinecone Assistant:

```bash
# Check for missing files in database
./run.sh validate --check-disk

# Automatically re-upload missing files 
./run.sh validate --reupload

# Clean up tracking for files that no longer exist
./run.sh validate --check-disk --clean
```

You can set up a cron job to run the validation periodically.

## Pinecone Assistant Integration

This tool now integrates with Pinecone Assistant API instead of the older Pinecone Vector DB with integrated embedding. The Assistant API provides a simpler way to upload and manage documents for RAG applications.

### Key Changes

- Documents are uploaded directly to Pinecone Assistant
- No need for manual embedding generation
- Simplified API interactions
- Better metadata handling

## Pinecone Assistant SDK Compatibility

The Pinecone Assistant SDK has different versions with varying APIs. This tool attempts to handle these differences gracefully:

- For newer SDK versions: We use `pc.assistant.Assistant(assistant_name="name")` with appropriate methods
- For older SDK versions: We fall back to different API patterns as needed

If you encounter SDK compatibility issues, try running the test script to diagnose:

```bash
# Check SDK installation and capabilities
./bin/test_assistant_sdk.py --check-sdk --verbose

# Test listing files in the assistant
./bin/test_assistant_sdk.py --list --verbose
```

## Testing the SDK Integration

The package now uses the official Pinecone SDK with the assistant plugin. You can test this integration with:

```bash
# Test listing files in the assistant
./bin/test_assistant_sdk.py --list --verbose

# Test uploading a file to the assistant
./bin/test_assistant_sdk.py --upload /path/to/file.pdf --verbose
```

This ensures that the SDK integration is working properly.

## Performance Optimization

The system supports optimized batch uploading of files to significantly improve throughput:

```bash
# Process with optimized batch upload (5 concurrent workers, batches of 20 files)
./bin/process-docs.py --parallel 5 --batch-size 20

# Show progress bar during processing
./bin/process-docs.py --progress

# Upload multiple files concurrently
./bin/utils.py upload file1.pdf file2.pdf file3.pdf --parallel 3 --progress
```

These optimizations provide significant performance improvements:

- **Batch Processing**: Groups files into batches to reduce per-file overhead
- **Concurrent Processing**: Uploads multiple files in parallel
- **Progress Reporting**: Shows real-time progress bars during processing
- **Adaptive Polling**: Automatically adjusts status polling frequency based on server responsiveness

For large document collections, these optimizations can improve performance by 5-10x for small files and 2-3x for larger files.

## License

MIT License