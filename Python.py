import logging
import json # Library untuk bekerja dengan file JSON
import time
import functools
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Konfigurasi Awal ---
TOKEN = "7574205111:AAFrGMET2J0FZTk7_LDprEnGzrE2i6v-Nnw"
DB_FILE = "file_database.json" # Nama file untuk database kita

# --- KONFIGURASI ANTI-SPAM & ANTI-BRUTE FORCE ---

# Cooldown umum (detik) antar perintah untuk semua pengguna
COOLDOWN_SECONDS = 3

# Batas percobaan gagal untuk /get sebelum diblokir sementara
GET_ATTEMPT_LIMIT = 5

# Jendela waktu (detik) untuk menghitung percobaan gagal /get
GET_ATTEMPT_WINDOW_SECONDS = 60

# Durasi blokir (detik) jika pengguna mencapai batas percobaan /get
BLOCK_DURATION_SECONDS = 300  # 5 menit

# --- "Database" Sederhana untuk Tracking Pengguna ---
# Menyimpan {user_id: timestamp_perintah_terakhir}
user_cooldowns = {}
# Menyimpan {user_id: [timestamp_gagal_1, timestamp_gagal_2]}
get_attempts = {}
# Menyimpan {user_id: timestamp_berakhirnya_blokir}
user_blocks = {}

# Logging untuk debugging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Fungsi untuk Mengelola Database JSON ---

def load_database():
    """Memuat database dari file JSON. Jika file tidak ada, kembalikan dictionary kosong."""
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {} # Jika file belum ada, mulai dengan database kosong
    except json.JSONDecodeError:
        return {} # Jika file rusak atau kosong, mulai baru untuk mencegah crash

def save_database(data):
    """Menyimpan data (dictionary) ke dalam file JSON."""
    with open(DB_FILE, 'w') as f:
        # indent=4 agar file JSON mudah dibaca manusia
        json.dump(data, f, indent=4)

# Memuat database saat bot pertama kali dijalankan
file_database = load_database()

# --- Fungsi untuk Fitur-fitur Bot ---

# Decorator untuk menerapkan cooldown umum
def rate_limit(func):
    @functools.wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        current_time = time.time()

        # Cek apakah pengguna ada di daftar cooldown
        if user_id in user_cooldowns:
            last_call_time = user_cooldowns[user_id]
            elapsed = current_time - last_call_time
            
            if elapsed < COOLDOWN_SECONDS:
                remaining = COOLDOWN_SECONDS - elapsed
                await update.message.reply_text(
                    f"⏳ Anda terlalu cepat! Silakan tunggu {remaining:.1f} detik lagi."
                )
                return
        
        # Update timestamp dan jalankan fungsi asli
        user_cooldowns[user_id] = current_time
        return await func(update, context, *args, **kwargs)
    return wrapped

# 1. Perintah /start
@rate_limit
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        f"Halo {user.mention_html()}!\n\nSaya adalah bot penyimpanan file pribadi Anda. "
        f"Kirimkan saya file untuk disimpan. Gunakan /info untuk melihat daftar file."
    )

# 2. Handler untuk Menerima dan Menyimpan File
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_attachment = None
    file_type = None
    original_filename = None

    if update.message.document:
        file_attachment = update.message.document
        file_type = "document"
        original_filename = file_attachment.file_name
    elif update.message.video:
        file_attachment = update.message.video
        file_type = "video"
        original_filename = file_attachment.file_name or f"video_{file_attachment.file_unique_id}.mp4"
    elif update.message.photo:
        file_attachment = update.message.photo[-1]
        file_type = "photo"
        original_filename = f"photo_{file_attachment.file_unique_id}.jpg"

    if file_attachment:
        if original_filename in file_database:
            await update.message.reply_text(
                f"⚠️ Gagal! File dengan nama '{original_filename}' sudah ada."
            )
            return

        file_database[original_filename] = {
            "file_id": file_attachment.file_id,
            "file_size": file_attachment.file_size,
            "file_type": file_type
        }
        
        # PERUBAHAN PENTING: Simpan ke file setiap kali ada file baru
        save_database(file_database)
        
        logger.info(f"File '{original_filename}' disimpan dari user {update.effective_user.username}")
        await update.message.reply_text(
            f"✅ Berhasil diunggah dan disimpan permanen!\nNama File: {original_filename}"
        )

