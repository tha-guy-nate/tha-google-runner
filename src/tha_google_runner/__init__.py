"""tha-google-runner: typed gspread wrapper for Google Sheets."""

from tha_google_runner.errors import GoogleError
from tha_google_runner.sheets import ThaSheets

__version__ = "0.1.0"
__all__ = [
    "GoogleError",
    "ThaSheets",
]
