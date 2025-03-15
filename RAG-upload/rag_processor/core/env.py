"""
Environment variable handling functions
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Define project root once at module level to avoid repeated calculations
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_environment_variables(override=False):
    """
    Load environment variables from .env file

    Args:
        override: If True, override existing environment variables

    Returns:
        bool: True if .env was found and loaded, False otherwise
    """
    dotenv_path = PROJECT_ROOT / ".env"

    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=override)
        return True
    else:
        return False


def get_env_variable(name, default=None):
    """Get an environment variable, with optional default"""
    return os.environ.get(name, default)


def expand_path(path):
    """Expand environment variables and ~ in path"""
    if not path:
        return None
    return os.path.expanduser(os.path.expandvars(path))


def get_project_root():
    """Get project root directory"""
    return PROJECT_ROOT
