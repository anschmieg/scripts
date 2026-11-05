#!/usr/bin/env python3
import argparse
import json
import os
import pickle
import subprocess
import sys

import numpy as np
from scipy.spatial.distance import cosine

# NOTE: Ensure 'sentence-transformers' and 'scipy' are installed: pip install sentence-transformers numpy scipy
from sentence_transformers import SentenceTransformer

# --- Configuration (Centralized Constants) ---
TEMPLATE_FILE = "templates.json"
VECTOR_CACHE_FILE = "templates_vectors.pkl"
MODEL_NAME = "all-MiniLM-L6-v2"
MIN_SEMANTIC_SCORE = 0.5  # Cosine Similarity score threshold (50%)

# --- Global Cache for Model ---
# We use a dictionary to hold the SentenceTransformer instance after it's loaded.
# This prevents redundant loading *if* the script were to call it multiple times
# (though it only calls it once per run in the current design).
GLOBAL_MODEL_CACHE = {}


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


def get_model(model_name):
    """Loads and caches the Sentence Transformer model."""
    if "model_instance" not in GLOBAL_MODEL_CACHE:
        print(
            f"[{Colors.YELLOW}Loading Semantic Model...{Colors.END}] This may take a few seconds."
        )
        try:
            # This is the heavy operation that causes the startup delay.
            GLOBAL_MODEL_CACHE["model_instance"] = SentenceTransformer(model_name)
        except Exception as e:
            print(
                f"{Colors.RED}Fatal Error: Could not initialize model '{model_name}'.{Colors.END}"
            )
            print(
                f"Ensure all dependencies (torch, transformers) are installed. Details: {e}"
            )
            sys.exit(1)
    return GLOBAL_MODEL_CACHE["model_instance"]


def load_vector_data():
    """Loads templates and vector cache for search mode."""
    templates = load_template_file()

    try:
        with open(VECTOR_CACHE_FILE, "rb") as f:
            cache = pickle.load(f)

        # Load the model, leveraging the new caching function
        model = get_model(cache["model"])

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
        print(f"{Colors.RED}Error loading semantic cache: {e}{Colors.END}")
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

    # Get model instance (heavy load happens here)
    model = get_model(MODEL_NAME)

    print(f"Model loaded. Generating {len(corpus)} embeddings...")

    try:
        # STEP 2: Generate Embeddings
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
            f"You can now run searches: {Colors.YELLOW}python template_wizard_cli.py academic report{Colors.END}"
        )
        print("=" * 70)

    except Exception as e:
        print(f"\n{Colors.RED} Error during embedding: {e}{Colors.END}")
        print("Check template data integrity.")


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


def interactive_fzf_selector(matches, prompt):
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

    # We use the prompt string passed in via the parsed arguments
    prompt = args.prompt

    # Load data, model, and vectors
    templates, template_names, template_vectors, model = load_vector_data()

    # 1. Semantic Matching
    matches = semantic_search(
        prompt, templates, template_names, template_vectors, model
    )

    if matches:
        print(
            f"{Colors.GREEN}Found {len(matches)} highly relevant template(s) above {MIN_SEMANTIC_SCORE * 100}% relevance.{Colors.END}"
        )

        # 2. Interactive Selection (FZF)
        selected_template = interactive_fzf_selector(matches, prompt)

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


class CustomHelpFormatter(argparse.RawTextHelpFormatter):
    """Custom formatter for a cleaner, tabular help output."""

    def _get_description(self):
        return f"{Colors.BOLD}Typst/Quarto Template Wizard CLI Tool{Colors.END}"

    def format_help(self):
        help_message = super().format_help()

        # Custom tabular usage example layout in the epilog
        custom_epilog = f"""
{Colors.BOLD}Usage & Commands:{Colors.END}
{Colors.BLUE}{"  Action":<15} {"Command":<25} {"Description"}{Colors.END}
{"-" * 80}
{Colors.GREEN}{"  Setup":<15}{Colors.END} {Colors.YELLOW}setup{Colors.END:<25} Generates the semantic vector cache (run once).
{Colors.GREEN}{"  Search (Default):":<15}{Colors.END} {Colors.YELLOW}[search] <query...>{Colors.END:<25} Performs semantic search and launches FZF TUI.
{"-" * 80}
{Colors.BOLD}Search Examples:{Colors.END}
  {Colors.YELLOW}python fuzzy_matcher.py professional CV for job{Colors.END}
  {Colors.YELLOW}python fuzzy_matcher.py search academic thesis in APA style{Colors.END}

{Colors.BOLD}Configuration Files:{Colors.END}
  {Colors.BLUE}{TEMPLATE_FILE:<20}{Colors.END} - Source file containing all template names and descriptions (JSON).
  {Colors.BLUE}{VECTOR_CACHE_FILE:<20}{Colors.END} - Local cache of semantic vectors (generated via setup).
        """

        script_name = os.path.basename(sys.argv[0])
        # Note: argparser automatically adds 'usage: scriptname [-h]'
        # We replace the generic line and then add the epilog
        help_message = help_message.split("\n\n")[0]  # keep only the 'usage' line

        help_message += custom_epilog.replace("%(prog)s", script_name)

        return help_message


def main():
    """Main function to handle CLI arguments."""

    # 1. Check for standard help flags
    if any(arg in sys.argv for arg in ["-h", "--help"]):
        parser_help = argparse.ArgumentParser(formatter_class=CustomHelpFormatter)
        parser_help.print_help()
        sys.exit(0)

    # 2. Check for setup command
    cli_args = sys.argv[1:]
    if cli_args and cli_args[0].lower() == "setup":
        parser_setup = argparse.ArgumentParser(
            description=f"{Colors.BOLD}Typst/Quarto Template Wizard CLI Tool - Setup{Colors.END}",
            formatter_class=CustomHelpFormatter,
            add_help=False,
        )
        parser_setup.add_argument("command", help=argparse.SUPPRESS)
        args = parser_setup.parse_args([cli_args[0]])
        setup_vectors(args)
        return

    # 3. Handle SEARCH (Default mode or explicitly called with 'search')

    # We use REMAINDER to capture all subsequent words for the query
    parser_search = argparse.ArgumentParser(add_help=False)
    parser_search.add_argument(
        "query_args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS
    )
    args = parser_search.parse_args()
    search_terms = args.query_args

    # --- Construct the prompt string ---

    # If the first argument was 'search', strip it
    if search_terms and search_terms[0].lower() == "search":
        search_terms = search_terms[1:]

    prompt = " ".join(search_terms).strip()

    if not prompt:
        # If no arguments were provided, print help text and exit
        parser_help = argparse.ArgumentParser(formatter_class=CustomHelpFormatter)
        parser_help.print_help()
        sys.exit(0)

    # 4. Run the search logic
    search_args = argparse.Namespace(prompt=prompt)
    run_search(search_args)


if __name__ == "__main__":
    main()