# 3. Perintah /info
@rate_limit
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan daftar file yang tersimpan, dikelompokkan berdasarkan jenis file."""

    # Pesan jika database masih kosong
    if not file_database:
        await update.message.reply_html(
            "🗃️ <b>Penyimpanan Anda Masih Kosong</b>\n\n"
            "Kirim file apa saja untuk mulai menyimpannya di sini!"
        )
        return

    # Siapkan list untuk setiap kategori
    documents = []
    videos = []
    photos = []

    # Kelompokkan file berdasarkan tipenya
    for filename, details in file_database.items():
        file_type = details.get("file_type", "document") # Default ke document jika tipe tidak ada
        # Kita tambahkan backtick (`) agar mudah disalin pengguna
        formatted_name = f"<code>{filename}</code>"
        if file_type == "document":
            documents.append(formatted_name)
        elif file_type == "video":
            videos.append(formatted_name)
        elif file_type == "photo":
            photos.append(formatted_name)

    # --- Bangun pesan balasan ---
    message_text = "✨ <b>Daftar File Tersimpan Anda</b> ✨\n\n"
    has_content = False

    if documents:
        message_text += "<b>📁 Dokumen</b>\n" + "\n".join(sorted(documents)) + "\n\n"
        has_content = True
    if videos:
        message_text += "<b>🎥 Video</b>\n" + "\n".join(sorted(videos)) + "\n\n"
        has_content = True
    if photos:
        message_text += "<b>🖼️ Foto</b>\n" + "\n".join(sorted(photos)) + "\n\n"
        has_content = True

    if has_content:
        message_text += "💡 Tips: Gunakan <code>/get nama_file.ext</code> untuk mengambil file."
    else:
        # Fallback jika ada data tapi tidak ada yang cocok kategori (seharusnya tidak terjadi)
        message_text = "Penyimpanan Anda kosong."


    await update.message.reply_html(message_text)

# 4. Perintah /get
# GANTIKAN FUNGSI get_file LAMA ANDA DENGAN YANG INI
async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengirim file kembali ke pengguna dengan proteksi brute force."""
    user_id = update.effective_user.id
    current_time = time.time()

    # 1. Cek apakah pengguna sedang dalam masa blokir
    if user_id in user_blocks and current_time < user_blocks[user_id]:
        remaining_block = user_blocks[user_id] - current_time
        await update.message.reply_text(
            f"❌ Anda diblokir sementara karena terlalu banyak percobaan gagal.\n"
            f"Silakan coba lagi dalam {remaining_block / 60:.1f} menit."
        )
        return

    if not context.args:
        await update.message.reply_text("Gunakan format: /get <nama_file_lengkap>")
        return
        
    requested_filename = " ".join(context.args)
    
    if requested_filename in file_database:
        # Jika berhasil, reset riwayat percobaan gagal pengguna
        if user_id in get_attempts:
            get_attempts[user_id] = []

        file_info = file_database[requested_filename]
        # ... (sisa logika pengiriman file seperti sebelumnya)
        file_id = file_info["file_id"]
        file_type = file_info["file_type"]
        
        logger.info(f"Mengirim file '{requested_filename}' ke user {update.effective_user.username}")
        if file_type == "document":
            await context.bot.send_document(chat_id=update.effective_chat.id, document=file_id)
        elif file_type == "video":
            await context.bot.send_video(chat_id=update.effective_chat.id, video=file_id)
        elif file_type == "photo":
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=file_id)
    else:
        # 2. Jika file tidak ditemukan, catat sebagai percobaan gagal
        logger.warning(f"Percobaan gagal /get dari user {user_id} untuk file '{requested_filename}'")
        
        # Inisialisasi daftar percobaan jika belum ada
        if user_id not in get_attempts:
            get_attempts[user_id] = []
        
        # Tambahkan timestamp percobaan saat ini
        get_attempts[user_id].append(current_time)
        
        # 3. Bersihkan timestamp lama yang sudah di luar jendela waktu
        valid_attempts = [t for t in get_attempts[user_id] if current_time - t < GET_ATTEMPT_WINDOW_SECONDS]
        get_attempts[user_id] = valid_attempts
        
        # 4. Cek apakah jumlah percobaan melebihi batas
        if len(valid_attempts) >= GET_ATTEMPT_LIMIT:
            user_blocks[user_id] = current_time + BLOCK_DURATION_SECONDS
            # Hapus riwayat percobaan setelah diblokir
            get_attempts[user_id] = []
            logger.error(f"USER {user_id} DIBLOKIR karena brute force /get")
            await update.message.reply_text(
                f"❌ Anda telah mencoba terlalu sering! Akun Anda diblokir selama {BLOCK_DURATION_SECONDS / 60:.0f} menit."
            )
        else:
            await update.message.reply_text(f"❌ File dengan nama '{requested_filename}' tidak ditemukan.")

