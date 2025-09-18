import os
from dotenv import load_dotenv

# Baris ini akan mencari file .env di folder proyek dan memuatnya.
load_dotenv()


# --- Konfigurasi Awal & Keamanan ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Pemeriksaan penting: hentikan bot jika token tidak ada.
if not TOKEN:
    raise ValueError("KRITIS: Variabel TELEGRAM_TOKEN tidak ditemukan. Pastikan file .env ada dan sudah benar, atau variabel lingkungan di server sudah diatur.")


# --- Konfigurasi Penyimpanan Permanen ---
DATA_DIR = "/var/data"
DB_FILE = os.path.join(DATA_DIR, "file_database.json")

os.makedirs(DATA_DIR, exist_ok=True)


COOLDOWN_SECONDS = 1
FILES_PER_PAGE = 5

