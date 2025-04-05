import os
import logging
import telebot
from openai import OpenAI
from openai._types import NOT_GIVEN 
from flask import Flask
from threading import Thread
import json

# === Загрузка данных из файла ===
if os.path.exists("data.json"):
    with open("data.json", "r") as f:
        data = json.load(f)
        chat_to_thread_id = data.get("chat_to_thread_id", {})
        chat_to_run_id = data.get("chat_to_run_id", {})
else:
    chat_to_thread_id = {}
    chat_to_run_id = {}


# Настройка логов
logging.basicConfig(level=logging.INFO)

# Получаем ключи из .env / Secrets
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Проверяем ключи
if not OPENAI_API_KEY:
    raise ValueError("❌ Нет API-ключа OpenAI.")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ Нет токена Telegram.")

# Инициализируем OpenAI с поддержкой Assistants v2
client = OpenAI(
    api_key=OPENAI_API_KEY,
    default_headers={"OpenAI-Beta": "assistants=v2"}
)

# Telegram-бот
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Чат -> thread_id
chat_to_thread_id = {}
chat_to_run_id = {}

# Создаём ассистента один раз

assistant_id = "asst_heHB29G3R8fmhgedCGVoafxo"

def save_data():
    with open("data.json", "w") as f:
        json.dump({
            "chat_to_thread_id": chat_to_thread_id,
            "chat_to_run_id": chat_to_run_id
        }, f)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = str(message.chat.id)
    user_input = message.text

    print(f"💬 {chat_id}: {user_input}")

    # Создаём thread_id, если нужно
    if chat_id not in chat_to_thread_id:
        thread = client.beta.threads.create()
        chat_to_thread_id[chat_id] = thread.id
        print(f"🧵 Создан новый thread: {thread.id}")
        save_data()

    thread_id = chat_to_thread_id[chat_id]

    # ⏳ Проверка: есть ли активный run?
    if chat_id in chat_to_run_id:
        current_run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=chat_to_run_id[chat_id]
        )
        if current_run.status in ["queued", "in_progress"]:
            try:
                bot.send_message(chat_id, "⏳ Подожди, я ещё думаю над предыдущим сообщением...")
            except Exception as e:
                print(f"❌ Ошибка при отправке предупреждения: {e}")
            return

    # Отправляем сообщение в OpenAI
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=user_input
    )

    # Запускаем run
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    # Сохраняем run_id для пользователя
    chat_to_run_id[chat_id] = run.id
    save_data()

    # Ждём завершения run
    while True:
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run.status == "completed":
            break

    # Получаем ответ
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    response = messages.data[0].content[0].text.value

    # Отправляем ответ в Telegram
    try:
        bot.send_message(chat_id, response)
    except Exception as e:
        print(f"❌ Ошибка при отправке сообщения в Telegram: {e}")

# Flask-сервер для UptimeRobot
app = Flask('')

@app.route('/')
def home():
    return "🤖 Бот онлайн!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# Запуск Flask в отдельном потоке
flask_thread = Thread(target=run_flask)
flask_thread.start()

if __name__ == "__main__":
    print("🚀 Бот запущен. Ждём сообщений в Telegram...")
    bot.polling(none_stop=True)
