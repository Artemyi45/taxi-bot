import telebot
from telebot import types
import datetime
import os
import pytz
import random
import psycopg2
from psycopg2.extras import RealDictCursor

# Добавь в начало бота после инициализации
print("🧪 Тест часового пояса:")
test_time = get_moscow_time()
print(f"Московское время: {test_time}")
print(f"UTC время: {test_time.astimezone(pytz.UTC)}")
print(f"Naive для БД: {ensure_timezone_naive(test_time)}")

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

init_database()

# --- Константы и утилиты ---
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
def get_moscow_time():
    """Возвращает текущее время по Москве (UTC+3)"""
    utc_now = datetime.datetime.now(pytz.UTC)
    return utc_now.astimezone(MOSCOW_TZ)

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

def ensure_timezone_aware(dt, timezone=MOSCOW_TZ):
    """Гарантирует, что datetime имеет часовой пояс"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return timezone.localize(dt)
    return dt.astimezone(timezone)

def ensure_timezone_naive(dt):
    """Гарантирует, что datetime не имеет часового пояса (для БД)"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(pytz.UTC).replace(tzinfo=None)
    return dt

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
user_states = {}

def get_active_shift(user_id):
    """Получает активную смену пользователя из БД"""
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Сначала проверяем есть ли поле is_active в таблице
        cur.execute('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='shifts' AND column_name='is_active'
        ''')
        
        has_is_active = cur.fetchone()
        
        if not has_is_active:
            print(f"⚠️ Поле is_active отсутствует в таблице для пользователя {user_id}")
            cur.close()
            conn.close()
            return None
        
        # Проверяем есть ли активные смены у пользователя
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
        
        if shift:
            print(f"✅ Найдена активная смена в БД для пользователя {user_id}")
            print(f"   ID смены: {shift['id']}")
            print(f"   Начало: {shift['start_time']}")
            print(f"   Пауза: {'Да' if shift['is_paused'] else 'Нет'}")
            return shift
        else:
            print(f"📭 Нет активных смен в БД для пользователя {user_id}")
            return None
            
    except psycopg2.Error as e:
        print(f"❌ Ошибка PostgreSQL при получении активной смены: {e}")
        return None
    except Exception as e:
        print(f"❌ Неожиданная ошибка при получении активной смены: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_user_state(user_id):
    """Возвращает состояние пользователя, создаёт если нет. Восстанавливает из БД если есть активная смена."""
    # Если уже есть в памяти - возвращаем
    if user_id in user_states:
        print(f"📦 Используем состояние из памяти для пользователя {user_id}")
        return user_states[user_id]
    
    # Проверяем БД на наличие активной смены
    print(f"🔍 Проверяем БД на активные смены для пользователя {user_id}")
    active_shift = get_active_shift(user_id)
    
    # ВАЖНО: Проверяем что active_shift не None и является словарем
    if not active_shift or not isinstance(active_shift, dict):
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
        print(f"🆕 Создано новое состояние для пользователя {user_id}")
        return user_states[user_id]
    
    # Восстанавливаем состояние из БД
    try:
        start_time = active_shift.get('start_time')
        if not start_time:
            print(f"❌ Нет start_time в данных смены для пользователя {user_id}")
            # Создаем новое состояние при ошибке данных
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
        
        if isinstance(start_time, str):
            start_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        
        # Приводим start_time к aware (с часовым поясом)
        if start_time.tzinfo is None:
            start_time = MOSCOW_TZ.localize(start_time)
        else:
            # Если уже имеет пояс, конвертируем в московский
            start_time = start_time.astimezone(MOSCOW_TZ)
        
        user_states[user_id] = {
            'is_working': True,
            'shift_start_time': start_time,
            'is_paused': active_shift.get('is_paused', False),
            'pause_start_time': active_shift.get('pause_start_time'),
            'awaiting_cash_input': active_shift.get('awaiting_cash_input', False),
            'pending_shift_data': None,  # Всегда None при восстановлении
            'shift_id': active_shift.get('id')  # сохраняем ID смены для обновлений
        }
        
        print(f"✅ Восстановлено состояние из БД для пользователя {user_id}")
        print(f"   ID смены: {active_shift.get('id')}")
        print(f"   Начало: {start_time.strftime('%d.%m.%Y %H:%M')}")
        print(f"   Пауза: {'Да' if user_states[user_id]['is_paused'] else 'Нет'}")
        print(f"   Ожидает кассу: {'Да' if user_states[user_id]['awaiting_cash_input'] else 'Нет'}")
        
        # --- ВАЖНОЕ ИСПРАВЛЕНИЕ: ---
        # Если смена ожидает кассу, но у нас нет данных - сбрасываем флаг
        if user_states[user_id]['awaiting_cash_input'] and not user_states[user_id].get('pending_shift_data'):
            print(f"⚠️ Восстановлена смена в состоянии ожидания кассы без данных. Сбрасываем флаг.")
            user_states[user_id]['awaiting_cash_input'] = False
            
            # Обновляем в БД
            try:
                conn = psycopg2.connect(os.environ['DATABASE_URL'])
                cur = conn.cursor()
                cur.execute('''
                    UPDATE shifts 
                    SET awaiting_cash_input = FALSE
                    WHERE driver_id = %s AND is_active = TRUE
                ''', (user_id,))
                conn.commit()
                cur.close()
                conn.close()
                print(f"   ✅ Сброшен awaiting_cash_input в БД")
            except Exception as e:
                print(f"   ❌ Ошибка при обновлении БД: {e}")
        
        # Если смена на паузе, корректируем время начала
        if user_states[user_id]['is_paused'] and active_shift.get('pause_start_time'):
            pause_start = active_shift['pause_start_time']
            if isinstance(pause_start, str):
                pause_start = datetime.datetime.fromisoformat(pause_start.replace('Z', '+00:00'))
            
            # Приводим pause_start к aware
            if pause_start.tzinfo is None:
                pause_start = MOSCOW_TZ.localize(pause_start)
            else:
                pause_start = pause_start.astimezone(MOSCOW_TZ)
            
            user_states[user_id]['pause_start_time'] = pause_start
            
            # Учитываем уже накопленное время пауз
            total_pause_seconds = active_shift.get('pause_duration_seconds', 0)
            
            # Добавляем текущую паузу
            current_time = get_moscow_time()
            current_pause = (current_time - pause_start).total_seconds()
            total_pause_seconds += current_pause
            
            print(f"   ⏸ Смена на паузе. Накоплено пауз: {total_pause_seconds:.0f} сек")
            
            # Сдвигаем время начала на общее время пауз
            user_states[user_id]['shift_start_time'] -= datetime.timedelta(seconds=total_pause_seconds)
            print(f"   Скорректировано время начала с учетом пауз")
        
    except KeyError as e:
        print(f"❌ Ошибка ключа в данных смены: {e}")
        # Создаем новое состояние при ошибке данных
        user_states[user_id] = {
            'is_working': False,
            'shift_start_time': None,
            'is_paused': False, 
            'pause_start_time': None,
            "awaiting_cash_input": False,
            "pending_shift_data": None,
            'shift_id': None
        }
    except Exception as e:
        print(f"❌ Неожиданная ошибка при восстановлении состояния: {e}")
        import traceback
        traceback.print_exc()
        # Создаем новое состояние при ошибке
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
    try:
        # Конвертируем времена в offset-naive для БД
        if start_time.tzinfo is not None:
            start_time = start_time.astimezone(pytz.UTC).replace(tzinfo=None)
        if end_time.tzinfo is not None:
            end_time = end_time.astimezone(pytz.UTC).replace(tzinfo=None)
        
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
    except Exception as e:
        print(f"❌ Ошибка при сохранении смены: {e}")
        import traceback
        traceback.print_exc()

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

def start_shift_in_db(user_id, start_time):
    """Создает новую активную смену в БД"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    
    try:
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
    except Exception as e:
        print(f"❌ Ошибка при создании смены: {e}")
        conn.rollback()
        cur.close()
        conn.close()
        return None

def update_shift_pause(user_id, is_paused, pause_start_time=None):
    """Обновляет состояние паузы в активной смене"""
    try:
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
    except Exception as e:
        print(f"❌ Ошибка при обновлении паузы: {e}")

def complete_shift_in_db(user_id, start_time, end_time, duration_str, cash, hourly_rate):
    """Завершает смену в БД"""
    try:
        # Конвертируем времена в offset-naive для БД
        start_time_naive = ensure_timezone_naive(start_time)
        end_time_naive = ensure_timezone_naive(end_time)
        
        # Считаем длительность
        duration_seconds = int((end_time_naive - start_time_naive).total_seconds())
        
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        
        # Завершаем смену, обновляя start_time
        cur.execute('''
            UPDATE shifts 
            SET start_time = %s,
                end_time = %s,
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
        ''', (start_time_naive, end_time_naive, duration_str, duration_seconds, cash, hourly_rate, user_id))
        
        shift_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Смена #{shift_id} завершена для пользователя {user_id}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при завершении смены: {e}")
        import traceback
        traceback.print_exc()
        return False

def cleanup_old_states():
    """Очищает зависшие состояния (например, смены в режиме ожидания кассы больше 24 часов)"""
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        
        # Проверяем есть ли поле is_active в таблице
        cur.execute('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='shifts' AND column_name='is_active'
        ''')
        
        if not cur.fetchone():
            print("⚠️ Поле is_active отсутствует, очистка не требуется")
            cur.close()
            conn.close()
            return
        
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
        else:
            print("✅ Нет зависших состояний для очистки")
        
        conn.commit()
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"⚠️ Ошибка при очистке старых состояний: {e}")

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

