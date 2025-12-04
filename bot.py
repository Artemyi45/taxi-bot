import telebot
from telebot import types
import datetime
import os
import pytz
import random
import psycopg2
from psycopg2.extras import RealDictCursor

def init_database():
    """Создаёт таблицы если их нет"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS shifts (
            id SERIAL PRIMARY KEY,
            driver_id BIGINT NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            duration_text VARCHAR(50),
            duration_seconds INTEGER,
            cash INTEGER NOT NULL CHECK (cash >= 0),
            hourly_rate INTEGER CHECK (hourly_rate >= 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE INDEX IF NOT EXISTS idx_shifts_driver_id 
        ON shifts(driver_id)
    ''')
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ База данных инициализирована")

# Инициализируем БД при старте
init_database()

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
    "Ты справился с самым сложным — началом! Теперь всё пойдет как по масу! 🛢️",
    "30 секунд — и ты уже победил свою лень! Это достойно уважения! 🏆",
    "Помни: даже самые длинные маршруты начинаются с первого метра! 🛣️",
    "30 секунд — первая ступень к финансовой свободе! 🤑",
    "Ты не работаешь — ты создаёшь свою империю на колесах! 🏰",
    "Каждый клиент — это новая возможность стать лучше! 🌟",
    "Город спит, а ты — нет. Ты — его ночной ангел-хранитель! 😇",
    "30 секунд мужества — и ты уже герой для кого-то сегодня! 🦸‍♂️",
    "Ты даришь людям не просто поездки — ты даришь время! ⏰"
]

bot = telebot.TeleBot(os.environ['BOT_TOKEN'])

MOSCOW_TZ = pytz.timezone('Europe/Moscow')
def get_moscow_time():
    return datetime.datetime.now(MOSCOW_TZ)

user_states = {}
def get_user_state(user_id):
    """Возвращает состояние пользователя, создаёт если нет"""
    if user_id not in user_states:
        user_states[user_id] = {
            'is_working': False,
            'shift_start_time': None,
            'is_paused': False, 
            'pause_start_time': None,
            "awaiting_cash_input": False,
            "pending_shift_data": None
        }
    return user_states[user_id]

def save_shift_to_db(user_id, start_time, end_time, duration_str, cash, hourly_rate):
    """Сохраняет смену в PostgreSQL"""
    # Вычисляем duration_seconds
    duration_seconds = int((end_time - start_time).total_seconds())
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO shifts 
        (driver_id, start_time, end_time, duration_text, duration_seconds, cash, hourly_rate)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (user_id, start_time, end_time, duration_str, duration_seconds, cash, hourly_rate))
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Смена сохранена в БД для пользователя {user_id}")

def get_user_shifts(user_id, limit=10):
    """Возвращает последние смены пользователя"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute('''
        SELECT start_time, duration_text, cash, hourly_rate
        FROM shifts 
        WHERE driver_id = %s 
        ORDER BY start_time DESC 
        LIMIT %s
    ''', (user_id, limit))
    
    shifts = cur.fetchall()
    cur.close()
    conn.close()
    return shifts

def send_motivation(chat_id, user_id):
    """Отправляет случайное мотивационное сообщение через 3 секунды"""
    import threading
    import time
    
    def motivation_timer():
        time.sleep(3)  # Ждём 3 секунды
        
        # Проверяем состояние КОНКРЕТНОГО пользователя
        state = get_user_state(user_id)
        if state['is_working'] and not state['is_paused']:
            message = random.choice(motivational_messages)
            bot.send_message(chat_id, message)
            print(f"✅ Мотивация отправлена пользователю {user_id}")
    
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
    button_history = types.KeyboardButton('📊 Мои смены')
    markup.add(button_start, button_pause, button_end, button_history)

    bot.send_message(message.chat.id,
                     'Что делаем? Воин:',
                     reply_markup=markup)

@bot.message_handler(func=lambda message: get_user_state(message.from_user.id)['awaiting_cash_input'])
def handle_cash_input(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    try:
        # Пробуем преобразовать в число
        cash = int(message.text)
        if cash < 0:
            raise ValueError("Отрицательная сумма")
        
        # Достаём временные данные смены
        data = state['pending_shift_data']
        
        # РАСЧЁТ СРЕДНЕГО ЧАСА
        shift_duration = data['end_time'] - data['start_time']
        total_seconds = shift_duration.total_seconds()
        hours_worked = total_seconds / 3600
        
        if hours_worked > 0:
            hourly_rate = cash / hours_worked
            hourly_rate_rounded = int(hourly_rate)
            hourly_rate_str = f"{hourly_rate_rounded}₽/ч"
        else:
            hourly_rate_rounded = 0
            hourly_rate_str = "0₽/ч"
        
        # Сохраняем в БД
        save_shift_to_db(
            user_id,
            data['start_time'],
            data['end_time'],
            data['duration_str'],
            cash,
            hourly_rate_rounded
        )
        
        # Сбрасываем состояние
        state['is_working'] = False
        state['shift_start_time'] = None
        state['is_paused'] = False
        state['pause_start_time'] = None
        state['awaiting_cash_input'] = False
        state['pending_shift_data'] = None
        
        # Сообщаем об успехе
        bot.send_message(message.chat.id,
                       f"✅ Смена завершена!\n"
                       f"⏱ Отработано: {data['duration_str']}\n"
                       f"💰 Касса: {cash}₽\n"
                       f"📊 Средний час: {hourly_rate_str}")
        
    except ValueError:
        bot.send_message(message.chat.id, 
                       "❌ Введите корректную сумму (целое число, не меньше 0)\n"
                       "💵 Введите сумму в кассе:")
        return

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    print(f"🔍 Получено сообщение: '{message.text}' от пользователя {user_id}")
    
    if message.text == 'В бой! Начать смену':
        if not state['is_working']:
            state['is_working'] = True
            state['shift_start_time'] = get_moscow_time()
            bot.send_message(message.chat.id, "Смена начата! 🚕")
            send_motivation(message.chat.id, user_id)
        else:
            bot.send_message(message.chat.id, "Смена уже начата!")
    
    elif message.text == 'Пауза/Продолжить':
        if state['is_working'] and not state['is_paused']:
            state['is_paused'] = True
            state['pause_start_time'] = get_moscow_time()
            bot.send_message(message.chat.id, "⏸ Смена на паузе")
            
        elif state['is_working'] and state['is_paused']:
            state['is_paused'] = False
            pause_duration = get_moscow_time() - state['pause_start_time']
            state['shift_start_time'] += pause_duration
            bot.send_message(message.chat.id, "▶ Смена продолжена")
            
        else:
            bot.send_message(message.chat.id, "❌ Смена не начата")

    elif message.text == 'Завершить смену':
        if state['is_working']:
            end_time = get_moscow_time()
            work_duration = end_time - state['shift_start_time']
            total_seconds = work_duration.total_seconds()
            
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            
            if hours > 0 and minutes > 0:
                time_str = f"{hours} ч {minutes} мин"
            elif hours > 0:
                time_str = f"{hours} ч"
            else:
                time_str = f"{minutes} мин"
            
            state['pending_shift_data'] = {
                'start_time': state['shift_start_time'],
                'end_time': end_time,
                'duration_str': time_str
            }
            
            state['awaiting_cash_input'] = True
            
            bot.send_message(message.chat.id, 
                           f"⏱ Отработано: {time_str}\n"
                           "💵 Введите сумму в кассе:")
            
        else:
            bot.send_message(message.chat.id, "Смена не начата!")
    
    elif message.text == '📊 Мои смены':
        shifts = get_user_shifts(user_id, limit=5)
        
        if not shifts:
            bot.send_message(message.chat.id, "📭 У вас пока нет завершенных смен")
            return
        
        response = "📊 Ваши последние смены:\n\n"
        
        for shift in shifts:
            date_str = shift['start_time'].strftime('%d.%m.%Y')
            response += f"📅 {date_str}\n"
            response += f"⏱ {shift['duration_text']} | 💰 {shift['cash']}₽ | 📊 {shift['hourly_rate']}₽/ч\n\n"
        
        # Добавляем общую статистику
        total_cash = sum(s['cash'] for s in shifts)
        avg_hourly = sum(s['hourly_rate'] for s in shifts) // len(shifts) if shifts else 0
        
        response += f"📈 Итого (последние {len(shifts)} смен):\n"
        response += f"💰 Общая касса: {total_cash}₽\n"
        response += f"📊 Средний час: {avg_hourly}₽/ч"
        
        bot.send_message(message.chat.id, response)

print("✅ Бот запущен с PostgreSQL и историей смен!")
bot.polling()