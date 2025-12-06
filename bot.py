import telebot
from telebot import types
import datetime
import os
import pytz
import random
import psycopg2
from psycopg2.extras import RealDictCursor

# --- Инициализация БД ---
def init_database():
    """Создаёт таблицы если их нет"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    
    # Создаем базовую таблицу (без новых полей для обратной совместимости)
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
    
    conn.commit()
    print("✅ База данных инициализирована (базовая структура)")
    
    # Теперь добавляем новые поля если их нет
    print("🔧 Проверяем наличие новых полей...")
    
    # Список полей для добавления
    new_columns = [
        ('is_active', 'BOOLEAN DEFAULT FALSE'),
        ('is_paused', 'BOOLEAN DEFAULT FALSE'),
        ('pause_start_time', 'TIMESTAMP'),
        ('pause_duration_seconds', 'INTEGER DEFAULT 0'),
        ('awaiting_cash_input', 'BOOLEAN DEFAULT FALSE')
    ]
    
    for column_name, column_type in new_columns:
        try:
            cur.execute(f'''
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='shifts' AND column_name='{column_name}'
            ''')
            
            if not cur.fetchone():
                print(f"   Добавляем поле {column_name}...")
                cur.execute(f'ALTER TABLE shifts ADD COLUMN {column_name} {column_type}')
                conn.commit()
                print(f"   ✅ Поле {column_name} добавлено")
            else:
                print(f"   ✅ Поле {column_name} уже существует")
                
        except Exception as e:
            print(f"   ⚠️ Ошибка при добавлении поля {column_name}: {e}")
            conn.rollback()
    
    # Создаем индексы (после добавления всех полей)
    print("🔧 Создаем индексы...")
    
    try:
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_shifts_driver_id 
            ON shifts(driver_id)
        ''')
        print("   ✅ Индекс idx_shifts_driver_id создан")
    except Exception as e:
        print(f"   ⚠️ Ошибка при создании idx_shifts_driver_id: {e}")
    
    try:
        # Проверяем есть ли уже поле is_active перед созданием индекса
        cur.execute('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='shifts' AND column_name='is_active'
        ''')
        
        if cur.fetchone():
            cur.execute('''
                CREATE INDEX IF NOT EXISTS idx_shifts_active 
                ON shifts(driver_id, is_active) 
                WHERE is_active = TRUE
            ''')
            print("   ✅ Индекс idx_shifts_active создан")
        else:
            print("   ⏭️ Поле is_active отсутствует, индекс не создан")
    except Exception as e:
        print(f"   ⚠️ Ошибка при создании idx_shifts_active: {e}")
    
    cur.close()
    conn.close()
    print("🎉 Инициализация БД завершена!")

# --- Константы и утилиты ---
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
def get_moscow_time():
    return datetime.datetime.now(MOSCOW_TZ)

def format_seconds_to_words(seconds):
    """Переводит секунды в '8 часов 25 минут' с правильным склонением"""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    
    # Склонение для часов
    if hours == 1:
        hours_str = "час"
    elif 2 <= hours <= 4:
        hours_str = "часа"
    else:
        hours_str = "часов"
    
    # Склонение для минут
    if minutes == 1:
        minutes_str = "минута"
    elif 2 <= minutes <= 4:
        minutes_str = "минуты"
    else:
        minutes_str = "минут"
    
    return f"{hours} {hours_str} {minutes} {minutes_str}"

# --- Мотивационные сообщения ---
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

bot = telebot.TeleBot(os.environ['BOT_TOKEN'])

# --- Состояния пользователей ---
def get_user_state(user_id):
    user_states = {}
    """Возвращает состояние пользователя, создаёт если нет. Восстанавливает из БД если есть активная смена."""
    # Если уже есть в памяти - возвращаем
    if user_id in user_states:
        return user_states[user_id]
    
    # Проверяем БД на наличие активной смены
    active_shift = get_active_shift(user_id)
    
    if active_shift:
        # Восстанавливаем состояние из БД
        start_time = active_shift['start_time']
        if isinstance(start_time, str):
            start_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        
        user_states[user_id] = {
            'is_working': True,
            'shift_start_time': start_time,
            'is_paused': active_shift['is_paused'],
            'pause_start_time': active_shift.get('pause_start_time'),
            'awaiting_cash_input': active_shift.get('awaiting_cash_input', False),
            'pending_shift_data': None,
            'shift_id': active_shift['id']  # сохраняем ID смены для обновлений
        }
        
        # Если смена на паузе, корректируем время начала
        if active_shift['is_paused'] and active_shift.get('pause_start_time'):
            pause_start = active_shift['pause_start_time']
            if isinstance(pause_start, str):
                pause_start = datetime.datetime.fromisoformat(pause_start.replace('Z', '+00:00'))
            
            # Учитываем уже накопленное время пауз
            total_pause_seconds = active_shift.get('pause_duration_seconds', 0)
            if active_shift['pause_start_time']:
                current_pause = (get_moscow_time() - pause_start).total_seconds()
                total_pause_seconds += current_pause
            
            # Сдвигаем время начала на общее время пауз
            user_states[user_id]['shift_start_time'] -= datetime.timedelta(seconds=total_pause_seconds)
        
        print(f"✅ Восстановлено состояние из БД для пользователя {user_id}")
    else:
        # Нет активной смены - создаем новое состояние
        user_states[user_id] = {
            'is_working': False,
            'shift_start_time': None,
            'is_paused': False, 
            'pause_start_time': None,
            "awaiting_cash_input": False,
            "pending_shift_data": None,
            'shift_id': None
        }
    
    return user_states[user_id]

# --- Работа с БД ---
def save_shift_to_db(user_id, start_time, end_time, duration_str, cash, hourly_rate):
    """Сохраняет смену в PostgreSQL"""
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

def get_user_shifts_grouped_by_date(user_id):
    """Возвращает смены пользователя сгруппированные по дате (текущий месяц)"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Текущий месяц по московскому времени
    now_moscow = datetime.datetime.now(MOSCOW_TZ)
    month_start = now_moscow.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + datetime.timedelta(days=32)).replace(day=1)
    
    cur.execute('''
        SELECT 
            DATE(start_time AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow') as shift_date,
            COUNT(*) as shifts_count,
            SUM(duration_seconds) as total_seconds,
            SUM(cash) as total_cash,
            CASE 
                WHEN SUM(duration_seconds) > 0 
                THEN (SUM(cash) / (SUM(duration_seconds) / 3600.0))::INTEGER
                ELSE 0
            END as avg_hourly_rate
        FROM shifts 
        WHERE driver_id = %s 
          AND start_time >= %s
          AND start_time < %s
        GROUP BY DATE(start_time AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow')
        ORDER BY shift_date DESC
    ''', (user_id, month_start, month_end))
    
    shifts = cur.fetchall()
    cur.close()
    conn.close()
    return shifts

