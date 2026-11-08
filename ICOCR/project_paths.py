"""Installation paths and the single shared DATA folder."""
from pathlib import Path
from shared_data import data_directory as shared_directory
ROOT = Path(__file__).resolve().parent

def data_directory(environ=None):
    return shared_directory(ROOT, environ)

DATA = data_directory()
VALIDATION = ROOT / 'validation'
SAMPLE_IMAGE = VALIDATION / 'images' / 'S20260928_0001(1).jpg'