# 5. Perintah /stats
def format_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    import math
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

# 5. Perintah /stats (DI SINI TEMPAT DECORATOR-NYA)
@rate_limit
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan statistik penyimpanan dengan format yang lebih indah dan ramah."""
    
    # Pesan jika database masih kosong
    if not file_database:
        await update.message.reply_html(
            "🗃️ <b>Penyimpanan Anda Masih Kosong</b>\n\n"
            "Yuk, kirimkan file pertama Anda untuk memulai petualangan digital ini! 🚀"
        )
        return

    # --- Perhitungan Statistik ---
    total_files = len(file_database)
    total_size = sum(info.get("file_size", 0) for info in file_database.values())
    type_counts = {"document": 0, "video": 0, "photo": 0}
    for info in file_database.values():
        type_counts[info["file_type"]] += 1
    
    # --- Helper function untuk membuat bar visual ---
    def create_progress_bar(percentage, bar_length=12):
        filled_length = int(bar_length * percentage // 100)
        bar = '▓' * filled_length + '░' * (bar_length - filled_length)
        return f"<code>{bar}</code>"

    # --- Membangun Tampilan Pesan ---
    doc_count = type_counts['document']
    vid_count = type_counts['video']
    pho_count = type_counts['photo']

    doc_perc = (doc_count / total_files) * 100 if total_files > 0 else 0
    vid_perc = (vid_count / total_files) * 100 if total_files > 0 else 0
    pho_perc = (pho_count / total_files) * 100 if total_files > 0 else 0

    composition_lines = []
    if doc_count > 0:
        bar = create_progress_bar(doc_perc)
        composition_lines.append(f"📁 <b>Dokumen:</b> {doc_count} file\n{bar} {doc_perc:.1f}%")
    if vid_count > 0:
        bar = create_progress_bar(vid_perc)
        composition_lines.append(f"🎥 <b>Video:</b> {vid_count} file\n{bar} {vid_perc:.1f}%")
    if pho_count > 0:
        bar = create_progress_bar(pho_perc)
        composition_lines.append(f"🖼️ <b>Foto:</b> {pho_count} file\n{bar} {pho_perc:.1f}%")
    
    composition_str = "\n\n".join(composition_lines)

    # --- Pesan Final ---
    stats_message = (
        f"✨ <b>Laporan Penyimpanan Anda</b> ✨\n\n"
        f"Ini dia rincian semua file berharga yang telah Anda simpan:\n\n"
        f"🗂️ <b>Total File:</b> {total_files}\n"
        f"💾 <b>Total Ukuran:</b> {format_size(total_size)}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
        f"<b>Komposisi File:</b>\n\n"
        f"{composition_str}\n\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"Hebat! Terus kumpulkan file penting Anda. 💪"
    )
    
    await update.message.reply_html(stats_message)

# --- Fungsi Utama untuk Menjalankan Bot ---
def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("get", get_file))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO | filters.PHOTO, handle_file))

    print("Bot sedang berjalan dengan penyimpanan permanen...")
    application.run_polling()

if __name__ == '__main__':
    main()