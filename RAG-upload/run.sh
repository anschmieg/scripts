#!/bin/bash

set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directory where the script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure virtual environment is activated
if [ ! -d .venv ]; then
  echo -e "${YELLOW}Creating virtual environment...${NC}"
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
else
  source .venv/bin/activate
fi

# Display header
echo -e "${BLUE}Pinecone Assistant RAG Uploader${NC}\n"

# Map command line arguments to their correct parameters
map_args() {
  local args=()

  for arg in "$@"; do
    case "$arg" in
    --verbose | -v)
      # Add this to the beginning so it applies globally
      args=("--verbose" "${args[@]}")
      ;;
    --remove-missing)
      # Map this to --clean for compatibility
      args+=("--clean")
      ;;
    *)
      # Pass other arguments unchanged
      args+=("$arg")
      ;;
    esac
  done

  echo "${args[@]}"
}

# Command dispatcher
case "$1" in
delete)
  echo -e "${GREEN}Deleting files...${NC}"
  shift
  if [ -z "$1" ]; then
    echo -e "${RED}Error: No file ID specified${NC}"
    echo "Usage: ./run.sh delete <file_id> [<file_id>...]"
    exit 1
  fi
  ./bin/utils.py delete "$@"
  ;;
env)
  echo -e "${GREEN}Testing environment setup...${NC}"
  ./bin/test_assistant_sdk.py --check-sdk --test-connection --verbose
  ;;
list)
  echo -e "${GREEN}Listing files...${NC}"
  shift
  # Map command line arguments to proper flags
  mapped_args=$(map_args "$@")
  ./bin/test_assistant_sdk.py --list $mapped_args
  ;;
upload)
  echo -e "${GREEN}Uploading file...${NC}"
  shift
  if [ -z "$1" ]; then
    echo -e "${RED}Error: No file specified${NC}"
    echo "Usage: ./run.sh upload <filepath>"
    exit 1
  fi

  # Extract files to upload (everything before any option)
  files=()
  while [ $# -gt 0 ] && [[ "$1" != --* ]]; do
    files+=("$1")
    shift
  done

  # Map remaining arguments
  mapped_args=$(map_args "$@")

  # Run the command with proper argument order
  ./bin/utils.py upload "${files[@]}" $mapped_args
  ;;
validate)
  echo -e "${GREEN}Validating files...${NC}"
  shift
  # Map command line arguments to proper flags
  mapped_args=$(map_args "$@")
  ./bin/utils.py validate $mapped_args
  ;;
process)
  echo -e "${GREEN}Processing documents...${NC}"
  shift
  # Map command line arguments to proper flags
  mapped_args=$(map_args "$@")
  ./bin/process-docs.py $mapped_args
  ;;
help | --help | -h)
  echo "Usage: ./run.sh COMMAND [options]"
  echo ""
  echo "Commands:"
  echo "  env                  Test environment setup and connection"
  echo "  list [--assistant NAME] List files in the assistant"
  echo "  upload FILE          Upload a file to the assistant"
  echo "  validate             Validate file tracking"
  echo "  process              Process and upload documents"
  echo "  delete ID [ID...]     Delete files from the assistant by ID"
  echo "  delete --by-name NAME Delete files by name instead of ID"
  echo "  help                 Show this help"
  echo ""
  echo "Common options:"
  echo "  --verbose, -v        Show verbose output"
  echo "  --dry-run            Don't actually upload files (with process command)"
  echo "  --parallel N         Number of concurrent upload workers (default: 5)"
  echo "  --batch-size N       Number of files to batch into a request (default: 20)"
  echo "  --no-progress        Disable progress bar (progress bar is on by default)"
  echo "  --remove-missing     Remove entries for missing files (with validate command)"
  echo "                       (alias for --clean)"
  ;;
*)
  echo -e "${RED}Unknown command: $1${NC}"
  echo "Run './run.sh help' for usage information"
  exit 1
  ;;
esac
