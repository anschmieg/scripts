#!/bin/zsh

# Function to display usage
function usage() {
    echo "Usage: f [-d|-f|-e] -p /parent/path/to/search [query]"
    echo "  -d: search for directories only"
    echo "  -f: search for files only"
    echo "  -e: search for an exact match"
    echo "  -p: specify the parent path to search (default: current directory)"
    echo "  query: optional search query for fzf"
    echo "  -h, --help: display this help message"
    exit 1
}

# Default values
search_type=""
parent_path="."
exact_match=false

# Parse command line options
while getopts "dfep:h" opt; do
    case ${opt} in
        d) search_type="d" ;;
        f) search_type="f" ;;
        e) exact_match=true ;;
        p) parent_path="${OPTARG}" ;;
        h) usage ;;
        *) usage ;;
    esac
done
shift $((OPTIND -1))

# Set the search query if provided
search_query="$1"

# Set the find command based on the search type
case "${search_type}" in
    d) find_cmd="find ${parent_path} -type d" ;;
    f) find_cmd="find ${parent_path} -type f" ;;
    *) find_cmd="find ${parent_path}" ;;
esac

# Modify the find command if exact match is required
if [ "${exact_match}" = true ]; then
    find_cmd="${find_cmd} -name \"*${search_query}*\""
fi

# Run the find command with fzf and the search query
eval "${find_cmd}" | fzf --query "${search_query}"
