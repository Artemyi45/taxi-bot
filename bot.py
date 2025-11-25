import telebot
from telebot import types
import datetime
import json
import os

def save_shift_to_json(user_id, start_time, end_time, duration_str):
    """Сохраняет данные о смене в JSON файл"""
    
    # Создаём данные для сохранения
    shift_data = {
        "user_id": user_id,
        "start_time": start_time.isoformat(),  # Преобразуем время в строку
        "end_time": end_time.isoformat(),
        "duration": duration_str,
        "date": datetime.datetime.now().strftime("%Y-%m-%d")
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

is_working = False
shift_start_time = None

bot = telebot.TeleBot(os.environ['BOT_TOKEN'])

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button_start = types.KeyboardButton('Начать смену')
    button_end = types.KeyboardButton('Завершить смену')
    markup.add(button_start, button_end)

    bot.send_message(message.chat.id,
                     'Выбери действие:',
                     reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    global is_working, shift_start_time
    
    if message.text == 'Начать смену':
        if not is_working:
            is_working = True
            shift_start_time = datetime.datetime.now()
            bot.send_message(message.chat.id, "Смена начата! 🚕")
        else:
            bot.send_message(message.chat.id, "Смена уже начата!")
    
    elif message.text == 'Завершить смену':
        if is_working:
            # Считаем разницу времени
            end_time = datetime.datetime.now()
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
            
            bot.send_message(message.chat.id, 
                           f"Смена завершена! ✅\n"
                           f"Отработано: {time_str}")
        else:
            bot.send_message(message.chat.id, "Смена не начата!")


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

print("✅ Бот запущен с сохранением в JSON!")
bot.polling()
