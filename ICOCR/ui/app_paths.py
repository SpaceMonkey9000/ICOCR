"""Application-folder paths and the default package classifier model."""
from pathlib import Path


# The application folder (qt_window.py lives here; this module is in ui/).
APP_ROOT = Path(__file__).resolve().parent.parent
APP_MODELS = APP_ROOT / 'models'
PACKAGE_MODEL_NAME = 'package_classifier.onnx'


def default_package_model(models_directory):
    """The package classifier in the Models folder, else the copy shipped with ICOCR."""
    chosen = Path(models_directory) / PACKAGE_MODEL_NAME
    bundled = APP_MODELS / PACKAGE_MODEL_NAME
    return chosen if chosen.is_file() or not bundled.is_file() else bundled