def get_active_shift(user_id):
    """Получает активную смену пользователя из БД"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute('''
        SELECT * FROM shifts 
        WHERE driver_id = %s 
          AND is_active = TRUE 
        ORDER BY start_time DESC 
        LIMIT 1
    ''', (user_id,))
    
    shift = cur.fetchone()
    cur.close()
    conn.close()
    return shift

def start_shift_in_db(user_id, start_time):
    """Создает новую активную смену в БД"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    
    # Сначала завершаем старые активные смены (на всякий случай)
    cur.execute('''
        UPDATE shifts 
        SET is_active = FALSE 
        WHERE driver_id = %s AND is_active = TRUE
    ''', (user_id,))
    
    # Создаем новую смену
    cur.execute('''
        INSERT INTO shifts 
        (driver_id, start_time, end_time, cash, hourly_rate, is_active)
        VALUES (%s, %s, %s, 0, 0, TRUE)
        RETURNING id
    ''', (user_id, start_time, start_time))
    
    shift_id = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"✅ Смена #{shift_id} создана для пользователя {user_id}")
    return shift_id

def update_shift_pause(user_id, is_paused, pause_start_time=None):
    """Обновляет состояние паузы в активной смене"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    
    if is_paused:
        cur.execute('''
            UPDATE shifts 
            SET is_paused = TRUE, 
                pause_start_time = %s
            WHERE driver_id = %s 
              AND is_active = TRUE
        ''', (pause_start_time, user_id))
    else:
        # Снимаем паузу и обновляем общее время пауз
        cur.execute('''
            UPDATE shifts 
            SET is_paused = FALSE,
                pause_duration_seconds = pause_duration_seconds + 
                    EXTRACT(EPOCH FROM (NOW() - pause_start_time))
            WHERE driver_id = %s 
              AND is_active = TRUE
        ''', (user_id,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"✅ Пауза обновлена для пользователя {user_id}")

def complete_shift_in_db(user_id, end_time, duration_str, cash, hourly_rate):
    """Завершает смену в БД"""
    duration_seconds = int((end_time - datetime.datetime.fromisoformat(str(end_time).replace('Z', '+00:00'))).total_seconds())
    
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE shifts 
        SET end_time = %s,
            duration_text = %s,
            duration_seconds = %s,
            cash = %s,
            hourly_rate = %s,
            is_active = FALSE,
            is_paused = FALSE,
            awaiting_cash_input = FALSE
        WHERE driver_id = %s 
          AND is_active = TRUE
        RETURNING id
    ''', (end_time, duration_str, duration_seconds, cash, hourly_rate, user_id))
    
    result = cur.fetchone()
    
    if result:
        shift_id = result[0]
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Смена #{shift_id} завершена для пользователя {user_id}")
        return True
    else:
        conn.rollback()
        cur.close()
        conn.close()
        print(f"❌ Не найдена активная смена для пользователя {user_id}")
        return False

def cleanup_old_states():
    """Очищает зависшие состояния (например, смены в режиме ожидания кассы больше 24 часов)"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    
    # Находим смены, которые ожидают ввода кассы больше 24 часов
    cur.execute('''
        UPDATE shifts 
        SET is_active = FALSE,
            awaiting_cash_input = FALSE,
            end_time = start_time + INTERVAL '1 hour'
        WHERE is_active = TRUE 
          AND awaiting_cash_input = TRUE
          AND created_at < NOW() - INTERVAL '24 hours'
        RETURNING id, driver_id
    ''')
    
    cleaned = cur.fetchall()
    
    if cleaned:
        print(f"🔄 Очищено {len(cleaned)} зависших состояний: {cleaned}")
    
    conn.commit()
    cur.close()
    conn.close()

