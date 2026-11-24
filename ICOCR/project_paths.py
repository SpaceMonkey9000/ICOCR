"""Installation paths and the single shared DATA folder."""
from pathlib import Path
from shared_data import data_directory as shared_directory
ROOT = Path(__file__).resolve().parent

def data_directory(environ=None):
    return shared_directory(ROOT, environ)

# ICLENS_DATA, else the folder saved in Settings (shared with ICDB), else the default
# location; see shared_data.data_directory.
DATA = data_directory()
VALIDATION = ROOT / 'validation'
SAMPLE_IMAGE = VALIDATION / 'images' / 'S20260928_0001(1).jpg'
