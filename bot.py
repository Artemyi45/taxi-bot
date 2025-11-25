import telebot
from telebot import types
import datetime
import json
import os
import pytz
import random

import random

motivational_messages = [
    "Воин, 30 секунд в строю! Ты — повелитель асфальта и король маршрутов! 👑",
    "30 секунд — и ты уже непобедим! Дорога боится сильных! ⚔️",
    "Таксюга, ты запустил не просто двигатель — ты запустил механизм успеха! 🚀",
    "Каждая секунда за рулем — это кирпичик в фундаменте твоего благополучия! 🏗️",
    "Ты не просто таксист — ты проводник людей к их мечтам! ✨",
    "30 секунд — и ты уже на 1% ближе к своим целям! 💪",
    "30 секунд работы! Скоро сможешь купить себе личный светофор! 🚦",
    "Таксюга, не гони — но и не тормози! Уже 30 секунд в пути! 🚗💨",
    "30 секунд — и пассажиры уже выстраиваются в очередь к тебе! 📈",
    "Дорога — это жизнь. Ты не просто едешь — ты живёшь! 🌅",
    "30 секунд назад ты принял решение изменить свой день. Горжусь тобой! 🤝",
    "Каждый поворот руля — это новый поворот судьбы! 🌀",
    "Ты справился с самым сложным — началом! Теперь всё пойдет как по маслу! 🛢️",
    "30 секунд — и ты уже победил свою лень! Это достойно уважения! 🏆",
    "Помни: даже самые длинные маршруты начинаются с первого метра! 🛣️",
    "30 секунд — первая ступень к финансовой свободе! 🤑",
    "Ты не работаешь — ты создаёшь свою империю на колесах! 🏰",
    "Каждый клиент — это новая возможность стать лучше! 🌟",
    "Город спит, а ты — нет. Ты — его ночной ангел-хранитель! 😇",
    "30 секунд мужества — и ты уже герой для кого-то сегодня! 🦸‍♂️",
    "Ты даришь людям не просто поездки — ты даришь время! ⏰"
]

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def get_moscow_time():
    return datetime.datetime.now(MOSCOW_TZ)

is_working = False
shift_start_time = None
is_paused = False
pause_start_time = None

bot = telebot.TeleBot(os.environ['BOT_TOKEN'])

def save_shift_to_json(user_id, start_time, end_time, duration_str):
    
    # Создаём данные для сохранения
    shift_data = {
        "user_id": user_id,
        "start_time": start_time.isoformat(),  # Преобразуем время в строку
        "end_time": end_time.isoformat(),
        "duration": duration_str,
        "date": get_moscow_time().strftime("%Y-%m-%d")
    }
    
    # Читаем существующие данные или создаём новые
    try:
        with open('shifts.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"shifts": []}  # Создаём структуру если файла нет
    
    # Добавляем новую смену
    data["shifts"].append(shift_data)
    
    # Сохраняем обратно в файл
    with open('shifts.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Смена сохранена в JSON для пользователя {user_id}")


def send_motivation(chat_id):
    """Отправляет случайное мотивационное сообщение через 30 секунд"""
    import threading
    import time
    
    def motivation_timer():
        time.sleep(30)  # Ждём 30 секунд
        
        # Проверяем что смена ещё активна и не на паузе
        if is_working and not is_paused:
            message = random.choice(motivational_messages)
            bot.send_message(chat_id, message)
            print(f"✅ Мотивация отправлена пользователю {chat_id}")
    
    # Запускаем таймер в отдельном потоке
    timer_thread = threading.Thread(target=motivation_timer)
    timer_thread.daemon = True
    timer_thread.start()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button_start = types.KeyboardButton('В бой! Начать смену')
    button_pause = types.KeyboardButton('Пауза/Продолжить')
    button_end = types.KeyboardButton('Завершить смену')
    markup.add(button_start, button_pause, button_end)

    bot.send_message(message.chat.id,
                     'Что делаем? Воин:',
                     reply_markup=markup)
    

@bot.message_handler(commands=['download'])
def download_json(message):
    """Отправляет файл shifts.json пользователю"""
    try:
        # Проверяем существует ли файл
        if not os.path.exists('shifts.json'):
            bot.reply_to(message, "📭 Файл shifts.json пока не создан")
            return
        
        # Читаем файл
        with open('shifts.json', 'r', encoding='utf-8') as f:
            json_data = f.read()
        
        # Создаём временный файл для отправки
        with open('temp_shifts.json', 'w', encoding='utf-8') as f:
            f.write(json_data)
        
        # Отправляем файл
        with open('temp_shifts.json', 'rb') as f:
            bot.send_document(message.chat.id, f, caption="📊 Данные ваших смен")
        
        # Удаляем временный файл
        os.remove('temp_shifts.json')
        
        print(f"✅ Файл отправлен пользователю {message.from_user.id}")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при отправке файла: {e}")
        print(f"❌ Ошибка: {e}")

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    global is_working, shift_start_time, is_paused, pause_start_time
    
    if message.text == 'В бой! Начать смену':
        if not is_working:
            is_working = True
            shift_start_time = get_moscow_time()
            bot.send_message(message.chat.id, "Смена начата! 🚕")
            # ЗАПУСКАЕМ ТАЙМЕР МОТИВАЦИИ - добавляем эту строку
            send_motivation(message.chat.id)
        else:
            bot.send_message(message.chat.id, "Смена уже начата!")
    
    elif message.text == 'Пауза/Продолжить':
        if is_working and not is_paused:
            # Ставим на паузу
            is_paused = True
            pause_start_time = get_moscow_time()
            bot.send_message(message.chat.id, "⏸ Смена на паузе")
            
        elif is_working and is_paused:
            # Продолжаем смену
            is_paused = False
            # КОРРЕКТИРУЕМ время начала смены на время паузы
            pause_duration = get_moscow_time() - pause_start_time
            shift_start_time += pause_duration
            bot.send_message(message.chat.id, "▶ Смена продолжена")
            
        else:
            bot.send_message(message.chat.id, "❌ Смена не начата")

    elif message.text == 'Завершить смену':
        if is_working:
            # Считаем разницу времени
            end_time = get_moscow_time()
            work_duration = end_time - shift_start_time
            total_seconds = work_duration.total_seconds()
            
            # Переводим в часы и минуты
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            
            # Форматируем вывод
            if hours > 0 and minutes > 0:
                time_str = f"{hours} ч {minutes} мин"
            elif hours > 0:
                time_str = f"{hours} ч"
            else:
                time_str = f"{minutes} мин"
            
            # СОХРАНЯЕМ В JSON
            save_shift_to_json(message.from_user.id, shift_start_time, end_time, time_str)
            
            # Сбрасываем состояние
            is_working = False
            shift_start_time = None
            is_paused = False
            pause_start_time = None
            
            bot.send_message(message.chat.id, 
                           f"Смена завершена! ✅\n"
                           f"Отработано: {time_str}")
        else:
            bot.send_message(message.chat.id, "Смена не начата!")

print("✅ Бот запущен с сохранением в JSON!")
bot.polling()
