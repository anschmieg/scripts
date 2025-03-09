#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from datetime import datetimefrom datetime import datetime

from pinecone import Pineconefrom pinecone import Pinecone

from assets.document_processor import CONFIG, process_documents, upload_file_to_pineconefrom assets.document_processor import CONFIG, process_documents, upload_file_to_pinecone

# Configure logging - will be updated based on verbose flagd based on verbose flag
logger = logging.getLogger(__name__)logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Configure logging based on verbosity level"""
    log_level = logging.DEBUG if verbose else logging.INFO    log_level = logging.DEBUG if verbose else logging.INFO

    # Configure root loggerger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s", - %(message)s",
        handlers=[logging.StreamHandler()],   handlers=[logging.StreamHandler()],
    )    )

    # Set level for specific loggers if needed
    logging.getLogger("assets.document_processor").setLevel(log_level)setLevel(log_level)
    logging.getLogger(__name__).setLevel(log_level)    logging.getLogger(__name__).setLevel(log_level)

    if verbose:
        logger.debug("Verbose logging enabled")        logger.debug("Verbose logging enabled")


def upload_single_file(file_path: str, dry_run: bool = False):run: bool = False):
    """Upload a single file to Pinecone."""
    pinecone_api_key = os.getenv("PINECONE_API_KEY")tenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        logger.error("Pinecone API key not found in .env file").error("Pinecone API key not found in .env file")
        return        return

    try:
        if dry_run:
            logger.info(f"DRY RUN: Would upload file {file_path} to Pinecone")th.basename(file_path)
            logger.debug(
                f"DRY RUN: File metadata - Size: {os.path.getsize(file_path)} bytes"hash = ""
            )
            return True        # If in verbose mode, calculate hash and log details
.DEBUG:
        pc = Pinecone(api_key=pinecone_api_key)ort generate_file_hash
        index = pc.Index(CONFIG["index_name"])
        if upload_file_to_pinecone(file_path, index, CONFIG["namespace"]):
            logger.info(f"Successfully uploaded {file_path} to Pinecone.")
            return Trueogger.info(f"DRY RUN: Would upload file {file_path} to Pinecone")
        else:
            logger.error(f"Failed to upload {file_path} to Pinecone.")ogging in verbose mode
            if logging.getLogger().level == logging.DEBUG:
                logger.debug(f"File details for {file_name}:")
                logger.debug(f"  - Hash: {file_hash}")(f"Failed to initialize Pinecone client: {e}")
                logger.debug(f"  - Size: {file_stats.st_size} bytes")        return False
                logger.debug(f"  - Created: {datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')}")
                logger.debug(f"  - Modified: {datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            
            return True
   description="Manual actions for document processing."
        pc = Pinecone(api_key=pinecone_api_key)
        index = pc.Index(CONFIG["index_name"])ent(
        if upload_file_to_pinecone(file_path, index, CONFIG["namespace"]):
            logger.info(f"Successfully uploaded {file_path} to Pinecone.")
               help="Process all documents in the target folder.",
            # Enhanced logging in verbose mode
            if logging.getLogger().level == logging.DEBUG:"--upload", type=str, help="Upload a single file to Pinecone.")
                logger.debug(f"File details for {file_name}:")ent(
                if file_hash:
                    logger.debug(f"  - Hash: {file_hash}")
                logger.debug(f"  - Created: {datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')}")   help="Run in dry run mode (no actual uploads).",
                logger.debug(f"  - Modified: {datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            
            return Trueche",
        else:
            logger.error(f"Failed to upload {file_path} to Pinecone.")   help="When used with --dry-run, updates the processed files cache as if files were processed.",
            return False
            ent(
    except Exception as e:rbose",
        logger.error(f"Failed to initialize Pinecone client: {e}")
        return False
   help="Enable verbose debug logging.",

def main():    args = parser.parse_args()
    parser = argparse.ArgumentParser(
        description="Manual actions for document processing." on verbosity
    )    setup_logging(args.verbose)
    parser.add_argument(
        "--process",d flags to sys.argv to make them accessible in the process_documents function
        action="store_true",
        help="Process all documents in the target folder.",
    )
    parser.add_argument("--upload", type=str, help="Upload a single file to Pinecone.")  and "--dry-run-update-cache" not in sys.argv
    parser.add_argument(
        "--dry-run",        sys.argv.append("--dry-run-update-cache")
        action="store_true",
        help="Run in dry run mode (no actual uploads).",t operation mode
    )
    parser.add_argument( RUN'}")
        "--dry-run-update-cache",run_update_cache}")
        action="store_true",        logger.debug(f"Command line arguments: {sys.argv}")
        help="When used with --dry-run, updates the processed files cache as if files were processed.",
    )
    parser.add_argument(run else ''}Processing all documents...")
        "--verbose",ents(dry_run=args.dry_run)
        "-v",
        action="store_true",
        help="Enable verbose debug logging.",pload_single_file(args.upload, dry_run=args.dry_run)
    )
    args = parser.parse_args()r(f"File not found: {args.upload}")
   sys.exit(1)
    # Setup logging first based on verbosity
    setup_logging(args.verbose)        parser.print_help()

    # Add flags to sys.argv to make them accessible in the process_documents function
    if (_ == "__main__":
        args.dry_run    main()



























    main()if __name__ == "__main__":        parser.print_help()    else:            sys.exit(1)            logger.error(f"File not found: {args.upload}")        else:            upload_single_file(args.upload, dry_run=args.dry_run)        if os.path.exists(args.upload):    elif args.upload:        process_documents(dry_run=args.dry_run)        logger.info(f"{'DRY RUN: ' if args.dry_run else ''}Processing all documents...")    if args.process:        logger.debug(f"Command line arguments: {sys.argv}")        logger.debug(f"Cache updates in dry run: {args.dry_run_update_cache}")        logger.debug(f"Operation mode: {'DRY RUN' if args.dry_run else 'ACTUAL RUN'}")    if args.verbose:    # Log the current operation mode        sys.argv.append("--dry-run-update-cache")    ):        and "--dry-run-update-cache" not in sys.argv        and args.dry_run_update_cache