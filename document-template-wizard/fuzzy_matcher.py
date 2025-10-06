import argparse
import json
import pickle
import subprocess
import sys

import numpy as np
from scipy.spatial.distance import cosine

# NOTE: Ensure 'sentence-transformers' is installed: pip install sentence-transformers
from sentence_transformers import SentenceTransformer

# --- Configuration (Centralized Constants) ---
TEMPLATE_FILE = "templates.json"
VECTOR_CACHE_FILE = "templates_vectors.pkl"
MODEL_NAME = "all-MiniLM-L6-v2"
MIN_SEMANTIC_SCORE = 0.5  # Cosine Similarity score threshold (50%)


# --- ANSI Escape Codes for Terminal Colors and Formatting ---
class Colors:
    """ANSI color codes."""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RED = "\033[91m"
    END = "\033[0m"
    BOLD = "\033[1m"


# --- Utility Functions ---


def load_template_file():
    """Loads templates from the JSON file."""
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(
            f"{Colors.RED}Error: Template catalog '{TEMPLATE_FILE}' not found.{Colors.END}"
        )
        print(
            f"Run the setup command first: {Colors.YELLOW}python template_wizard_cli.py setup{Colors.END}"
        )
        sys.exit(1)
    except json.JSONDecodeError:
        print(
            f"{Colors.RED}Error: Failed to parse '{TEMPLATE_FILE}'. Check JSON formatting.{Colors.END}"
        )
        sys.exit(1)


def load_template_vectors():
    """Loads templates and vector cache for search mode."""
    templates = load_template_file()

    try:
        with open(VECTOR_CACHE_FILE, "rb") as f:
            cache = pickle.load(f)

        # Load the model required for the vectors (downloads if not cached globally)
        model = SentenceTransformer(cache["model"])

        return templates, cache["names"], cache["vectors"], model

    except FileNotFoundError:
        print(
            f"{Colors.RED}Error: Vector cache '{VECTOR_CACHE_FILE}' not found.{Colors.END}"
        )
        print(
            f"Please run the setup command first: {Colors.YELLOW}python template_wizard_cli.py setup{Colors.END}"
        )
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}Error loading semantic model/cache: {e}{Colors.END}")
        sys.exit(1)


# --- Subcommand 1: Setup Logic ---


def setup_vectors(args):
    """Generates and caches the semantic vectors for the template descriptions."""
    print("--- 🛠️ TEMPLATE WIZARD SETUP: Generating Semantic Vectors ---")

    # STEP 1: Load Template Data
    templates = load_template_file()
    if not templates:
        print(
            f"{Colors.YELLOW}No templates found in JSON. Nothing to process.{Colors.END}"
        )
        return

    # Create the corpus: combining name and description is best for semantic search
    corpus = [f"{t['name']}. {t['description']}" for t in templates]
    template_names = [t["name"] for t in templates]

    print(
        f"Loaded {len(templates)} templates. Initializing Sentence Transformer Model ('{MODEL_NAME}')..."
    )

    try:
        # STEP 2: Load Model and Generate Embeddings
        model = SentenceTransformer(MODEL_NAME)

        print(f"Model loaded. Generating {len(corpus)} embeddings...")

        # Encode the corpus texts into high-dimensional vectors
        corpus_embeddings = model.encode(corpus, convert_to_tensor=False)

        # STEP 3: Cache Vectors to Disk
        with open(VECTOR_CACHE_FILE, "wb") as f:
            pickle.dump(
                {
                    "names": template_names,
                    "vectors": corpus_embeddings,
                    "model": MODEL_NAME,
                },
                f,
            )

        print("\n" + "=" * 70)
        print(
            f"{Colors.GREEN}{Colors.BOLD}✅ Setup Complete! Vector cache saved to '{VECTOR_CACHE_FILE}'.{Colors.END}{Colors.END}"
        )
        print(
            f"You can now run searches: {Colors.YELLOW}python template_wizard_cli.py search 'academic report'{Colors.END}"
        )
        print("=" * 70)

    except Exception as e:
        print(f"\n{Colors.RED} Error during embedding or model load: {e}{Colors.END}")
        print("Ensure 'sentence-transformers' and 'torch' are installed correctly.")


# --- Subcommand 2: Search Logic ---


