"""sw-metadata-bot: RSMetaCheck bot for pushing issues with existing repository metadata."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("sw-metadata-bot")
except PackageNotFoundError:
    # Package is not installed
    __version__ = "unknown"

__all__ = ["__version__"]