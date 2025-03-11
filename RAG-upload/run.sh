#!/bin/bash

set -e

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directory where the script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Setup virtual environment if it doesn't exist
if [ ! -d .venv ]; then
  echo -e "${YELLOW}Creating virtual environment...${NC}"
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
else
  source .venv/bin/activate
fi

# Command dispatcher
case "$1" in
env)
  echo -e "${GREEN}Testing environment setup...${NC}"
  ./bin/test_assistant_sdk.py --check-sdk --verbose
  ;;
list)
  echo -e "${GREEN}Listing files...${NC}"
  shift
  ./bin/test_assistant_sdk.py --list --verbose $@
  ;;
upload)
  echo -e "${GREEN}Uploading file...${NC}"
  shift
  ./bin/utils.py upload $@
  ;;
validate)
  echo -e "${GREEN}Validating files...${NC}"
  shift
  ./bin/utils.py validate $@
  ;;
process)
  echo -e "${GREEN}Processing documents...${NC}"
  shift
  ./bin/process-docs.py $@
  ;;
help)
  echo "Usage: ./run.sh COMMAND [options]"
  echo ""
  echo "Commands:"
  echo "  env                  Test environment setup"
  echo "  list                 List files (--files to show file paths)"
  echo "  upload FILE          Upload a file"
  echo "  validate             Validate file tracking"
  echo "  process              Process documents"
  echo "  help                 Show this help"
  echo ""
  echo "Common options:"
  echo "  --verbose            Show verbose output"
  echo "  --dry-run            Don't actually upload files"
  ;;
*)
  echo -e "${RED}Unknown command: $1${NC}"
  echo "Run './run.sh help' for usage information"
  exit 1
  ;;
esac
