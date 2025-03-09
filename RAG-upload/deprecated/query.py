import argparse
import os

import dotenv
from pinecone import Pinecone


def main(query_text, top_k=5, namespace=None, api_key=None, index_host=None):
    # Default to env API key if not provided
    dotenv.load_dotenv()
    if api_key is None:
        api_key = os.getenv("PINECONE_API_KEY")

    # Default to this DB host if not provided
    if index_host is None:
        index_host = "https://personal-files-9vwoy12.svc.aped-4627-b74a.pinecone.io"

    # Initialize the Pinecone client
    pc = Pinecone(api_key=api_key)

    # To get the unique host for an index, see https://docs.pinecone.io/guides/data/target-an-index
    index = pc.Index(host=index_host)

    # Perform the query with the correct parameter structure
    response = index.search_records(
        namespace=namespace, query={"inputs": {"text": query_text}, "top_k": top_k}
    )

    # Print the results
    for match in response["result"]["hits"]:
        print(
            f"ID: {match['_id']}, Score: {match['_score']}, Metadata: {match['fields']}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Query a Pinecone database with integrated embedding."
    )
    parser.add_argument("query_text", help="The search query text")

    # Make top_k both a positional and optional argument
    parser.add_argument(
        "top_k_pos", nargs="?", type=int, default=5, help=argparse.SUPPRESS
    )  # Hide from help but still accept positional

    parser.add_argument(
        "-k",
        "--top_k",
        type=int,
        dest="top_k",
        help="Number of top results to return (default: 5)",
    )

    parser.add_argument(
        "-a",
        "--api_key",
        help="Pinecone API key (default: uses PINECONE_API_KEY from environment)",
    )

    parser.add_argument(
        "-i",
        "--index_host",
        help="Pinecone index host (defaults to the personal index)",
    )

    parser.add_argument(
        "-n", "--namespace", help="Namespace to query (default: all namespaces)"
    )

    args = parser.parse_args()

    # Use the flag version if provided, otherwise use positional
    top_k = args.top_k if args.top_k is not None else args.top_k_pos

    main(args.query_text, top_k, args.namespace, args.api_key, args.index_host)
