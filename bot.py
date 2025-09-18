import logging
import asyncio
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Cukup impor TOKEN, config.py akan menangani sisanya secara otomatis.
from config import TOKEN
from handlers import (
    start, info_command, stats, get_file, 
    handle_file, delete_command, button_handler, 
    search_command, list_files, buat_folder_command,
    pindah_command, hapus_folder_command,
    privacy_policy_command
)

async def post_initialize(application: Application):
    # ... (Fungsi ini tidak berubah)
    commands = [
        BotCommand("start", "🏠 Mulai ulang bot"),
        BotCommand("info", "ℹ️ Tentang bot ini"),
        BotCommand("list", "🗂️ Lihat semua file"),
        BotCommand("get", "📥 Ambil file dari penyimpanan"),
        BotCommand("pindah", "➡️ Pindahkan file ke folder lain"),
        BotCommand("cari", "🔍 Cari file spesifik"),
        BotCommand("stats", "📊 Lihat statistik penyimpanan"),
        BotCommand("buat_folder", "➕ Buat folder baru"),
        BotCommand("hapus_folder", "➖ Hapus folder"),
        BotCommand("hapus", "❌ Hapus file dari folder"),
        BotCommand("kebijakan_privasi", "🔒 Baca Kebijakan Privasi"),
    ]
    await application.bot.set_my_commands(commands)

async def main():
    # ... (Fungsi ini tidak berubah)
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    application = Application.builder().token(TOKEN).build()

    # Pendaftaran Handler (tidak berubah)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("list", list_files))
    application.add_handler(CommandHandler("cari", search_command))
    application.add_handler(CommandHandler("get", get_file))
    application.add_handler(CommandHandler("hapus", delete_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("buat_folder", buat_folder_command))
    application.add_handler(CommandHandler("hapus_folder", hapus_folder_command))
    application.add_handler(CommandHandler("pindah", pindah_command))
    application.add_handler(CommandHandler("kebijakan_privasi", privacy_policy_command))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO | filters.PHOTO, handle_file))
    application.add_handler(CallbackQueryHandler(button_handler))

    try:
        print("Bot sedang berjalan...")
        await application.initialize()
        await post_initialize(application)
        await application.updater.start_polling()
        await application.start()
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("Bot dihentikan.")
    finally:
        if application.updater and application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()

if __name__ == '__main__':
    asyncio.run(main())
