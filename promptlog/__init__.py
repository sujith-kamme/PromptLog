from importlib.metadata import PackageNotFoundError, version

from promptlog.config import init
from promptlog.tracker import log_prompt, track

__all__ = ["init", "track", "log_prompt"]

try:
    __version__ = version("prompt-log")
except PackageNotFoundError:
    __version__ = "0.1.0"