def semantic_search(prompt, templates, template_names, template_vectors, model):
    """
    Performs semantic search using cached vectors and cosine similarity.
    Returns ranked matches as full template data.
    """
    print(f"\n{Colors.BLUE}--- Semantic Search: Encoding Query ---{Colors.END}")

    # 1. Encode the user's query
    query_vector = model.encode([prompt], convert_to_tensor=False)[0]

    # 2. Calculate cosine similarity between the query vector and all template vectors
    # We transpose the vectors matrix for efficient calculation
    template_vectors_matrix = np.array(template_vectors)

    # Calculate scores (Cosine Distance is 1 - Cosine Similarity)
    # The cosine function from scipy takes two arrays and returns the distance.
    distances = [
        cosine(query_vector, template_vectors_matrix[i])
        for i in range(template_vectors_matrix.shape[0])
    ]
    scores = 1 - np.array(distances)

    # 3. Filter and structure results
    results = []
    for i, score in enumerate(scores):
        if score >= MIN_SEMANTIC_SCORE:
            template_name = template_names[i]

            # Find the full template object using the name
            # We use next() for quick lookup based on name
            full_template = next(
                (t for t in templates if t["name"] == template_name), None
            )

            if full_template:
                results.append(
                    {
                        "score": int(score * 100),  # Scale to 0-100 for display
                        "system": full_template["system"],
                        "name": full_template["name"],
                        "description": full_template["description"],
                    }
                )

    # Sort and return
    return sorted(results, key=lambda x: x["score"], reverse=True)


def selection_menu(matches, prompt):
    """
    Uses the fzf utility to provide a highly interactive, searchable selection TUI.
    """
    if not matches:
        return None

    # 1. Format data for fzf input (Tab-separated values)
    fzf_input = []
    # Header line must be included first for fzf to use it
    fzf_input.append(
        f"{Colors.BOLD}{'SCORE':<5} | {'SYSTEM':<7} | {'TEMPLATE NAME':<40} | DESCRIPTION{Colors.END}"
    )

    for item in matches:
        # Ensure description is clean and formatted for the fzf column
        desc = item["description"].replace("\n", " ")
        line = (
            f"{Colors.YELLOW}{item['score']:<5}{Colors.END} | "
            f"{item['system'].capitalize():<7} | "
            f"{item['name']:<40} | "
            f"{desc}"
        )
        fzf_input.append(line)

    # 2. Define the fzf command and arguments
    # We use a placeholder for the color scheme to ensure portability
    fzf_command = [
        "fzf",
        "--layout=reverse",
        "--header",
        f"Select template for: {prompt} | (Score > {MIN_SEMANTIC_SCORE * 100}%)",
        "--ansi",
        "--delimiter",
        "|",
        "--with-nth",
        "1..3",  # Show Score, System, and Name in the main interface
        "--header-lines",
        "1",  # Treat the first line of output as a header
        "--prompt",
        "Template > ",
    ]

    # 3. Execute fzf and capture output
    try:
        process = subprocess.run(
            fzf_command,
            input="\n".join(fzf_input).encode("utf-8"),
            capture_output=True,
            check=False,
        )

        selected_line = process.stdout.decode("utf-8").strip()

        if not selected_line:
            return None

        # 4. Parse the selected line to get the template name
        # The selected line contains the full '|' separated string. We extract the NAME field (column 3)
        parts = selected_line.split("|")

        # The third part (index 2) is the Name field
        # We need to strip the ANSI codes and whitespace
        name_with_ansi = parts[2].strip()

        # Simple regex to remove ANSI codes if necessary (fzf generally handles this well)
        # However, since the name is unique, we find the match based on the name key.

        # Extract the clean name by stripping color codes and spaces
        selected_name = (
            name_with_ansi.replace(Colors.GREEN, "")
            .replace(Colors.YELLOW, "")
            .replace(Colors.END, "")
            .strip()
        )

        # Find the full original template object using the unique name
        return next(item for item in matches if item["name"] == selected_name)

    except FileNotFoundError:
        print(f"{Colors.RED}Error: 'fzf' command not found.{Colors.END}")
        print(
            f"Please install fzf (e.g., {Colors.YELLOW}brew install fzf{Colors.END})."
        )
        return None


