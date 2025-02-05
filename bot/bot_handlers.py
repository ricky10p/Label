import os
from telebot import TeleBot
from bot.bot_utils import (
    search_address,
    get_shipping_estimates,
    format_results_message,
    create_number_buttons,
    create_detail_buttons,
    create_back_button,
    ITEMS_PER_PAGE  # Impor konstanta ITEMS_PER_PAGE
)
from bot.session_manager import SessionManager
import html
from openpyxl import load_workbook
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# State management untuk menyimpan status input pengguna
user_states = {}

bot = None
session_manager = SessionManager()

def start_bot(token):
    global bot
    bot = TeleBot(token)

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        text = (
            "🔍 BOT PENCARIAN ALAMAT INDONESIA\n\n"
            "Ketik nama wilayah yang ingin dicari:\n"
            "Contoh: Bakongan atau 23773\n\n"
            "Gunakan filter spesifik:\n"
            "kelurahan:Bakongan provinsi:Aceh\n\n"
            "Atau kombinasi teks bebas dan filter:\n"
            "Bakongan provinsi:Aceh"
        )
        bot.send_message(message.chat.id, text, parse_mode='HTML')

    @bot.message_handler(func=lambda m: True)
    def handle_search(message):
        user_id = message.from_user.id
        query = message.text.strip()

        # Handle input berdasarkan state pengguna
        if user_id in user_states:
            state = user_states[user_id]
            if state == "waiting_for_name":
                user_states[user_id] = {"name": message.text, "state": "waiting_for_phone"}
                bot.reply_to(message, "📞 Masukkan nomor HP penerima:")
                return
            elif isinstance(state, dict) and state["state"] == "waiting_for_phone":
                user_states[user_id]["phone"] = message.text
                user_states[user_id]["state"] = "waiting_for_address"
                bot.reply_to(message, "📍 Masukkan alamat lengkap (contoh: Jl. Merdeka No. 12, RT 001/RW 002):")
                return
            elif isinstance(state, dict) and state["state"] == "waiting_for_address":
                name = state["name"]
                phone = state["phone"]
                address = message.text
                del user_states[user_id]

                # Simpan data sementara untuk proses selanjutnya
                user_states[user_id] = {"name": name, "phone": phone, "address": address, "state": "waiting_for_courier"}
                markup = create_courier_buttons(user_id)
                bot.send_message(message.chat.id, "🚚 Pilih jasa kirim:", reply_markup=markup)
                return

        results = search_address(query)
        if not results:
            bot.reply_to(message, "❌ Tidak ditemukan hasil untuk pencarian tersebut")
            return

        session_manager.save_results(user_id, results)

        msg_content = format_results_message(results, 1)
        markup = create_number_buttons(results, 1, user_id)

        bot.send_message(
            message.chat.id,
            f"🔍 Ditemukan {len(results)} hasil:\n\n{msg_content}",
            reply_markup=markup,
            parse_mode='HTML'
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('COURIER_'))
    def handle_courier_selection(call):
        user_id = int(call.data.split('_')[1])
        courier = call.data.split('_')[2]

        if user_id not in user_states or "state" not in user_states[user_id]:
            bot.answer_callback_query(call.id, "Sesi telah berakhir")
            return

        # Simpan pilihan jasa kirim
        user_states[user_id]["courier"] = courier
        user_states[user_id]["state"] = "waiting_for_cod"

        # Tampilkan pilihan COD ongkir
        markup = create_cod_buttons(user_id)
        bot.send_message(call.message.chat.id, "📦 Pilih opsi COD Ongkir:", reply_markup=markup)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('COD_'))
    def handle_cod_selection(call):
        user_id = int(call.data.split('_')[1])
        cod_option = call.data.split('_')[2]

        if user_id not in user_states or "state" not in user_states[user_id]:
            bot.answer_callback_query(call.id, "Sesi telah berakhir")
            return

        # Simpan pilihan COD ongkir
        user_states[user_id]["cod"] = cod_option

        # Lanjutkan proses cetak resi
        process_cetak_resi(call.message.chat.id, user_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('HALAMAN_'))
    def handle_page(call):
        _, user_id, page = call.data.split('_')
        user_id = int(user_id)
        page = int(page)

        results = session_manager.get_results(user_id)
        if not results:
            bot.answer_callback_query(call.id, "Sesi telah berakhir")
            return

        msg_content = format_results_message(results, page)
        markup = create_number_buttons(results, page, user_id)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🔍 Ditemukan {len(results)} hasil:\n\n{msg_content}",
            reply_markup=markup,
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('PILIH_'))
    def handle_selection(call):
        _, user_id, idx = call.data.split('_')
        user_id = int(user_id)
        idx = int(idx)

        results = session_manager.get_results(user_id)
        if not results or idx >= len(results):
            bot.answer_callback_query(call.id, "Data tidak tersedia")
            return

        selected = results[idx]
        session_manager.save_selected_address(user_id, selected)

        detail = (
            "📋 DETAIL LENGKAP\n\n"
            f"🏘️ Kelurahan: {html.escape(selected['kelurahan'])}\n"
            f"📍 Kecamatan: {html.escape(selected['kecamatan'])}\n"
            f"🏙️ Kota/Kab: {html.escape(selected['kota'])}\n"
            f"🌏 Provinsi: {html.escape(selected['provinsi'])}\n"
            f"📮 Kode Pos: {selected['kode_pos']}\n"
            f"🔢 Kode Kemendagri: {html.escape(selected['kode_kemendagri'])}"
        )

        markup = create_detail_buttons(user_id)
        bot.send_message(call.message.chat.id, detail, reply_markup=markup, parse_mode='HTML')
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('CEKONGKIR_'))
    def handle_cek_ongkir(call):
        user_id = int(call.data.split('_')[1])
        selected_address = session_manager.get_selected_address(user_id)

        if not selected_address:
            bot.answer_callback_query(call.id, "Alamat tidak tersedia")
            return

        postal_code = selected_address['kode_pos']
        estimates = get_shipping_estimates(postal_code)

        if isinstance(estimates, str):  # Jika error
            response_text = estimates
        else:
            response_text = "📦 ESTIMASI BIAYA PENGIRIMAN\n\n"
            for courier_name, courier_info in estimates.items():
                price = courier_info.get("price", "Tidak diketahui")
                estimate_delivery = courier_info.get("estimate_delivery", "Tidak diketahui")
                response_text += (
                    f"🚚 Kurir: {courier_name}\n"
                    f"💰 Harga: Rp {price}\n"
                    f"⏰ Estimasi Pengiriman: {estimate_delivery}\n\n"
                )

        markup = create_back_button(user_id)
        bot.send_message(call.message.chat.id, response_text, reply_markup=markup, parse_mode='HTML')
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('BACK_'))
    def handle_back(call):
        user_id = int(call.data.split('_')[1])
        results = session_manager.get_results(user_id)

        if not results:
            bot.answer_callback_query(call.id, "Sesi telah berakhir")
            return

        # Tampilkan halaman pertama hasil pencarian
        msg_content = format_results_message(results, 1)
        markup = create_number_buttons(results, 1, user_id)

        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🔍 Ditemukan {len(results)} hasil:\n\n{msg_content}",
            reply_markup=markup,
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('BACKDETAIL_'))
    def handle_back_detail(call):
        user_id = int(call.data.split('_')[1])
        selected_address = session_manager.get_selected_address(user_id)

        if not selected_address:
            bot.answer_callback_query(call.id, "Alamat tidak tersedia")
            return

        detail = (
            "📋 DETAIL LENGKAP\n\n"
            f"🏘️ Kelurahan: {html.escape(selected_address['kelurahan'])}\n"
            f"📍 Kecamatan: {html.escape(selected_address['kecamatan'])}\n"
            f"🏙️ Kota/Kab: {html.escape(selected_address['kota'])}\n"
            f"🌏 Provinsi: {html.escape(selected_address['provinsi'])}\n"
            f"📮 Kode Pos: {selected_address['kode_pos']}\n"
            f"🔢 Kode Kemendagri: {html.escape(selected_address['kode_kemendagri'])}"
        )

        markup = create_detail_buttons(user_id)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=detail,
            reply_markup=markup,
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('CETAKRESI_'))
    def handle_cetak_resi(call):
        user_id = int(call.data.split('_')[1])
        selected_address = session_manager.get_selected_address(user_id)

        if not selected_address:
            bot.answer_callback_query(call.id, "Alamat tidak tersedia")
            return

        # Mulai state untuk meminta nama penerima
        user_states[user_id] = "waiting_for_name"
        bot.send_message(call.message.chat.id, "📝 Masukkan nama penerima:")
        bot.answer_callback_query(call.id)

    def process_cetak_resi(chat_id, user_id):
        user_data = user_states.get(user_id)
        if not user_data:
            bot.send_message(chat_id, "❌ Data tidak tersedia")
            return

        selected_address = session_manager.get_selected_address(user_id)
        if not selected_address:
            bot.send_message(chat_id, "❌ Alamat tidak tersedia")
            return

        # Gabungkan alamat lengkap dengan data kelurahan, kecamatan, kota, dan provinsi
        full_address = (
            f"{user_data['address']}, "
            f"{selected_address['kelurahan']}, "
            f"{selected_address['kecamatan']}, "
            f"{selected_address['kota']}, "
            f"{selected_address['provinsi']}"
        )

        # Path ke file template Excel
        template_path = "data/label.xlsx"
        output_path = f"data/{user_data['name']}.xlsx"  # Nama file berdasarkan nama pelanggan

        try:
            # Kirim notifikasi bahwa resi sedang diproses
            bot.send_message(chat_id, f"⏳ Resi sedang diproses untuk {user_data['name']}...")

            # Load workbook dari template
            if not os.path.exists(template_path):
                bot.send_message(chat_id, "❌ File template Excel tidak ditemukan.")
                return

            workbook = load_workbook(template_path)
            sheet = workbook.active

            # Isi data ke file Excel
            sheet["D34"] = user_data["name"]  # Nama penerima
            sheet["D36"] = user_data["phone"]  # Nomor HP
            sheet["D38"] = full_address  # Alamat lengkap
            sheet["D41"] = selected_address['kode_pos']  # Kode pos
            sheet["B45"] = user_data["courier"]  # Jasa kirim
            sheet["B47"] = "IYA" if user_data["cod"] == "YES" else "TIDAK"  # COD Ongkir

            # Simpan file hasil edit
            workbook.save(output_path)
            workbook.close()

            # Kirim file ke pengguna dengan keterangan yang sesuai
            with open(output_path, "rb") as file:
                bot.send_document(chat_id, file, caption=f"📄 Berikut adalah resi untuk {user_data['name']}.")

            # Hapus file hasil edit dari server
            os.remove(output_path)

            bot.send_message(chat_id, "✅ Resi berhasil dikirim!")
        except FileNotFoundError:
            bot.send_message(chat_id, "❌ File template Excel tidak ditemukan. Pastikan file 'label.xlsx' ada di folder 'data/'.")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Gagal mencetak resi: {str(e)}")

    def create_courier_buttons(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("JNE", callback_data=f"COURIER_{user_id}_JNE"))
        markup.add(InlineKeyboardButton("J&T", callback_data=f"COURIER_{user_id}_J&T"))
        markup.add(InlineKeyboardButton("SiCepat", callback_data=f"COURIER_{user_id}_SiCepat"))
        markup.add(InlineKeyboardButton("Lion Parcel", callback_data=f"COURIER_{user_id}_LionParcel"))
        return markup

    def create_cod_buttons(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("COD Ongkir X", callback_data=f"COD_{user_id}_NO"))
        markup.add(InlineKeyboardButton("COD Ongkir ✓", callback_data=f"COD_{user_id}_YES"))
        return markup

    bot.infinity_polling()