@bot.message_handler(func=lambda message: 
    get_user_state(message.from_user.id).get('awaiting_cash_input', False) == True)
def handle_cash_input(message):
    try:
        user_id = message.from_user.id
        print(f"💰 Обрабатываем ввод кассы от пользователя {user_id}")
        
        state = get_user_state(user_id)
        print(f"📊 Состояние: awaiting_cash_input={state.get('awaiting_cash_input')}")
        print(f"📊 pending_shift_data: {state.get('pending_shift_data')}")
        
        # Проверяем наличие данных
        if not state.get('pending_shift_data'):
            print(f"❌ Нет данных о смене для пользователя {user_id}")
            state['awaiting_cash_input'] = False
            bot.send_message(message.chat.id, 
                           "❌ Ошибка: данные смены не найдены.\n"
                           "Начните новую смену командой 'В бой! Начать смену'")
            return
        
        data = state['pending_shift_data']
        
        # Проверяем наличие всех необходимых полей
        if not data.get('start_time') or not data.get('end_time'):
            print(f"❌ Неполные данные о смене: {data}")
            state['awaiting_cash_input'] = False
            state['pending_shift_data'] = None
            bot.send_message(message.chat.id, 
                           "❌ Ошибка: неполные данные смены.\n"
                           "Начните новую смену командой 'В бой! Начать смену'")
            return
        
        try:
            cash = int(message.text)
            if cash < 0:
                raise ValueError("Отрицательная сумма")
            
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
                data['start_time'],  # Скорректированное время начала
                data['end_time'],
                data['duration_str'],
                cash,
                hourly_rate_rounded)
            
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
            
    except Exception as e:
        print(f"❌ Ошибка в handle_cash_input: {e}")
        import traceback
        traceback.print_exc()
        bot.send_message(message.chat.id, "⚠️ Произошла ошибка. Попробуйте еще раз.")

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    try:
        user_id = message.from_user.id
        print(f"🔍 Обрабатываем сообщение от пользователя {user_id}: '{message.text}'")
        
        state = get_user_state(user_id)
        print(f"📊 Состояние пользователя: is_working={state.get('is_working')}")
        
        # Если смена активна и ожидает кассу, но нет данных - сбрасываем
        if state.get('awaiting_cash_input') and not state.get('pending_shift_data'):
            print(f"⚠️ Сброс состояния ожидания кассы для пользователя {user_id}")
            state['awaiting_cash_input'] = False
            
            # Обновляем в БД
            try:
                conn = psycopg2.connect(os.environ['DATABASE_URL'])
                cur = conn.cursor()
                cur.execute('''
                    UPDATE shifts 
                    SET awaiting_cash_input = FALSE
                    WHERE driver_id = %s AND is_active = TRUE
                ''', (user_id,))
                conn.commit()
                cur.close()
                conn.close()
                print(f"✅ Сброшен awaiting_cash_input в БД")
            except Exception as e:
                print(f"❌ Ошибка при сбросе в БД: {e}")
        
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
            try:
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
            except Exception as e:
                print(f"❌ Ошибка при обновлении БД: {e}")
            
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
            
    except Exception as e:
        print(f"❌ Ошибка в handle_buttons: {e}")
        import traceback
        traceback.print_exc()
        bot.send_message(message.chat.id, "⚠️ Произошла ошибка. Попробуйте еще раз.")