def initialize_template(template_data):
    """Initializes the document using the correct CLI tool (typst or quarto)."""
    system = template_data["system"]
    template_name = template_data["name"]

    # Create a clean directory name from the template name
    if system == "typst":
        base_name = template_name.replace("@preview/", "").replace("-", "_")
    else:  # Quarto (GitHub path)
        base_name = template_name.split("/")[-1]

    output_dir = f"{base_name}_project"

    # --- Determine the command based on the system ---
    if system == "typst":
        cmd = ["typst", "init", template_name, output_dir]
    elif system == "quarto":
        cmd = ["quarto", "use", "template", template_name, output_dir]
    else:
        print(
            f"{Colors.RED}Error: Unknown system '{system}'. Initialization aborted.{Colors.END}"
        )
        return

    print(f"\n{Colors.BLUE}✨ Initializing document using {system}...{Colors.END}")
    print(f"{Colors.YELLOW}Command: {' '.join(cmd)}{Colors.END}")

    try:
        subprocess.run(cmd, check=True)
        print("\n" + "=" * 70)
        print(
            f"{Colors.GREEN}{Colors.BOLD}✅ Success! Project '{output_dir}' created.{Colors.END}{Colors.END}"
        )
        print(
            f"To start working in VS Code: {Colors.YELLOW}code ./{output_dir}{Colors.END}"
        )
        print("=" * 70)
    except subprocess.CalledProcessError as e:
        print(f"\n{Colors.RED}❌ Initialization failed (CLI error).{Colors.END}")
        print(f"Ensure that '{system}' is installed and accessible in your PATH.")
        print(f"Error details: {e}")
    except FileNotFoundError:
        print(f"\n{Colors.RED}❌ Initialization failed.{Colors.END}")
        print(
            f"The command '{system}' was not found. Please install the necessary CLI tool."
        )


def run_search(args):
    """Entry point for the 'search' subcommand."""

    if not args.prompt:
        print(f"{Colors.RED}Error: A search prompt is required.{Colors.END}")
        print(
            f"Usage: {Colors.YELLOW}python template_wizard_cli.py search 'thesis report'{Colors.END}"
        )
        return

    # Load data, model, and vectors
    templates, template_names, template_vectors, model = load_template_vectors()

    # 1. Semantic Matching
    matches = semantic_search(
        args.prompt, templates, template_names, template_vectors, model
    )

    if matches:
        print(
            f"{Colors.GREEN}Found {len(matches)} highly relevant template(s) above {MIN_SEMANTIC_SCORE * 100}% relevance.{Colors.END}"
        )

        # 2. Interactive Selection (FZF)
        selected_template = selection_menu(matches, args.prompt)

        if selected_template:
            initialize_template(selected_template)
        else:
            print(f"{Colors.YELLOW}Template selection cancelled.{Colors.END}")

    else:
        print(
            f"\n{Colors.RED}❌ Semantic search failed to find a template above the score threshold ({MIN_SEMANTIC_SCORE * 100}%).{Colors.END}"
        )
        print("Try a more detailed query (e.g., 'academic thesis paper in APA style').")


# --- Main Argument Parser ---


def main():
    """Main function to handle CLI arguments."""
    parser = argparse.ArgumentParser(
        description=f"{Colors.BOLD}Typst/Quarto Template Wizard CLI Tool{Colors.END}",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Usage Examples:
  # 1. Setup (Run once after installing new templates.json):
  python template_wizard_cli.py setup
  
  # 2. Search for a template:
  python template_wizard_cli.py search "professional CV for job application"
  
  # 3. Search for a specific academic paper format:
  python template_wizard_cli.py search "IEEE conference paper"
        """,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand for SETUP
    parser_setup = subparsers.add_parser(
        "setup",
        help=f"Generates semantic vectors from {TEMPLATE_FILE} and caches them to {VECTOR_CACHE_FILE}.",
    )
    parser_setup.set_defaults(func=setup_vectors)

    # Subcommand for SEARCH
    parser_search = subparsers.add_parser(
        "search",
        help="Performs semantic search using the cached vectors and launches an interactive FZF selector.",
    )
    parser_search.add_argument(
        "prompt",
        type=str,
        help="The natural language query describing the desired document.",
    )
    parser_search.set_defaults(func=run_search)

    # Execute the appropriate function
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
