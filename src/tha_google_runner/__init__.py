"""tha-google-runner: typed wrapper for Google Sheets, Docs, Drive, Slides, and Gmail."""

from importlib.metadata import version

from tha_google_runner.docs import ThaDocs
from tha_google_runner.drive import ThaDrive
from tha_google_runner.errors import GoogleError, GoogleHttpError
from tha_google_runner.gmail import ThaGmail
from tha_google_runner.sheets import ThaSheets
from tha_google_runner.slides import ThaSlides

__version__ = version("tha-google-runner")
__all__ = [
    "GoogleError",
    "GoogleHttpError",
    "ThaDocs",
    "ThaDrive",
    "ThaGmail",
    "ThaSheets",
    "ThaSlides",
]
