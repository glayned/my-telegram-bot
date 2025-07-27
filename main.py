import telebot
from telebot.apihelper import ApiTelegramException
from openai import OpenAI
import os
from dotenv import load_dotenv
import time
import logging
import threading
from collections import defaultdict
from requests.exceptions import ProxyError, ConnectionError
from typing import cast
from openai.types.chat import ChatCompletionMessageParam

# Настройка логирования
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not all([OPENROUTER_API_KEY, TELEGRAM_BOT_TOKEN]):
    raise ValueError("OPENROUTER_API_KEY или TELEGRAM_BOT_TOKEN не установлены в переменных окружения")

# Инициализация клиентов
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)
BOT_USERNAME = bot.get_me().username

# Глобальные структуры
messages = defaultdict(list)
BOT_NAMES = ["жестянка", "железяка"]

# Настройки чатов
chat_settings = {
    -1001418076682: {
        "system_prompt": "Тебя зовут Жестянка. Ты находишься в чате астро-трейдеров под руководством Дмитрия Мальцева. Отвечай лаконично, с ноткой креативного юмора, по делу и по-русски.",
        "context_length": 5
    },
    -1002740607720: {
        "system_prompt": "Ты превосходный трейдер школы Мальцева. Дмитрий Мальцев трейдер практик, поэт и астролог научил разбираться в финансовых рынках, в том числе опционах и криптовалюте.",
        "context_length": 5
    }
}

DEFAULT_PROMPT = "Тебя зовут Жестянка. Ты прогрессивная Железяка. Находишься в удивительном лесу, где Белка главная среди зверей, которым она периодически дерёт хвосты. Здесь обитают: удивительный Алень, Волчара, лесной Крол, Медведь, лесной Лев с Антарктиды, гениальная Птица и прочие чудные обитатели, которые очень общительны и интересуются финансовым рынком. Отвечай лаконично, общайся креативно с юмором."

# Настройки контекста и ограничения по частоте
MAX_CONTEXT_LENGTH = 5
MAX_CONTEXT_AGE = 1800
RATE_LIMIT = 5
TIME_FRAME = 60
user_request_times = defaultdict(list)


def retry_with_backoff(func, max_retries=5, initial_delay=1, max_delay=60):
    def wrapper(*args, **kwargs):
        retries = 0
        delay = initial_delay
        if max_retries <= 0:
            return func(*args, **kwargs)
        while retries < max_retries:
            try:
                return func(*args, **kwargs)
            except (ProxyError, ConnectionError, ApiTelegramException) as e:
                retries += 1
                if retries == max_retries:
                    logger.error(f"Максимальное количество попыток исчерпано. Последняя ошибка: {e}")
                    raise
                logger.warning(f"Попытка {retries} не удалась. Ошибка: {e}. Повторная попытка через {delay} секунд.")
                time.sleep(delay)
                delay = min(delay * 2, max_delay)
        return func(*args, **kwargs)

    return wrapper


def rate_limited(user_id):
    current_time = time.time()
    user_times = [t for t in user_request_times[user_id] if current_time - t < TIME_FRAME]
    user_request_times[user_id] = user_times

    if len(user_times) >= RATE_LIMIT:
        wait_time = TIME_FRAME - (current_time - user_times[0])
        return True, round(wait_time)
    user_times.append(current_time)
    return False, 0


def trim_messages(chat_id, limit):
    current_time = time.time()
    messages[chat_id] = [
                            msg for msg in messages[chat_id]
                            if current_time - msg.get("timestamp", 0) < MAX_CONTEXT_AGE
                        ][-limit:]


def should_process_message(message):
    if not message.text:
        return False
    lower_text = message.text.lower()
    return (
            f"@{BOT_USERNAME}" in message.text or
            any(name in lower_text for name in BOT_NAMES) or
            (message.reply_to_message and
             message.reply_to_message.from_user and
             message.reply_to_message.from_user.username == BOT_USERNAME)
    )


@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if not message.text:
        return

    command = message.text.lower()
    if command.startswith('/'):
        if command == '/start':
            response = (
                f"⚡️ Хай-Лой! Я Железяка! 🤖 Для общения со мной просто упомяни "
                f"@{BOT_USERNAME}, вызвав по имени 'Жестянка' или процитируй моё сообщение, "
                "чтобы задать свой вопрос https://t.me/d1tradebot"
            )
        elif command == '/help':
            response = (
                "Я отвечаю на вопросы. Просто упомяни меня по имени, назвав меня 'Жестянка' "
                f"или 'Железяка', ответив на одно из сообщений @{BOT_USERNAME}."
            )
        else:
            return
        send_message_safely(message.chat.id, response)
    elif should_process_message(message):
        limited, wait = rate_limited(message.from_user.id)
        if limited:
            send_message_safely(message.chat.id, f"🚫 Слишком часто! 🤖 просит подождать {wait} сек.")
        else:
            process_message(message)


def send_typing_action(chat_id, stop_event):
    while not stop_event.is_set():
        try:
            bot.send_chat_action(chat_id, 'typing')
        except Exception as e:
            logger.error(f"Ошибка при отправке статуса набора текста: {str(e)}")
        time.sleep(4)


