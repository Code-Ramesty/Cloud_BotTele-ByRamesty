# handlers.py

import logging, time, functools, zlib, math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import COOLDOWN_SECONDS, FILES_PER_PAGE
from database_manager import load_database, save_database

# --- Inisialisasi & Variabel Global ---
logger = logging.getLogger(__name__)
db_data = load_database() # Ini sekarang berisi data SEMUA pengguna
user_cooldowns = {}

# --- FUNGSI HELPER BARU ---
def get_user_data(user_id: str):
    """Mengambil data untuk user tertentu, atau membuat entry baru jika belum ada."""
    user_id = str(user_id)
    if user_id not in db_data:
        db_data[user_id] = {"folders": [], "files": {}}
    return db_data[user_id]

# (Fungsi rate_limit dan format_size tidak berubah)
def rate_limit(func):
    @functools.wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id; current_time = time.time()
        if user_id in user_cooldowns and (current_time - user_cooldowns.get(user_id, 0)) < COOLDOWN_SECONDS:
            remaining = COOLDOWN_SECONDS - (current_time - user_cooldowns.get(user_id, 0))
            if update.callback_query: await context.bot.answer_callback_query(update.callback_query.id, text=f"⏳ Tunggu {remaining:.1f} dtk.", show_alert=True)
            else: await (update.message or update.callback_query.message).reply_text(f"⏳ Anda terlalu cepat! Tunggu {remaining:.1f} dtk.")
            return
        user_cooldowns[user_id] = current_time
        return await func(update, context, *args, **kwargs)
    return wrapped

def format_size(size_bytes):
    """Mengubah byte menjadi format yang mudah dibaca (KB, MB, GB)."""
    if not isinstance(size_bytes, (int, float)) or size_bytes <= 0:
        return "0 B"
    
    size_name = ("B", "KB", "MB", "GB", "TB")
    
    try:
        i = int(math.floor(math.log(size_bytes, 1024)))
        if i >= len(size_name):
            i = len(size_name) - 1
            
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        
        return f"{s} {size_name[i]}"
    except ValueError:
        # Menangani kasus jika size_bytes adalah 0 setelah pengecekan awal
        return "0 B"



# --- FUNGSI-FUNGSI PERINTAH (DIPERBARUI UNTUK MULTI-USER) ---

@rate_limit
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    get_user_data(user_id) # Pastikan user terdaftar saat pertama kali start
    save_database(db_data)
    user = update.effective_user
    await update.message.reply_html(f"Halo {user.mention_html()}! Bot manajemen file pribadi Anda siap digunakan.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)
    
    file_attachment, file_type, original_filename = None, None, None
    if update.message.document:
        file_attachment, file_type, original_filename = update.message.document, "document", update.message.document.file_name
    elif update.message.video:
        file_attachment, file_type, original_filename = update.message.video, "video", update.message.video.file_name or f"video_{update.message.video.file_unique_id}.mp4"
    elif update.message.photo:
        file_attachment, file_type, original_filename = update.message.photo[-1], "photo", f"photo_{update.message.photo[-1].file_unique_id}.jpg"

    if file_attachment:
        if original_filename in user_data["files"]:
            await update.message.reply_text(f"⚠️ Gagal! File '{original_filename}' sudah ada di penyimpanan Anda.")
            return
            
        # --- PERBAIKAN DI SINI ---
        # Gunakan 'or 0' untuk memberi nilai default 0 jika file_size adalah None
        file_size = file_attachment.file_size or 0
        
        user_data["files"][original_filename] = {
            "file_id": file_attachment.file_id,
            "file_size": file_size, # Gunakan variabel file_size yang sudah aman
            "file_type": file_type,
            "folder": "_root"
        }
        save_database(db_data)
        logger.info(f"File '{original_filename}' disimpan dari user {user_id}")
        await update.message.reply_text(f"✅ Berhasil diunggah ke folder Utama!\nNama File: {original_filename}")

@rate_limit
async def buat_folder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)
    if not context.args: await update.message.reply_text("Gunakan format: /buat_folder <nama_folder_baru>"); return
    folder_name = " ".join(context.args)
    if folder_name in user_data["folders"] or folder_name == "Utama" or folder_name == "_root":
        await update.message.reply_text(f"❌ Folder '{folder_name}' sudah ada."); return
    user_data["folders"].append(folder_name)
    save_database(db_data)
    await update.message.reply_text(f"✅ Folder '{folder_name}' berhasil dibuat.")


