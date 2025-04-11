import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import requests
from datetime import datetime, timedelta
import threading

API_TOKEN = "7809159665:AAEM1x02VKgTAs8OzTt0I-ZUC57XbKXMORU"
CRYPTO_BOT_TOKEN = "368678:AA5a84tPAU5I8dTTgZ0oyMseyYCitoJCg7c"
OUTLINE_API_URL = "https://194.156.66.56:57071/dzLy_MMYLxSWsao8fjOgLA"
CRYPTO_BOT_API = "https://pay.crypt.bot/api"

bot = telebot.TeleBot(API_TOKEN, threaded=True)

manual_usdt_rate = None
TRAFFIC_LIMIT_GB = 1
EXTRA_GB_PRICE = 100

# DB INIT
db = sqlite3.connect("infervpn.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    key_id INTEGER,
    access_url TEXT,
    expires DATETIME,
    is_trial BOOLEAN DEFAULT 1,
    balance REAL DEFAULT 0,
    is_subscribed BOOLEAN DEFAULT 0,
    traffic_used REAL DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    invoice_id TEXT,
    amount REAL,
    status TEXT DEFAULT 'pending'
)''')
db.commit()

# Курс

def get_usdt_rate():
    if manual_usdt_rate:
        return manual_usdt_rate
    try:
        response = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=USDTRUB", timeout=5)
        return float(response.json()['price'])
    except:
        return 90  # fallback курс

# Главное меню

def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💼 Мой баланс", callback_data='balance'),
        InlineKeyboardButton("🛒 Купить подписку", callback_data='buy_outline'),
        InlineKeyboardButton("📡 Моя подписка", callback_data='my_subscription'),
        InlineKeyboardButton("💳 Пополнить баланс", callback_data='pay'),
        InlineKeyboardButton("📊 Статус подписки", callback_data='status'),
        InlineKeyboardButton("🆘 Помощь", callback_data='help')
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
    db.commit()
    bot.send_message(user_id, "👋 Привет от команды INFERVPN! Мы за свободный интернет и защищённую цифровую жизнь. Добро пожаловать в наш сервис!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: True, content_types=['text'])
def support_message(message):
    if message.text.isdigit():
        handle_amount_input(message)
    else:
        print(f"📩 Сообщение в поддержку от {message.from_user.id} ({message.from_user.first_name}): {message.text}")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    try:
        if call.data == 'balance':
            cursor.execute("SELECT balance FROM users WHERE id=?", (user_id,))
            balance = cursor.fetchone()[0]
            bot.send_message(user_id, f"💼 Баланс: {balance:.2f} ₽")

        elif call.data == 'pay':
            bot.send_message(user_id, "💳 Введите сумму пополнения в рублях:")

        elif call.data.startswith('check_payment_'):
            invoice_id = call.data.split('_')[-1]
            headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
            resp = requests.get(f"{CRYPTO_BOT_API}/getInvoices", headers=headers, params={"invoice_ids": invoice_id}).json()
            status = resp['result']['items'][0]['status']
            if status == 'paid':
                cursor.execute("UPDATE payments SET status='paid' WHERE invoice_id=?", (invoice_id,))
                cursor.execute("UPDATE users SET balance=balance+(SELECT amount FROM payments WHERE invoice_id=?) WHERE id=?", (invoice_id, user_id))
                db.commit()
                bot.send_message(user_id, "✅ Баланс пополнен!")
            else:
                bot.send_message(user_id, "⏳ Платёж ещё не подтверждён.")

        elif call.data == 'buy_outline':
            cursor.execute("SELECT balance FROM users WHERE id=?", (user_id,))
            balance = cursor.fetchone()[0]
            if balance >= 240:
                res = requests.post(f"{OUTLINE_API_URL}/access-keys", verify=False).json()
                key_id, access_url = res['id'], res['accessUrl']
                expires = datetime.now() + timedelta(days=30)
                cursor.execute("UPDATE users SET key_id=?, access_url=?, expires=?, is_subscribed=1, balance=balance-240, is_trial=0, traffic_used=0 WHERE id=?",
                               (key_id, access_url, expires, user_id))
                db.commit()
                bot.send_message(user_id, f"✅ Подписка до {expires.strftime('%d.%m.%Y %H:%M')}\nВаш ключ: {access_url}\n📦 Трафик: 1 ГБ")
            else:
                bot.send_message(user_id, "❌ Недостаточно средств.")

        elif call.data == 'status':
            cursor.execute("SELECT expires FROM users WHERE id=?", (user_id,))
            result = cursor.fetchone()
            if result and result[0]:
                expires = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S.%f')
                left = expires - datetime.now()
                bot.send_message(user_id, f"📊 Подписка до {expires.strftime('%d.%m.%Y %H:%M')} (осталось {left.days} д., {left.seconds//3600} ч.)")
            else:
                bot.send_message(user_id, "❌ Подписка не активна.")

        elif call.data == 'my_subscription':
            cursor.execute("SELECT access_url, expires, traffic_used FROM users WHERE id=?", (user_id,))
            row = cursor.fetchone()
            if row and row[1]:
                access_url, expires, traffic = row
                expires = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S.%f')
                over = max(0, traffic - TRAFFIC_LIMIT_GB)
                bot.send_message(user_id, f"🔑 Ключ: {access_url}\n📅 До: {expires.strftime('%d.%m.%Y %H:%M')}\n📊 Трафик: {traffic:.2f} ГБ / {TRAFFIC_LIMIT_GB} ГБ\n💸 Сверх: {int(over)} ГБ × {EXTRA_GB_PRICE}₽ = {int(over)*EXTRA_GB_PRICE} ₽")
            else:
                bot.send_message(user_id, "❌ Подписка не найдена.")

        elif call.data == 'help':
            bot.send_message(user_id, "🆘 Напишите сообщение, оно будет передано в поддержку.")

        bot.answer_callback_query(call.id)

    except Exception as e:
        bot.send_message(user_id, f"⚠️ Ошибка: {str(e)}")

# Обработка ввода суммы

def handle_amount_input(message):
    user_id = message.from_user.id
    rub = float(message.text)
    usdt = round(rub / get_usdt_rate(), 2)
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    payload = {"asset": "USDT", "amount": usdt, "description": f"Пополнение на {rub}₽"}
    resp = requests.post(f"{CRYPTO_BOT_API}/createInvoice", headers=headers, json=payload).json()
    if resp.get('ok'):
        invoice = resp['result']
        cursor.execute("INSERT INTO payments (user_id, invoice_id, amount) VALUES (?, ?, ?)", (user_id, invoice['invoice_id'], rub))
        db.commit()
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("✅ Я оплатил", callback_data=f'check_payment_{invoice["invoice_id"]}'))
        bot.send_message(user_id, f"💳 [Оплатите {usdt} USDT]({invoice['pay_url']})", reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(user_id, "⚠️ Ошибка создания счёта.")

# Запуск бота
threading.Thread(target=lambda: bot.infinity_polling(timeout=30, long_polling_timeout=10), daemon=True).start()

# Консоль
while True:
    cmd = input("Команда (rate/support/add_balance): ").strip().lower()
    if cmd == "rate":
        manual_usdt_rate = float(input("USDT к RUB: "))
    elif cmd == "support":
        uid = int(input("ID пользователя: "))
        msg = input("Сообщение: ")
        bot.send_message(uid, f"🔔 Поддержка: {msg}")
    elif cmd == "add_balance":
        uid = int(input("ID: "))
        amt = float(input("Сумма: "))
        cursor.execute("UPDATE users SET balance=balance+? WHERE id=?", (amt, uid))
        db.commit()
        print("✅ Готово")