# --- Запуск бота ---
print("✅ Бот запущен с PostgreSQL!")

import traceback

try:
    # Очищаем старые зависшие состояния
    cleanup_old_states()

    # Восстанавливаем активные смены из БД при запуске
    print("🔄 Восстанавливаем активные смены из БД...")
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Проверяем есть ли поле is_active
        cur.execute('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='shifts' AND column_name='is_active'
        ''')
        
        if cur.fetchone():
            # Поле есть - ищем активные смены
            cur.execute("SELECT DISTINCT driver_id FROM shifts WHERE is_active = TRUE")
            active_drivers = cur.fetchall()
            
            for driver in active_drivers:
                user_id = driver['driver_id']
                get_user_state(user_id)  # Это восстановит состояние из БД
                print(f"   Восстановлена смена для водителя {user_id}")
            
            print(f"✅ Восстановлено {len(active_drivers)} активных смен")
        else:
            print("⚠️ Поле is_active отсутствует, восстановление не требуется")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"⚠️ Ошибка при восстановлении смен: {e}")
        traceback.print_exc()

except Exception as e:
    print(f"❌ Критическая ошибка при запуске бота: {e}")
    traceback.print_exc()

import time

while True:
    try:
        print("🤖 Запускаю бота...")
        
        # Очищаем вебхук перед запуском polling
        bot.remove_webhook()
        time.sleep(1)
        
        bot.polling(
            none_stop=True,
            interval=3,
            timeout=30,
            long_polling_timeout=20
        )
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
        break
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
        traceback.print_exc()
        print("🔄 Перезапуск через 15 секунд...")
        time.sleep(15)