def split_message(text, max_length=4000):
    """Умная разбивка с сохранением структуры"""
    if not text or len(text) <= max_length:
        return [text] if text else [""]

    parts = []
    current = ""
    paragraphs = text.split('\n\n')

    if not paragraphs:
        paragraphs = [text]

    for paragraph in paragraphs:
        if len(current + paragraph + '\n\n') <= max_length:
            current += paragraph + '\n\n'
        else:
            if current:
                parts.append(current.strip())
                current = ""

            if len(paragraph) > max_length:
                sentences = paragraph.split('. ')
                for sentence in sentences:
                    if sentence.strip():
                        if sentence.endswith('.'):
                            sentence_processed = sentence + ' '
                        else:
                            sentence_processed = sentence + '. '

                        if len(current + sentence_processed) <= max_length:
                            current += sentence_processed
                        else:
                            if current:
                                parts.append(current.strip())
                            current = sentence_processed
            else:
                current = paragraph + '\n\n'

    if current:
        parts.append(current.strip())

    return parts if parts else [""]


@retry_with_backoff
def send_message_safely(chat_id, text, reply_to_message=None):
    try:
        if len(text) > 4096:
            parts = split_message(text, 4000)
            for i, part in enumerate(parts):
                if i == 0 and reply_to_message and time.time() - reply_to_message.date < 60:
                    bot.reply_to(reply_to_message, part)
                else:
                    bot.send_message(chat_id, part)
                time.sleep(0.3)
        else:
            if reply_to_message and time.time() - reply_to_message.date < 60:
                bot.reply_to(reply_to_message, text)
            else:
                bot.send_message(chat_id, text)
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {str(e)}")


def process_message(message):
    logger.info(f"Получено сообщение: ID={message.message_id}, Chat={message.chat.id}, Text={message.text}")
    chat_id = message.chat.id

    settings = chat_settings.get(chat_id, {})
    system_prompt = settings.get("system_prompt", DEFAULT_PROMPT)
    context_limit = settings.get("context_length", MAX_CONTEXT_LENGTH)

    user_message = message.text.replace(f"@{BOT_USERNAME}", "").strip()
    for name in BOT_NAMES:
        user_message = user_message.replace(name, "").strip()

    if len(user_message) > 1000:
        send_message_safely(chat_id, "Сообщение длинное! 🤖 просит использовать не более 1000 символов.")
        return

    messages[chat_id].append({"role": 'user', "content": user_message, "timestamp": time.time()})
    trim_messages(chat_id, context_limit)

    stop_event = threading.Event()
    typing_thread = threading.Thread(target=send_typing_action, args=(chat_id, stop_event))
    typing_thread.start()

    try:
        chat_history = cast(
            list[ChatCompletionMessageParam],
            [{"role": "system", "content": system_prompt}] + [
                {"role": m["role"], "content": m["content"]} for m in messages[chat_id]
            ]
        )

        completion = client.chat.completions.create(
            model="moonshotai/kimi-k2:free",
            messages=chat_history,
            max_tokens=1000
        )

        response = completion.choices[0].message.content
        if response:
            send_message_safely(chat_id, response, message)
            messages[chat_id].append({"role": 'assistant', "content": response, "timestamp": time.time()})
            trim_messages(chat_id, context_limit)
        else:
            send_message_safely(chat_id, "🤖 отказывается генерировать ответ! Попробуйте переформулировать вопрос.")
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {str(e)}")
        send_message_safely(chat_id, "🤖 глючит при обработке запроса, повторите попытку позднее")
    finally:
        stop_event.set()
        typing_thread.join(timeout=1)


def clean_old_data():
    current_time = time.time()
    for user_id in list(user_request_times.keys()):
        user_request_times[user_id] = [t for t in user_request_times[user_id] if current_time - t < TIME_FRAME]
        if not user_request_times[user_id]:
            del user_request_times[user_id]

    for chat_id in list(messages.keys()):
        msgs = messages[chat_id]
        if not msgs:
            del messages[chat_id]
        elif current_time - msgs[-1].get("timestamp", 0) > 3600:
            del messages[chat_id]


def start_cleaner(interval_seconds=300):
    def cleaner_loop():
        while True:
            try:
                clean_old_data()
            except Exception as e:
                logger.error(f"Ошибка при очистке данных: {e}")
            time.sleep(interval_seconds)

    thread = threading.Thread(target=cleaner_loop, daemon=True)
    thread.start()


def main():
    start_cleaner()  # Запуск фоновой очистки каждые 5 минут
    while True:
        try:
            logger.info("Бот запущен. Для остановки нажмите Ctrl+C.")
            bot.polling(none_stop=True, timeout=60)
        except ApiTelegramException as e:
            if e.error_code == 502:
                logger.error("Получена ошибка 502. Ожидание перед повторной попыткой...")
                time.sleep(30)
            else:
                logger.error(f"Ошибка Telegram API: {e}")
                time.sleep(10)
        except KeyboardInterrupt:
            logger.info("Получен сигнал прерывания. Завершение работы бота.")
            break
        except Exception as e:
            logger.error(f"Произошла ошибка в работе бота: {e}")
            time.sleep(15)


if __name__ == "__main__":
    main()
