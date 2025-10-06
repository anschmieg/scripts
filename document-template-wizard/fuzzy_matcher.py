import json
import subprocess
import sys

from fuzzywuzzy import process

# --- Configuration ---
TEMPLATE_FILE = "templates.json"
FUZZY_THRESHOLD = 75  # Minimum similarity score (out of 100) for a "good" match


def load_local_templates():
    """Loads the curated template catalog from the local JSON file."""
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Template catalog '{TEMPLATE_FILE}' not found.")
        print("Please ensure the file exists in the current directory.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Failed to parse '{TEMPLATE_FILE}'. Check JSON formatting.")
        sys.exit(1)


def fuzzy_match_template(prompt, templates):
    """
    Performs fuzzy matching on both template names and descriptions.
    Returns the top matches above the threshold.
    """
    # Create a list of names/descriptions to search against, using the full object
    search_targets = {}
    for t in templates:
        # Use the name + description as a single search target for better coverage
        search_target = f"{t['name']} - {t['description']}"
        search_targets[search_target] = t

    # 1. Get best matches based on the composite string
    best_matches = process.extractBests(
        prompt,
        list(search_targets.keys()),
        score_cutoff=FUZZY_THRESHOLD,
        limit=5,  # Look for top 5 relevant matches
    )

    # 2. Map matches back to the original structured dictionary items
    results = []
    seen_names = set()
    for match_string, score in best_matches:
        original_template = search_targets[match_string]

        # Use the 'name' (identifier) as the unique key
        if original_template["name"] not in seen_names:
            results.append(
                {
                    "score": score,
                    "system": original_template["system"],
                    "name": original_template["name"],
                    "description": original_template["description"],
                }
            )
            seen_names.add(original_template["name"])

    return sorted(results, key=lambda x: x["score"], reverse=True)


def call_llm_fallback(prompt, templates):
    """
    Simulates the LLM fallback step by generating a prompt for the LLM.

    In a real application (e.g., using Gemini API or Ollama), this function
    would execute an external API call and return the selected template name.
    """
    print("\n--- LLM FALLBACK: Generating Prompt ---")

    # Generate the list of available templates for the LLM
    template_list = "\n".join(
        [
            f"- {t['name']} (System: {t['system']}, Purpose: {t['description']})"
            for t in templates
        ]
    )

    llm_prompt = f"""
    The user needs a document template based on the following query: '{prompt}'.
    
    Select the single most suitable template identifier (the 'name' field) 
    from the list below. If no template is suitable, respond ONLY with 'NONE'.

    Available Templates:
    {template_list}

    Your final response MUST be ONLY the template identifier (the 'name') or NONE.
    """

    print(
        "\n[NOTE: In a live environment, the following prompt would be sent to the LLM:]"
    )
    print("-" * 50)
    print(llm_prompt)
    print("-" * 50)

    # --- PLACEHOLDER FOR LLM RESPONSE ---
    # For demonstration, we simulate a 'NONE' response to proceed to manual selection.
    # Replace this section with your actual LLM integration (e.g., using the Gemini API).

    print("No actual LLM call was executed (placeholder response is 'NONE').")
    return "NONE"


def initialize_template(template_data):
    """Initializes the document using the correct CLI tool."""
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
        # Typst init command: typst init @preview/template_name output_dir
        cmd = ["typst", "init", template_name, output_dir]
    elif system == "quarto":
        # Quarto use template command: quarto use template github/path output_dir
        # Note: quarto use template automatically fetches the latest version
        cmd = ["quarto", "use", "template", template_name, output_dir]
    else:
        print(f"Error: Unknown system '{system}'. Initialization aborted.")
        return

    print(f"\n✨ Initializing document using {system}...")
    print(f"Command: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
        print("\n" + "=" * 60)
        print(f"✅ Success! Project '{output_dir}' created.")
        print(f"To start working in VS Code: code ./{output_dir}")
        print("=" * 60)
    except subprocess.CalledProcessError as e:
        print("\n❌ Initialization failed (CLI error).")
        print(f"Ensure that '{system}' is installed and accessible in your PATH.")
        print(f"Error details: {e}")
    except FileNotFoundError:
        print("\n❌ Initialization failed.")
        print(
            f"The command '{system}' was not found. Please install the necessary CLI tool."
        )


# --- Main Execution ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python template_wizard.py <document description>")
        sys.exit(1)

    user_prompt = " ".join(sys.argv[1:]).strip()
    templates = load_local_templates()

    # 1. Fuzzy Match Check
    matches = fuzzy_match_template(user_prompt, templates)

    if matches:
        print(
            f"Found {len(matches)} highly relevant match(es) for '{user_prompt}' (Score > {FUZZY_THRESHOLD}):"
        )

        # Display the best match and prompt for confirmation
        best_match = matches[0]

        print("\n" + "-" * 60)
        print(f"BEST MATCH (Score {best_match['score']}%):")
        print(f"System: {best_match['system'].capitalize()}")
        print(f"Template Name: {best_match['name']}")
        print(f"Description: {best_match['description']}")
        print("-" * 60)

        # Simple confirmation loop
        selection = (
            input(f"Use '{best_match['name']}'? (Y/n/l for list): ").strip().lower()
        )

        if selection == "y" or selection == "":
            initialize_template(best_match)
        elif selection == "l":
            print("\n--- Detailed Template List ---")
            for i, item in enumerate(matches, 1):
                print(
                    f"({item['score']}%) [{item['system'].capitalize()}] {item['name']}: {item['description']}"
                )
            print(
                "\nIf you want to use one, run the wizard again with a more specific prompt."
            )
        else:
            print("Template selection aborted.")

    else:
        # 2. LLM Fallback (Currently simulates a failed match)
        print(f"\nNo strong fuzzy match found for '{user_prompt}'.")
        llm_suggestion = call_llm_fallback(user_prompt, templates)

        if llm_suggestion and llm_suggestion != "NONE":
            # This branch would require fetching the full template data object
            # based on the LLM's suggested name.
            print(f"LLM suggested '{llm_suggestion}', attempting initialization...")
            # For simplicity, if LLM returns a name, we'd proceed assuming the script can find its metadata
            pass
        else:
            print(
                "\n❌ Failed to find a suitable template automatically. Please try a different query or manually choose from the catalog."
            )
