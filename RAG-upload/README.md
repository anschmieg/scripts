# Pinecone Document Processor

## Prerequisites

### System Requirements
- macOS (10.15+)
- Python 3.8+
- Homebrew

### Required Tools
1. Install Poppler for PDF conversion:
```bash
brew install poppler
```

2. Install Python dependencies:
```bash
pip3 install python-dotenv pinecone-client
```

## Configuration

### 1. Environment Setup
1. Create a `.env` file in the script directory with your Pinecone API key:
```
PINECONE_API_KEY=your_pinecone_api_key_here
```

2. Edit the script configuration:
- `TARGET_FOLDER`: Path to your documents folder
- `namespace`: Pinecone namespace (optional)
- `index_name`: Your Pinecone index name

### 2. Launchd Configuration
You need to create an XML plist file to schedule the script with macOS' launchd service.
1. The file `LAUNCHD_CONFIG.xml` contains a sample configuration. Adjust it to match your setup.
2. Save the file to `~/Library/LaunchAgents/com.yourname.pinecone-doc-processor.plist`.

### Installation
```bash
# Make script executable
chmod +x launchd-document-processor.py

    # ONLY If not done before, copy launchd configuration
    cp com.yourname.pinecone-doc-processor.plist ~/Library/LaunchAgents/

# Load the launchd job
launchctl load ~/Library/LaunchAgents/com.yourname.pinecone-doc-processor.plist
```

## Usage

### Scheduled Document Processor
This script is designed to run automatically via `launchd` on macOS. It processes documents in the specified folder and uploads them to Pinecone.

### Manual Actions
You can manually process documents or upload a single file using the `manual-actions.py` script.

#### Process All Documents
```bash
source .venv/bin/activate
python3 manual-actions.py --process
```

#### Upload a Single File
```bash
source .venv/bin/activate
python3 manual-actions.py --upload /path/to/your/file.txt
```

### Dry Run Mode
You can test the app without performing actual uploads by using the `--dry-run` flag:

```bash
source .venv/bin/activate
python3 launchd-document-processor.py --dry-run
```

To update the file tracking cache even in dry run mode:

```bash
source .venv/bin/activate
python3 launchd-document-processor.py --dry-run --dry-run-update-cache
```

### Verbose Logging
For debugging purposes, you can enable verbose logging with the `--verbose` or `-v` flag:

```bash
source .venv/bin/activate
python3 manual-actions.py --process --verbose
```

This can be combined with dry run mode for testing:

```bash
source .venv/bin/activate
python3 manual-actions.py --process --dry-run --verbose
```

## Supported File Types
- Text files: .txt, .md, .json, .yaml, .csv, etc.
- Documents: .pdf, .docx, .pptx, .xlsx

## Change Detection
The application uses a hybrid approach for efficient change detection:

1. **First Pass**: Check file modification timestamp (fast)
2. **Second Pass**: If timestamp changed, verify with hash calculation (moderate)
3. **Third Pass**: Only process and upload when content actually changed

This multi-stage approach optimizes performance while ensuring accuracy.

## Troubleshooting
- Check logs at `~/Library/Logs/PineconeDocProcessor.log`
- Verify Pinecone API key in `.env`
- Ensure target folder is accessible

## Features
- Automatic document processing
- Efficient hybrid change detection
- Supports multiple file types
- Tracks processed files to avoid duplicates
- Comprehensive metadata tracking (creation date, modification date, file hash)
- Logs processing results

## Metadata Tracking
The system tracks the following metadata for each processed file:
- File hash (SHA-256)
- Creation date and time
- Modification date and time
- File size in bytes
- Processing timestamp

This metadata is used for efficient change detection and is included in the Pinecone records for better data management and retrieval.