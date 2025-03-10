#!/bin/bash
# Helper script to run RAG Processor commands from the root directory

# Ensure script is executable
chmod +x bin/process-docs.py
chmod +x bin/utils.py
chmod +x tools/debugger.py

# Get the command and pass all arguments
COMMAND=$1
shift # Remove first argument (the command) from $@

case $COMMAND in
process)
  ./bin/process-docs.py "$@"
  ;;
upload)
  ./bin/utils.py upload "$@"
  ;;
validate)
  ./bin/utils.py validate "$@"
  ;;
debug)
  ./tools/debugger.py "$@"
  ;;
list)
  ./tools/debugger.py list "$@"
  ;;
env)
  ./tools/debugger.py env
  ;;
migrate)
  python backward_compat.py
  ;;
help | --help | -h)
  echo "Usage: ./run.sh COMMAND [OPTIONS]"
  echo ""
  echo "Commands:"
  echo "  process   Process documents in target folder"
  echo "  upload    Upload a specific file to Pinecone"
  echo "  validate  Validate database against processed files tracking"
  echo "  debug     Run debugging tools"
  echo "  list      List documents in target folder"
  echo "  env       Show environment variables"
  echo "  migrate   Set up backward compatibility"
  echo "  help      Show this help message"
  echo ""
  echo "Examples:"
  echo "  ./run.sh process --dry-run -v              Process documents in dry-run mode with verbose output"
  echo "  ./run.sh upload /path/to/document.pdf      Upload a specific document"
  echo "  ./run.sh validate --reupload               Validate database and re-upload missing files"
  echo "  ./run.sh list --files                      List files in target folder"
  echo "  ./run.sh env                               Show environment debug information"
  ;;
*)
  echo "Unknown command: $COMMAND"
  echo "Run './run.sh help' for usage information."
  exit 1
  ;;
esac