# --- Мотивация ---
def send_motivation(chat_id, user_id):
    """Отправляет случайное мотивационное сообщение через 3 секунды"""
    import threading
    import time
    
    def motivation_timer():
        time.sleep(3)
        state = get_user_state(user_id)
        
        # Проверяем что смена активна и не на паузе
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT is_active, is_paused 
            FROM shifts 
            WHERE driver_id = %s 
            ORDER BY id DESC 
            LIMIT 1
        ''', (user_id,))
        shift_status = cur.fetchone()
        cur.close()
        conn.close()
        
        if shift_status and shift_status['is_active'] and not shift_status['is_paused']:
            message = random.choice(motivational_messages)
            bot.send_message(chat_id, message)
            print(f"✅ Мотивация отправлена пользователю {user_id}")
    
    timer_thread = threading.Thread(target=motivation_timer)
    timer_thread.daemon = True
    timer_thread.start()

# --- Команды бота ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button_start = types.KeyboardButton('В бой! Начать смену')
    button_pause = types.KeyboardButton('Пауза/Продолжить')
    button_end = types.KeyboardButton('Завершить смену')
    button_history = types.KeyboardButton('📊 Мои смены')
    markup.add(button_start, button_pause, button_end, button_history)

    bot.send_message(message.chat.id, 'Что делаем? Воин:', reply_markup=markup)

@bot.message_handler(func=lambda message: get_user_state(message.from_user.id)['awaiting_cash_input'])
def handle_cash_input(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    try:
        cash = int(message.text)
        if cash < 0:
            raise ValueError("Отрицательная сумма")
        
        data = state['pending_shift_data']
        shift_duration = data['end_time'] - data['start_time']
        total_seconds = shift_duration.total_seconds()
        hours_worked = total_seconds / 3600
        
        if hours_worked > 0:
            hourly_rate = cash / hours_worked
            hourly_rate_rounded = int(hourly_rate)
            hourly_rate_str = f"{hourly_rate_rounded} в час"
        else:
            hourly_rate_rounded = 0
            hourly_rate_str = "0 в час"
        
        # Завершаем смену в БД
        success = complete_shift_in_db(
            user_id,
            data['end_time'],
            data['duration_str'],
            cash,
            hourly_rate_rounded
        )
        
        if success:
            # Сбрасываем состояние
            state['is_working'] = False
            state['shift_start_time'] = None
            state['is_paused'] = False
            state['pause_start_time'] = None
            state['awaiting_cash_input'] = False
            state['pending_shift_data'] = None
            state['shift_id'] = None
            
            bot.send_message(message.chat.id,
                           f"✅ Смена завершена!\n"
                           f"⏱ Отработано: {data['duration_str']}\n"
                           f"💰 Касса: {cash} руб\n"
                           f"📊 Средний час: {hourly_rate_str}")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при сохранении смены")
        
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
            start_time = get_moscow_time()
            shift_id = start_shift_in_db(user_id, start_time)
            
            if shift_id:
                state['is_working'] = True
                state['shift_start_time'] = start_time
                state['shift_id'] = shift_id
                state['is_paused'] = False
                state['pause_start_time'] = None
                state['awaiting_cash_input'] = False
                
                bot.send_message(message.chat.id, "Смена начата! 🚕")
                send_motivation(message.chat.id, user_id)
            else:
                bot.send_message(message.chat.id, "❌ Ошибка при начале смены")
        else:
            bot.send_message(message.chat.id, "Смена уже начата!")
    
    elif message.text == 'Пауза/Продолжить':
        if not state['is_working']:
            bot.send_message(message.chat.id, "❌ Смена не начата")
            return
        
        current_time = get_moscow_time()
        
        if not state['is_paused']:
            # Ставим на паузу
            state['is_paused'] = True
            state['pause_start_time'] = current_time
            
            # Обновляем в БД
            update_shift_pause(user_id, True, current_time)
            
            bot.send_message(message.chat.id, "⏸ Смена на паузе")
            
        else:
            # Снимаем с паузы
            pause_duration = current_time - state['pause_start_time']
            
            # Обновляем время начала с учетом паузы
            state['shift_start_time'] += pause_duration
            state['is_paused'] = False
            state['pause_start_time'] = None
            
            # Обновляем в БД
            update_shift_pause(user_id, False, None)
            
            bot.send_message(message.chat.id, "▶ Смена продолжена")
    
    elif message.text == 'Завершить смену':
        if not state['is_working']:
            bot.send_message(message.chat.id, "❌ Смена не начата")
            return
        
        end_time = get_moscow_time()
        
        # Вычисляем чистое рабочее время (исключая паузы)
        if state['is_paused']:
            # Если на паузе, считаем до начала паузы
            work_duration = state['pause_start_time'] - state['shift_start_time']
        else:
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
        
        # Помечаем в БД что ожидаем ввод кассы
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        cur.execute('''
            UPDATE shifts 
            SET awaiting_cash_input = TRUE,
                end_time = %s
            WHERE driver_id = %s AND is_active = TRUE
        ''', (end_time, user_id))
        conn.commit()
        cur.close()
        conn.close()
        
        bot.send_message(message.chat.id, 
                       f"⏱ Отработано: {time_str}\n"
                       "💵 Введите сумму в кассе:")
    
    elif message.text == '📊 Мои смены':
        shifts = get_user_shifts_grouped_by_date(user_id)
        
        if not shifts:
            month_name = datetime.datetime.now(MOSCOW_TZ).strftime('%B').lower()
            bot.send_message(message.chat.id, f"📭 В {month_name} пока нет завершенных смен")
            return
        
        response = "📊 Ваши смены в этом месяце:\n\n"
        
        for shift in shifts:
            date_str = shift['shift_date'].strftime('%d.%m.%Y')
            
            # Форматируем время
            time_str = format_seconds_to_words(shift['total_seconds'])
            
            response += f"📅 {date_str}\n"
            response += f"⏱ {time_str}  |  💰 {shift['total_cash']} руб  |  📊 {shift['avg_hourly_rate']} в час\n\n"
        
        # Статистика за месяц
        total_shifts = sum(s['shifts_count'] for s in shifts)
        total_cash = sum(s['total_cash'] for s in shifts)
        total_seconds = sum(s['total_seconds'] for s in shifts)
        
        total_time_str = format_seconds_to_words(total_seconds)
        
        response += "────────────────\n"
        response += f"📈 Итого за месяц:\n"
        response += f"{total_shifts} смены / {total_cash} руб"
        
        bot.send_message(message.chat.id, response)

# Запуск бота с восстановлением состояний
print("✅ Бот запущен с PostgreSQL!")

# Очищаем старые зависшие состояния
cleanup_old_states()

# Восстанавливаем активные смены из БД при запуске
print("🔄 Восстанавливаем активные смены из БД...")
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("SELECT DISTINCT driver_id FROM shifts WHERE is_active = TRUE")
active_drivers = cur.fetchall()
cur.close()
conn.close()

for driver in active_drivers:
    user_id = driver['driver_id']
    get_user_state(user_id)  # Это восстановит состояние из БД
    print(f"   Восстановлена смена для водителя {user_id}")

print(f"✅ Восстановлено {len(active_drivers)} активных смен")

import time

while True:
    try:
        print("🤖 Запускаю бота...")
        bot.polling(
            none_stop=True,      # не останавливаться при ошибках
            interval=3,          # интервал между запросами
            timeout=30,          # таймаут соединения
            long_polling_timeout=20  # таймаут long-polling
        )
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
        break
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
        print("🔄 Перезапуск через 15 секунд...")
        time.sleep(15)