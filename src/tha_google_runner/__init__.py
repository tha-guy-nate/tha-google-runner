"""tha-google-runner: typed wrapper for Google Sheets, Docs, and Drive."""

from tha_google_runner.docs import ThaDocs
from tha_google_runner.drive import ThaDrive
from tha_google_runner.errors import GoogleError
from tha_google_runner.gmail import ThaGmail
from tha_google_runner.sheets import ThaSheets
from tha_google_runner.slides import ThaSlides

__version__ = "0.1.3"
__all__ = [
    "GoogleError",
    "ThaDocs",
    "ThaDrive",
    "ThaGmail",
    "ThaSheets",
    "ThaSlides",
]