# ... (SEMUA FUNGSI LAINNYA JUGA PERLU MENGGUNAKAN user_data)
# Contoh untuk 'list_files' dan 'stats'. Pola yang sama berlaku untuk SEMUA fungsi.

@rate_limit
async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_folder_menu(update, "list")

@rate_limit
async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_folder_menu(update, "get")

@rate_limit
async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_folder_menu(update, "del")

@rate_limit
async def hapus_folder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Memulai proses penghapusan folder (tahap 1: pilih folder)."""
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)

    if not user_data["folders"]:
        await update.message.reply_html("<b>Tidak ada folder kustom untuk dihapus.</b>")
        return

    keyboard = []
    for folder_name in sorted(user_data["folders"]):
        keyboard.append([InlineKeyboardButton(f"📁 {folder_name}", callback_data=f"rmdir-select_{folder_name}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Pilih folder yang ingin Anda hapus:", reply_markup=reply_markup)

@rate_limit
async def pindah_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)
    if not user_data["files"]: await update.message.reply_html("🗃️ <b>Tidak ada file untuk dipindahkan.</b>"); return
    all_files = sorted(user_data["files"].items())
    reply_markup = create_paginated_keyboard(user_id, all_files, 0, "move", "selectfile")
    await update.message.reply_text("Pilih file yang ingin Anda pindahkan:", reply_markup=reply_markup)


@rate_limit
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)
    if not context.args: await update.message.reply_text("Contoh: `/cari laporan`"); return
    keyword = " ".join(context.args).lower()
    search_results = sorted([(fn, dt) for fn, dt in user_data["files"].items() if keyword in fn.lower()])
    if not search_results: await update.message.reply_text(f"❌ Tidak ada file ditemukan: `{keyword}`", parse_mode='MarkdownV2'); return
    reply_markup = create_paginated_keyboard(user_id, search_results, 0, "search", keyword)
    await update.message.reply_text(f"Hasil pencarian untuk '{keyword}':", reply_markup=reply_markup)


@rate_limit
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan statistik penyimpanan dengan format yang lebih indah dan ramah."""
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)
    total_files = len(user_data['files'])
    
    if total_files == 0:
        await update.message.reply_html("🗃️ <b>Penyimpanan Anda Masih Kosong.</b>")
        return

    # Menghitung total ukuran dengan aman
    total_size = sum(info.get("file_size") or 0 for info in user_data['files'].values())
    
    counts = {"document": 0, "video": 0, "photo": 0}
    for info in user_data['files'].values():
        counts[info["file_type"]] += 1
        
    def create_bar(p):
        filled = int(12 * p // 100)
        return f"<code>{'▓' * filled}{'░' * (12 - filled)}</code>"
        
    lines = []
    if counts['document'] > 0:
        lines.append(f"📁 Dokumen: {counts['document']} file\n{create_bar((counts['document']/total_files)*100)} {(counts['document']/total_files)*100:.1f}%")
    if counts['video'] > 0:
        lines.append(f"🎥 Video: {counts['video']} file\n{create_bar((counts['video']/total_files)*100)} {(counts['video']/total_files)*100:.1f}%")
    if counts['photo'] > 0:
        lines.append(f"🖼️ Foto: {counts['photo']} file\n{create_bar((counts['photo']/total_files)*100)} {(counts['photo']/total_files)*100:.1f}%")
        
    msg = (
        f"✨ <b>Laporan Penyimpanan Anda</b> ✨\n\n"
        f"🗂️ <b>Total File:</b> {total_files}\n"
        f"💾 <b>Total Ukuran:</b> {format_size(total_size)}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
        f"<b>Komposisi File:</b>\n\n"
        f"{'\n\n'.join(lines)}\n\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"💪 Hebat! Terus kumpulkan file penting Anda."
    )
    await update.message.reply_html(msg)

@rate_limit
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (Fungsi ini tidak perlu akses data, jadi tidak berubah)
    current_year = time.strftime("%Y"); creator_username = "MazAlvi"
    info_text = (f'🤖 <b>Tentang Bot Penyimpanan Pribadi</b> 🤖\n\nHai! Saya adalah asisten pribadi Anda untuk menyimpan dan mengelola file-file penting langsung di Telegram.\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n✨ <b>Fitur Utama Saya:</b>\n\n<code>/start</code> - 🏠 Memulai interaksi dengan saya.\n<code>/list</code> - 🗂️ Melihat semua file Anda yang tersimpan.\n<code>/get</code> - 📥 Mengunduh file dari penyimpanan.\n<code>/hapus</code> - ❌ Menghapus file secara permanen.\n<code>/buat_folder</code> - ➕ Membuat folder baru.\n<code>/pindah</code> - ➡️ Memindahkan file antar folder.\n<code>/cari</code> - 🔍 Mencari file spesifik dengan kata kunci.\n<code>/stats</code> - 📊 Melihat statistik penyimpanan Anda.\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\nCukup kirimkan saya file untuk menyimpannya. Semua file Anda aman bersama saya! 🚀\n\n--- \n<i>Dibuat oleh: <a href="https://t.me/{creator_username}">Ramesty</a>\n© {current_year} Hak Cipta Dilindungi</i>')
    await update.message.reply_html(info_text)

async def show_folder_menu(update: Update, command: str):
    user_id = str(update.effective_user.id)
    user_data = get_user_data(user_id)
    keyboard = [[InlineKeyboardButton("📁 Utama (Root)", callback_data=f"{command}-list__root_0")]]
    for folder_name in sorted(user_data["folders"]):
        keyboard.append([InlineKeyboardButton(f"📁 {folder_name}", callback_data=f"{command}-list_{folder_name}_0")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = {"list": "Pilih folder untuk melihat isinya:", "get": "Pilih folder untuk mengambil file:", "del": "Pilih folder untuk menghapus file:"}
    if update.callback_query: await update.callback_query.edit_message_text(text=message_text[command], reply_markup=reply_markup)
    else: await update.message.reply_text(text=message_text[command], reply_markup=reply_markup)

@rate_limit
async def privacy_policy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan pesan kebijakan privasi bot."""
    # Mengambil tahun saat ini agar selalu update
    current_year = time.strftime("%Y")
    
    privacy_text = (
        "🔐 <b>Kebijakan Privasi Bot</b>\n\n"
        f"<i>Terakhir diperbarui: 16 September {current_year}</i>\n\n"
        "Privasi Anda adalah prioritas utama. Berikut adalah data yang kami kumpulkan dan bagaimana kami menggunakannya:\n\n"
        "<b>1. Data yang Dikumpulkan</b>\n"
        "Bot ini HANYA menyimpan informasi yang mutlak diperlukan untuk berfungsi:\n"
        "• <b>User ID Telegram</b>: Untuk memisahkan file Anda dari pengguna lain.\n"
        "• <b>Metadata File</b>: `file_id` (penunjuk dari Telegram), nama, ukuran, jenis, dan folder file Anda.\n\n"
        "❗️<b>PENTING</b>: Bot **TIDAK** menyimpan isi file Anda. File fisik tetap aman di server Telegram.\n\n"
        "<b>2. Penggunaan Data</b>\n"
        "Data Anda hanya digunakan agar bot bisa berfungsi, seperti menampilkan daftar file dan mengirimkannya saat Anda minta.\n\n"
        "<b>3. Berbagi Data</b>\n"
        "Data Anda **tidak akan pernah** dibagikan, dijual, atau disewakan kepada pihak ketiga mana pun.\n\n"
        "<b>4. Penghapusan Data</b>\n"
        "Anda memiliki kendali penuh. Menggunakan perintah <code>/hapus</code> dan <code>/hapus_folder</code> akan menghapus metadata terkait secara permanen dari database kami."
    )
    await update.message.reply_html(privacy_text)

def create_paginated_keyboard(user_id: str, item_list: list, page: int, command: str, context_data: str):
    user_data = get_user_data(user_id)
    # ... (sisa logika tidak berubah signifikan, karena sudah menerima item_list yang benar)
    keyboard = []; total_items = len(item_list); total_pages = math.ceil(total_items/FILES_PER_PAGE) if total_items>0 else 1
    start_index = page*FILES_PER_PAGE; end_index = start_index+FILES_PER_PAGE
    items_on_page = item_list[start_index:end_index]
    if command == "move" and context_data == "selectfile":
        for filename, details in items_on_page:
            icon = {"document":"📁", "video":"🎥", "photo":"🖼️"}.get(details.get("file_type"),"📄"); button_text = f"{icon} {filename}"
            file_hash = str(zlib.adler32(filename.encode('utf-8'))); keyboard.append([InlineKeyboardButton(button_text, callback_data=f"move-select_{file_hash}")])
    else:
        folder_name = context_data; next_action_prefix = "file" if command == "get" else ("info" if command == "list" else "select")
        for filename, details in items_on_page:
            icon = {"document":"📁", "video":"🎥", "photo":"🖼️"}.get(details.get("file_type"),"📄"); button_text = f"{icon} {filename}"
            file_hash = str(zlib.adler32(filename.encode('utf-8'))); keyboard.append([InlineKeyboardButton(button_text, callback_data=f"{command}-{next_action_prefix}_{file_hash}")])
    nav_buttons = []
    if page > 0: nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"{command}-list_{context_data}_{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1: nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"{command}-list_{context_data}_{page + 1}"))
    if nav_buttons: keyboard.append(nav_buttons)
    if command in ["get", "list", "del"]: keyboard.append([InlineKeyboardButton("⬅️ Kembali ke Folder", callback_data=f"{command}-show-category")])
    elif command == "move": keyboard.append([InlineKeyboardButton("⬅️ Batal Pindah", callback_data="move-cancel_")])
    return InlineKeyboardMarkup(keyboard)

@rate_limit
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Router super canggih untuk semua tombol, sekarang dengan logika hapus folder."""
    query = update.callback_query
    user_id = str(query.from_user.id)
    user_data = get_user_data(user_id)
    await query.answer()
    if query.data == "noop": return
    
    command, _, data = query.data.partition('-')
    action, _, data = data.partition('_')

    # ... (logika untuk action == "list", "show-category", dan command == "move" tetap sama)
    # ... (cukup salin-tempel seluruh fungsi ini untuk menggantikan yang lama)

    # === BAGIAN MENAMPILKAN DAFTAR FILE (PAGINASI) ===
    if action == "list":
        context_data, _, page_str = data.rpartition('_'); page = int(page_str)
        if command == "search":
            keyword = context_data; file_list = sorted([(fn, dt) for fn, dt in user_data["files"].items() if keyword in fn.lower()])
        elif command == "move":
            file_list = sorted(user_data["files"].items())
        else:
            folder = context_data; file_list = sorted([(fn, dt) for fn, dt in user_data["files"].items() if dt.get('folder') == folder])
        reply_markup = create_paginated_keyboard(user_id, file_list, page, command, context_data)
        display_text = f"Isi folder '{context_data if context_data != '_root' else 'Utama'}':"
        if command == "move": display_text = "Pilih file yang ingin Anda pindahkan:"
        await query.edit_message_text(text=display_text, reply_markup=reply_markup)

    # === BAGIAN MENU UTAMA / KEMBALI ===
    elif action == "show-category": await show_folder_menu(update, command)

    # === BAGIAN PROSES PINDAH FILE (MULTI-LANGKAH) ===
    elif command == "move":
        if action == "select":
            file_hash_to_move = data
            filename_to_move = next((fn for fn in user_data["files"] if str(zlib.adler32(fn.encode('utf-8'))) == file_hash_to_move), None)
            if not filename_to_move: await query.edit_message_text(text="❌ Gagal! File sumber tidak ditemukan."); return
            keyboard = [[InlineKeyboardButton("📁 Utama (Root)", callback_data=f"move-tofolder_{file_hash_to_move}__root")]]
            for folder_name in sorted(user_data["folders"]): keyboard.append([InlineKeyboardButton(f"📁 {folder_name}", callback_data=f"move-tofolder_{file_hash_to_move}_{folder_name}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text=f"Pindahkan '{filename_to_move}' ke folder:", reply_markup=reply_markup)
        elif action == "tofolder":
            file_hash, _, dest_folder = data.partition('_')
            filename_to_move = next((fn for fn in user_data["files"] if str(zlib.adler32(fn.encode('utf-8'))) == file_hash), None)
            if filename_to_move:
                user_data["files"][filename_to_move]["folder"] = dest_folder; save_database(db_data)
                dest_display = dest_folder if dest_folder != "_root" else "Utama"
                await query.edit_message_text(text=f"✅ File '{filename_to_move}' dipindahkan ke folder '{dest_display}'.")
            else: await query.edit_message_text(text="❌ Gagal! File tidak ditemukan.")

    # === BAGIAN BARU: PROSES HAPUS FOLDER (MULTI-LANGKAH) ===
    elif command == "rmdir":
        folder_to_delete = data
        files_in_folder = [fn for fn, dt in user_data["files"].items() if dt.get("folder") == folder_to_delete]

        if action == "select":
            if not files_in_folder: # Jika folder kosong
                keyboard = [[
                    InlineKeyboardButton("✅ Ya, Hapus", callback_data=f"rmdir-confirm_{folder_to_delete}"),
                    InlineKeyboardButton("❌ Batal", callback_data="rmdir-cancel_")
                ]]
                await query.edit_message_text(text=f"Folder '{folder_to_delete}' ini kosong. Anda yakin ingin menghapusnya?", reply_markup=InlineKeyboardMarkup(keyboard))
            else: # Jika folder berisi file
                keyboard = [[
                    InlineKeyboardButton("🗑️ Hapus Semua Isinya", callback_data=f"rmdir-delall_{folder_to_delete}"),
                    InlineKeyboardButton("➡️ Pindahkan ke Utama", callback_data=f"rmdir-moveall_{folder_to_delete}")
                ], [InlineKeyboardButton("❌ Batal", callback_data="rmdir-cancel_")]]
                await query.edit_message_text(
                    text=f"⚠️ Folder '{folder_to_delete}' berisi {len(files_in_folder)} file! Apa yang ingin Anda lakukan?",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )

        elif action in ["confirm", "delall", "moveall"]:
            if folder_to_delete not in user_data["folders"]:
                await query.edit_message_text(text="❌ Gagal! Folder sudah dihapus."); return

            if action == "moveall":
                for filename in files_in_folder:
                    user_data["files"][filename]["folder"] = "_root"
            elif action == "delall":
                for filename in files_in_folder:
                    del user_data["files"][filename]
            
            # Hapus folder dari daftar setelah isinya diurus
            user_data["folders"].remove(folder_to_delete)
            save_database(db_data)
            await query.edit_message_text(text=f"✅ Folder '{folder_to_delete}' dan isinya telah berhasil diurus.")

        elif action == "cancel":
            await query.edit_message_text(text="👍 Aksi penghapusan folder dibatalkan.")

    # === BAGIAN PROSES GET & DELETE FILE ===
    elif action in ["file", "select"]:
        received_hash = data
        filename_to_process = next((fn for fn in user_data["files"] if str(zlib.adler32(fn.encode('utf-8'))) == received_hash), None)
        if not filename_to_process: await query.edit_message_text(text="❌ Gagal! File mungkin sudah dihapus."); return
        if action == "file":
            info = user_data["files"][filename_to_process]
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action='upload_document')
            if info["file_type"] == "document": await context.bot.send_document(query.message.chat_id, info["file_id"])
            elif info["file_type"] == "video": await context.bot.send_video(query.message.chat_id, info["file_id"])
            elif info["file_type"] == "photo": await context.bot.send_photo(query.message.chat_id, info["file_id"])
        elif action == "select":
            keyboard = [[InlineKeyboardButton("✅ Ya, Hapus", callback_data=f"del-confirm_{received_hash}"), InlineKeyboardButton("❌ Batal", callback_data="del-cancel_")]]
            await query.edit_message_text(text=f"Anda yakin?\n<b>File:</b> <code>{filename_to_process}</code>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    # === BAGIAN KONFIRMASI HAPUS & BATAL UMUM ===
    elif action == "confirm":
        received_hash = data
        filename_to_process = next((fn for fn in user_data["files"] if str(zlib.adler32(fn.encode('utf-8'))) == received_hash), None)
        if filename_to_process and filename_to_process in user_data["files"]:
            del user_data["files"][filename_to_process]; save_database(db_data)
            await query.edit_message_text(text=f"✅ File <code>{filename_to_process}</code> berhasil dihapus.", parse_mode='HTML')
        else: await query.edit_message_text(text="❌ Gagal! File mungkin sudah dihapus.")
    
    elif action == "cancel":
        await query.edit_message_text(text="👍 Aksi dibatalkan.")