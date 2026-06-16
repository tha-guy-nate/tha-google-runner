"""tha-google-runner: typed wrapper for Google Sheets and Docs."""

from tha_google_runner.docs import ThaDocs
from tha_google_runner.errors import GoogleError
from tha_google_runner.sheets import ThaSheets

__version__ = "0.1.2"
__all__ = [
    "GoogleError",
    "ThaDocs",
    "ThaSheets",
]
