# database_manager.py

import json
from config import DB_FILE

def load_database():
    """Memuat database dari file JSON. Jika tidak ada, kembalikan dict kosong."""
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Memulai dengan database multi-user yang kosong
        return {}

def save_database(data):
    """Menyimpan data (dictionary) ke dalam file JSON."""
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)