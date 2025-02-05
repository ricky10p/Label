import json
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Konstanta global
ITEMS_PER_PAGE = 5  # Jumlah hasil per halaman

def search_address(query):
    try:
        with open('data/kodepos.json') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading data: {str(e)}")
        return []

    filters = {}
    general_terms = []

    for part in query.split():
        if ':' in part:
            key, value = part.split(':', 1)
            filters[key.lower().strip()] = value.strip().lower()
        else:
            general_terms.append(part.strip().lower())

    results = []
    for entry in data:
        match = True

        for field in ['kelurahan', 'kecamatan', 'kota', 'provinsi', 'kode_pos']:
            if field in filters:
                entry_value = str(entry.get(field, '')).lower()
                filter_value = filters[field]

                if field == 'kode_pos':
                    if entry_value != filter_value:
                        match = False
                        break
                else:
                    if filter_value not in entry_value:
                        match = False
                        break

        if match and general_terms:
            searchable = ' '.join([
                str(entry['kelurahan']),
                str(entry['kecamatan']),
                str(entry['kota']),
                str(entry['provinsi'])
            ]).lower()

            if not all(term in searchable for term in general_terms):
                match = False

        if match:
            results.append(entry)

    return sorted(results, key=lambda x: (
        x['provinsi'],
        x['kota'],
        x['kecamatan'],
        x['kelurahan']
    ))

def get_shipping_estimates(postal_code):
    autofill_url = f"https://app.mengantar.com/api/address/autofill?keyword={postal_code}"
    try:
        response = requests.get(autofill_url)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("data"):
                destination = data["data"][0]
                destination_id = destination["_id"]

                estimate_url = f"https://app.mengantar.com/api/order/allEstimatePublic?origin_id=5fc62debf8f44b34aa4bded9&destination_id={destination_id}&weight=1"
                estimate_response = requests.get(estimate_url)
                if estimate_response.status_code == 200:
                    estimate_data = estimate_response.json()
                    if estimate_data.get("success") and estimate_data.get("data"):
                        return estimate_data["data"]
                    return "❌ Tidak ada estimasi biaya pengiriman yang tersedia."
                return "❌ Gagal mendapatkan estimasi biaya pengiriman."
            return "❌ Tidak ditemukan alamat yang cocok di Mengantar."
        return "❌ Terjadi kesalahan saat menghubungi API Mengantar."
    except Exception as e:
        return f"❌ Error: {str(e)}"

def format_results_message(results, page):
    start = (page-1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    response = []

    for idx, entry in enumerate(results[start:end], start=1):
        global_number = start + idx
        response.append(
            f"<b>🔢 HASIL {global_number}</b>\n"
            f"🏘️ <i>Kelurahan:</i> {entry['kelurahan']}\n"
            f"📍 <i>Kecamatan:</i> {entry['kecamatan']}\n"
            f"🏙️ <i>Kota:</i> {entry['kota']}\n"
            f"🌏 <i>Provinsi:</i> {entry['provinsi']}\n"
            f"📮 <i>Kode Pos:</i> <code>{entry['kode_pos']}</code>\n"
        )
    return '\n\n'.join(response)

def create_number_buttons(results, page, user_id):
    markup = InlineKeyboardMarkup()
    start = (page-1) * ITEMS_PER_PAGE

    row = []
    for idx in range(len(results[start:start+ITEMS_PER_PAGE])):
        global_number = start + idx + 1
        row.append(InlineKeyboardButton(str(global_number), callback_data=f"PILIH_{user_id}_{start+idx}"))
    markup.row(*row)

    nav_buttons = []
    total_pages = (len(results) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"HALAMAN_{user_id}_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data=f"HALAMAN_{user_id}_{page+1}"))

    if nav_buttons:
        markup.row(*nav_buttons)

    return markup

def create_detail_buttons(user_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Kembali ke Hasil", callback_data=f"BACK_{user_id}"))
    markup.add(InlineKeyboardButton("📦 Cek Ongkir", callback_data=f"CEKONGKIR_{user_id}"))
    markup.add(InlineKeyboardButton("📄 Cetak Resi", callback_data=f"CETAKRESI_{user_id}"))  # Tambahkan tombol ini
    return markup

def create_back_button(user_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Kembali ke Detail", callback_data=f"BACKDETAIL_{user_id}"))
    return markup
