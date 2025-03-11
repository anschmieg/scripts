"""
Environment variable handling functions
"""

import os
from pathlib import Path

from dotenv import load_dotenv


def load_environment_variables():
    """Load environment variables from .env file"""
    # Find project root (where .env should be located)
    project_root = Path(__file__).resolve().parent.parent.parent
    dotenv_path = project_root / ".env"

    if dotenv_path.exists():
        load_dotenv(dotenv_path)
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
    return Path(__file__).resolve().parent.parent.parent
