import telebot
import datetime
import time
import traceback
import os
import pytz
import random
import psycopg2
import threading
from psycopg2.extras import RealDictCursor
from telebot import types
from datetime import datetime, timedelta


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
    
    # СОЗДАЕМ ТАБЛИЦУ ДЛЯ АДМИНКИ (ДОБАВЬ ЭТОТ БЛОК)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS shift_edits (
            id SERIAL PRIMARY KEY,
            shift_id INTEGER NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
            editor_id BIGINT NOT NULL,
            edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason TEXT,
            old_start_time TIMESTAMP,
            new_start_time TIMESTAMP,
            old_end_time TIMESTAMP,
            new_end_time TIMESTAMP,
            old_cash INTEGER,
            new_cash INTEGER,
            old_hourly_rate INTEGER,
            new_hourly_rate INTEGER
        )
    ''')
    
        # Создаем таблицу месячных планов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS monthly_plans (
            id SERIAL PRIMARY KEY,
            driver_id BIGINT NOT NULL,
            target_amount INTEGER NOT NULL CHECK (target_amount >= 0),
            year INTEGER NOT NULL,
            month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(driver_id, year, month)
        )
    ''')
    #     # Создаем таблицу недельных планов
    # cur.execute('''
    #     CREATE TABLE IF NOT EXISTS weekly_plans (
    #         id SERIAL PRIMARY KEY,
    #         driver_id BIGINT NOT NULL,
    #         target_amount INTEGER NOT NULL CHECK (target_amount >= 0),
    #         week_year INTEGER NOT NULL,  # Год недели по ISO
    #         week_number INTEGER NOT NULL CHECK (week_number >= 1 AND week_number <= 53),
    #         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    #         UNIQUE(driver_id, week_year, week_number)
    #     )
    # ''')

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
    
    # ДОБАВЛЯЕМ ИНДЕКС ДЛЯ shift_edits (ВАЖНО!)
    try:
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_shift_edits_shift_id 
            ON shift_edits(shift_id)
        ''')
        print("   ✅ Индекс idx_shift_edits_shift_id создан")
    except Exception as e:
        print(f"   ⚠️ Ошибка при создании idx_shift_edits_shift_id: {e}")
    
    cur.close()
    conn.close()
    print("🎉 Инициализация БД завершена!")

init_database()

# --- Константы и утилиты ---
bot = telebot.TeleBot(os.environ['BOT_TOKEN'])

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

def format_duration(seconds):
    """Форматирует секунды в '2 ч 15 мин'"""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    
    if hours > 0 and minutes > 0:
        return f"{hours} ч {minutes} мин"
    elif hours > 0:
        return f"{hours} ч"
    else:
        return f"{minutes} мин"

def get_current_iso_week():
    """Возвращает текущий год и номер недели по ISO (пн-вс)"""
    now = get_moscow_time()
    # isocalendar возвращает (год, номер недели, день недели)
    iso_year, iso_week, iso_day = now.isocalendar()
    return iso_year, iso_week

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
        return dt.replace(tzinfo=None)  # ✅ ПРОСТО УДАЛЯЕМ ТАЙМЗОНУ
    return dt

# --- Состояния пользователей ---
user_states = {}

# --- Напоминания о паузах ---
def start_pause_reminder_checker():
    """Запускает фоновый поток для проверки пауз"""
    def checker_loop():
        while True:
            time.sleep(60)  # Проверяем каждую минуту
            check_paused_shifts()
    
    thread = threading.Thread(target=checker_loop, daemon=True)
    thread.start()
    print("✅ Запущен проверщик напоминаний о паузах")

def check_paused_shifts():
    """Проверяет смены на паузе и отправляет напоминания"""
    current_time = get_moscow_time()
    
    for user_id, state in list(user_states.items()):  # Используем list для копирования
        try:
            if (state.get('is_working') and 
                state.get('is_paused') and 
                state.get('pause_start_time')):
                
                pause_duration = current_time - state['pause_start_time']
                total_minutes = int(pause_duration.total_seconds() // 60)
                
                # Проверяем, не отправляли ли уже напоминание
                last_reminder = state.get('last_pause_reminder_minutes', 0)
                
                # Напоминание через 1 час (60 минут)
                if total_minutes >= 60 and last_reminder < 60:
                    bot.send_message(
                        user_id,
                        f"⏰ Напоминание: смена на паузе уже 1 час\n"
                        f"Не забудь продолжить работу!"
                    )
                    state['last_pause_reminder_minutes'] = 60
                    print(f"⏰ Напоминание отправлено пользователю {user_id} (1 час)")
                
                # Напоминание каждые 30 минут после первого часа
                elif total_minutes >= 90 and (total_minutes - last_reminder) >= 30:
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    
                    time_str = f"{hours} ч" if minutes == 0 else f"{hours} ч {minutes} мин"
                    
                    bot.send_message(
                        user_id,
                        f"⏰ Напоминание: смена на паузе уже {time_str}\n"
                        f"Продолжить или завершить смену?"
                    )
                    state['last_pause_reminder_minutes'] = total_minutes
                    print(f"⏰ Напоминание отправлено пользователю {user_id} ({time_str})")
                    
        except Exception as e:
            print(f"⚠️ Ошибка при проверке паузы для {user_id}: {e}")

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
            'shift_id': None,
            'awaiting_plan_input': False,
            'plan_type': None,
            'current_plan_menu': None
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
                'shift_id': None,
                'awaiting_plan_input': False,
                'plan_type': None,
                'current_plan_menu': None
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
            'shift_id': active_shift.get('id'),
            'awaiting_plan_input': False,
            'plan_type': None,
            'current_plan_menu': None    # сохраняем ID смены для обновлений
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

def get_monthly_plan(user_id, year=None, month=None):
    """Получить месячный план пользователя"""
    if year is None or month is None:
        now = get_moscow_time()  # Используем нашу функцию для московского времени
        year = now.year
        month = now.month
    
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute('''
            SELECT * FROM monthly_plans 
            WHERE driver_id = %s AND year = %s AND month = %s
        ''', (user_id, year, month))
        
        plan = cur.fetchone()
        cur.close()
        conn.close()
        return plan
    except Exception as e:
        print(f"❌ Ошибка при получении плана: {e}")
        return None

def save_monthly_plan(user_id, amount):
    """Сохраняет или обновляет месячный план пользователя"""
    now = get_moscow_time()
    year = now.year
    month = now.month
    
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        
        # Используем INSERT ON CONFLICT для обновления при повторе
        cur.execute('''
            INSERT INTO monthly_plans (driver_id, target_amount, year, month)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (driver_id, year, month) 
            DO UPDATE SET target_amount = EXCLUDED.target_amount,
                         created_at = CURRENT_TIMESTAMP
            RETURNING id
        ''', (user_id, amount, year, month))
        
        plan_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Месячный план #{plan_id} сохранен для пользователя {user_id}: {amount} руб")
        return True
    except Exception as e:
        print(f"❌ Ошибка при сохранении плана: {e}")
        return False

def get_weekly_plan(user_id, week_year=None, week_number=None):
    """Получить недельный план пользователя"""
    if week_year is None or week_number is None:
        week_year, week_number = get_current_iso_week()
    
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute('''
            SELECT * FROM weekly_plans 
            WHERE driver_id = %s AND week_year = %s AND week_number = %s
        ''', (user_id, week_year, week_number))
        
        plan = cur.fetchone()
        cur.close()
        conn.close()
        return plan
    except Exception as e:
        print(f"❌ Ошибка при получении недельного плана: {e}")
        return None

def save_weekly_plan(user_id, amount):
    """Сохраняет или обновляет недельный план пользователя"""
    week_year, week_number = get_current_iso_week()
    
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO weekly_plans (driver_id, target_amount, week_year, week_number)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (driver_id, week_year, week_number) 
            DO UPDATE SET target_amount = EXCLUDED.target_amount,
                         created_at = CURRENT_TIMESTAMP
            RETURNING id
        ''', (user_id, amount, week_year, week_number))
        
        plan_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Недельный план #{plan_id} сохранен для пользователя {user_id}: {amount} руб (неделя {week_number}/{week_year})")
        return True
    except Exception as e:
        print(f"❌ Ошибка при сохранении недельного плана: {e}")
        return False

# --- Команды бота ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button_shift = types.KeyboardButton('🚗 Смена')
    button_reports = types.KeyboardButton('📊 Отчеты')
    button_plan = types.KeyboardButton('🎯 План')
    markup.row(button_shift, button_reports, button_plan)
    
    bot.send_message(message.chat.id, 
                    '🚕 Тебя приветствует Вован - бот, помощник таксиста\nВыбери раздел:',
                    reply_markup=markup)

def show_shift_menu(message):
    """Показывает меню управления сменой"""
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    if not state['is_working']:
        # Смена не активна - только кнопка "Начать"
        button_start = types.KeyboardButton('🟢 Начать смену')
        markup.row(button_start)
        
        status_text = "🚗 Раздел: Смена"
        
    else:
        # Смена активна
        if state['is_paused']:
            # На паузе - показываем длительность
            pause_duration = get_moscow_time() - state['pause_start_time']
            total_minutes = int(pause_duration.total_seconds() // 60)
            
            if total_minutes < 60:
                pause_str = f"{total_minutes} мин"
            else:
                hours = total_minutes // 60
                minutes = total_minutes % 60
                if minutes == 0:
                    pause_str = f"{hours} ч"
                else:
                    pause_str = f"{hours} ч {minutes} мин"
            
            status_text = f"⏸ Смена на паузе ({pause_str})"
            
            button_continue = types.KeyboardButton('▶ Продолжить')
            button_end = types.KeyboardButton('✅ Завершить смену')
            markup.row(button_continue, button_end)
            
        else:
            # Активна, не на паузе
            status_text = "🟢 Смена активна"
            
            button_pause = types.KeyboardButton('⏸ Пауза/продолжить')
            button_end = types.KeyboardButton('✅ Завершить смену')
            markup.row(button_pause, button_end)
    
    # Кнопка "Назад" всегда
    button_back = types.KeyboardButton('◀️ Назад')
    markup.row(button_back)
    
    # Отправляем сообщение
    bot.send_message(message.chat.id, status_text, reply_markup=markup)

def show_plan_menu(message):
    """Показывает меню управления планами"""
    user_id = message.from_user.id
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    button_monthly = types.KeyboardButton('📅 План на месяц')
    button_weekly = types.KeyboardButton('🔄 План на неделю')
    button_back = types.KeyboardButton('◀️ Назад')
    
    markup.row(button_monthly, button_weekly)
    markup.row(button_back)
    
    bot.send_message(
        message.chat.id,
        "🎯 Управление планами\n\n"
        "Установите цели для мотивации и отслеживания прогресса",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text in ['✏️ Редактировать', '✏️ Установить план', '◀️ Назад к планам'])
def handle_monthly_plan_menu(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if message.text == '✏️ Редактировать' or message.text == '✏️ Установить план':
        # Включаем режим ожидания ввода плана
        state['awaiting_plan_input'] = True
        state['plan_type'] = 'monthly'
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        button_cancel = types.KeyboardButton('❌ Отмена')
        markup.row(button_cancel)
        
        bot.send_message(
            message.chat.id,
            "Введите сумму месячного плана в рублях:\n\n"
            "Например: 80000",
            reply_markup=markup
        )
        
    elif message.text == '◀️ Назад к планам':
        show_plan_menu(message)

def show_monthly_plan_menu(message):
    """Показывает меню месячного плана"""
    user_id = message.from_user.id
    state = get_user_state(user_id)
    state['current_plan_menu'] = 'monthly'
    # Получаем текущий план
    plan = get_monthly_plan(user_id)
    
    # Определяем текущий месяц и год для отображения
    now = get_moscow_time()
    month_names = [
        'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
        'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
    ]
    month_name = month_names[now.month - 1]
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    if plan:
        # Если план есть
        message_text = (
            f"🎯 План на {month_name} {now.year}\n\n"
            f"Текущий план: {plan['target_amount']:,} руб"
        )
        button_text = "✏️ Редактировать"
    else:
        # Если плана нет
        message_text = (
            f"🎯 План на {month_name} {now.year}\n\n"
            f"План не задан"
        )
        button_text = "✏️ Установить план"
    
    button_edit = types.KeyboardButton(button_text)
    button_back = types.KeyboardButton('◀️ Назад к планам')
    
    markup.row(button_edit)
    markup.row(button_back)
    
    bot.send_message(message.chat.id, message_text, reply_markup=markup)

def show_weekly_plan_menu(message):
    """Показывает меню недельного плана"""
    user_id = message.from_user.id
    state = get_user_state(user_id)
    state['current_plan_menu'] = 'weekly'
    # Получаем текущий план
    plan = get_weekly_plan(user_id)
    
    # Определяем текущую неделю для отображения
    week_year, week_number = get_current_iso_week()
    
    # Получаем даты начала и конца недели (пн-вс)
    now = get_moscow_time()
    start_of_week = now - timedelta(days=now.weekday())  # Понедельник
    end_of_week = start_of_week + timedelta(days=6)      # Воскресенье
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    if plan:
        # Если план есть
        message_text = (
            f"🔄 План на неделю {week_number} ({start_of_week.strftime('%d.%m')}-{end_of_week.strftime('%d.%m.%Y')})\n\n"
            f"Текущий план: {plan['target_amount']:,} руб"
        )
        button_text = "✏️ Редактировать"
    else:
        # Если плана нет
        message_text = (
            f"🔄 План на неделю {week_number} ({start_of_week.strftime('%d.%m')}-{end_of_week.strftime('%d.%m.%Y')})\n\n"
            f"План не задан"
        )
        button_text = "✏️ Установить план"
    
    button_edit = types.KeyboardButton(button_text)
    button_back = types.KeyboardButton('◀️ Назад к планам')
    
    markup.row(button_edit)
    markup.row(button_back)
    
    bot.send_message(message.chat.id, message_text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ['🚗 Смена', '📊 Отчеты', '🎯 План', '◀️ Назад'])
def handle_main_menu(message):
    if message.text == '🚗 Смена':
        show_shift_menu(message)
    elif message.text == '📊 Отчеты':
        # Пока заглушка
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        button_back = types.KeyboardButton('◀️ Назад')
        markup.row(button_back)
        bot.send_message(message.chat.id, "📊 Раздел: Отчеты\n(в разработке)", reply_markup=markup)
    elif message.text == '🎯 План':  # ← ДОБАВИЛИ ЭТО
        show_plan_menu(message)       # ← И ЭТО
    elif message.text == '◀️ Назад':
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        button_shift = types.KeyboardButton('🚗 Смена')
        button_reports = types.KeyboardButton('📊 Отчеты')
        button_plan = types.KeyboardButton('🎯 План')
        markup.row(button_shift, button_reports, button_plan)
        
        bot.send_message(
            message.chat.id, 
            'Выбери раздел:', 
            reply_markup=markup
        )

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

@bot.message_handler(func=lambda message: 
    get_user_state(message.from_user.id).get('awaiting_plan_input', False) == True)
def handle_plan_input(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if message.text == '❌ Отмена':
        # Отмена ввода
        state['awaiting_plan_input'] = False
        state['plan_type'] = None
        show_monthly_plan_menu(message)
        return
    
    try:
        amount = int(message.text)
        
        if amount <= 0:
            raise ValueError("Отрицательная или нулевая сумма")
        
        if amount > 10000000:  # Максимум 10 млн (можно изменить)
            bot.send_message(message.chat.id, 
                           "❌ Слишком большая сумма. Максимум 10 000 000 руб\n"
                           "Введите сумму еще раз:")
            return
        
        # Сохраняем план
        success = save_monthly_plan(user_id, amount)
        
        if success:
            # Сбрасываем состояние
            state['awaiting_plan_input'] = False
            state['plan_type'] = None
            
            # Показываем подтверждение и возвращаем в меню
            now = get_moscow_time()
            month_names = [
                'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
            ]
            month_name = month_names[now.month - 1]
            
            bot.send_message(
                message.chat.id,
                f"✅ План на {month_name} {now.year} установлен: {amount:,} руб"
            )
            
            # Возвращаем в меню плана
            show_plan_menu(message)
        else:
            bot.send_message(message.chat.id, 
                           "❌ Ошибка при сохранении плана. Попробуйте еще раз:")
            
    except ValueError:
        bot.send_message(message.chat.id, 
                       "❌ Введите корректную сумму (целое число больше 0)\n"
                       "Например: 80000\n\n"
                       "Введите сумму еще раз:")

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    try:
        user_id = message.from_user.id
        print(f"🔍 Обрабатываем сообщение от пользователя {user_id}: '{message.text}'")
        
        state = get_user_state(user_id)
        print(f"📊 Состояние пользователя: is_working={state.get('is_working')}")
        
        # ===== ОБРАБОТКА КНОПКИ ОТМЕНЫ =====
        if message.text == '❌ Отмена':
            if state.get('awaiting_plan_input'):
                print(f"❌ Отмена ввода плана для пользователя {user_id}")
                state['awaiting_plan_input'] = False
                state['plan_type'] = None
                show_plan_menu(message)
                return
            elif state.get('awaiting_cash_input'):
                print(f"❌ Отмена ввода кассы для пользователя {user_id}")
                state['awaiting_cash_input'] = False
                state['pending_shift_data'] = None
                show_shift_menu(message)
                return
        
                # ===== ОБРАБОТКА МЕНЮ ПЛАНОВ =====
        if message.text == '📅 План на месяц':
            show_monthly_plan_menu(message)
            return
        elif message.text == '🔄 План на неделю':
            show_weekly_plan_menu(message)
            return
        elif message.text == '◀️ Назад к планам':
            show_plan_menu(message)
            return
        elif message.text in ['✏️ Редактировать', '✏️ Установить план']:
            user_id = message.from_user.id
            state = get_user_state(user_id)
            
            # Включаем режим ожидания ввода плана
            state['awaiting_plan_input'] = True
            state['plan_type'] = 'monthly'
            
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            button_cancel = types.KeyboardButton('❌ Отмена')
            markup.row(button_cancel)
            
            bot.send_message(
                message.chat.id,
                "Введите сумму месячного плана в рублях:\n\n"
                "Например: 80000",
                reply_markup=markup
            )
            return
        
        elif message.text in ['✏️ Редактировать', '✏️ Установить план']:
            # Нужно определить в каком меню мы находимся
            # Проще всего проверить состояние или последнее действие
            # Пока сделаем так: если есть weekly_plan - значит в меню недельного
            
            user_id = message.from_user.id
            state = get_user_state(user_id)
            
            # Проверяем какой план редактируем
            weekly_plan = get_weekly_plan(user_id)
            monthly_plan = get_monthly_plan(user_id)
            
            # Определяем тип плана по контексту (упрощенно)
            # В реальности нужно хранить текущее меню в состоянии
            
            if weekly_plan is not None or True:  # Пока всегда weekly для теста
                state['awaiting_plan_input'] = True
                state['plan_type'] = 'weekly'
            else:
                state['awaiting_plan_input'] = True
                state['plan_type'] = 'monthly'
            
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            button_cancel = types.KeyboardButton('❌ Отмена')
            markup.row(button_cancel)
            
            plan_type_str = "недельного" if state['plan_type'] == 'weekly' else "месячного"
            
            bot.send_message(
                message.chat.id,
                f"Введите сумму {plan_type_str} плана в рублях:\n\n"
                "Например: 20000",
                reply_markup=markup
            )
            return


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
        
        # ===== ОБРАБОТКА КНОПОК ИЗ РАЗДЕЛА "СМЕНА" =====
        
        if message.text == '🟢 Начать смену':
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
                    
                    bot.send_message(message.chat.id, "✅ Смена начата! 🚕")
                else:
                    bot.send_message(message.chat.id, "❌ Ошибка при начале смены")
            else:
                bot.send_message(message.chat.id, "⚠️ Смена уже начата!")
                
        elif message.text in ['⏸ Пауза/продолжить', '▶ Продолжить']:
            if not state['is_working']:
                bot.send_message(message.chat.id, "❌ Смена не начата")
                show_shift_menu(message)
                return
            
            current_time = get_moscow_time()
            
            if not state['is_paused']:
                # Ставим на паузу
                state['is_paused'] = True
                state['pause_start_time'] = current_time
                state['last_pause_reminder_minutes'] = 0
                # Обновляем в БД
                update_shift_pause(user_id, True, current_time)
                
                bot.send_message(message.chat.id, "⏸ Смена на паузе")
                show_shift_menu(message)
                
            else:
                # Снимаем с паузы
                pause_duration = current_time - state['pause_start_time']
                
                # Обновляем время начала с учетом паузы
                state['shift_start_time'] += pause_duration
                state['is_paused'] = False
                state['pause_start_time'] = None
                state['last_pause_reminder_minutes'] = 0
                # Обновляем в БД
                update_shift_pause(user_id, False, None)
                
                bot.send_message(message.chat.id, "▶ Смена продолжена")
                show_shift_menu(message)
        
        elif message.text == '✅ Завершить смену':
            if not state['is_working']:
                bot.send_message(message.chat.id, "❌ Смена не начата")
                show_shift_menu(message)
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
            
            # НЕ возвращаем в меню СМЕНА - остаёмся в ожидании кассы
            bot.send_message(message.chat.id, 
                           f"⏱ Отработано: {time_str}\n"
                           "💵 Введите сумму в кассе:")
        
        # ===== ОБРАБОТКА КНОПОК ГЛАВНОГО МЕНЮ =====
        elif message.text in ['🚗 СМЕНА', '📊 ОТЧЕТЫ', '🎯 ПЛАН', '◀️ НАЗАД']:
            # Эти кнопки уже обрабатываются в handle_main_menu
            pass
        
        # ===== СТАРЫЕ КНОПКИ (для обратной совместимости) =====
        elif message.text == 'В бой! Начать смену':
            # Старая кнопка - перенаправляем на новую логику
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
                    
                    bot.send_message(message.chat.id, "✅ Смена начата! 🚕")
                    send_welcome(message)
                else:
                    bot.send_message(message.chat.id, "❌ Ошибка при начале смены")
            else:
                bot.send_message(message.chat.id, "⚠️ Смена уже начата!")
        
        elif message.text == 'Пауза/Продолжить':
            # Старая кнопка - перенаправляем на новую логику
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
            # Старая кнопка - перенаправляем на новую логику
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
            
        # ===== ЕСЛИ КНОПКА НЕ РАСПОЗНАНА =====
        else:
            # Показываем стартовое меню
            send_welcome(message)
            
    except Exception as e:
        print(f"❌ Ошибка в handle_buttons: {e}")
        import traceback
        traceback.print_exc()
        bot.send_message(message.chat.id, "⚠️ Произошла ошибка. Попробуйте еще раз.")

# --- Webhook настройка ---
import flask
from flask import Flask, request

app = Flask(__name__)

print("✅ Бот инициализирован с PostgreSQL!")
start_pause_reminder_checker()
print("✅ Проверщик напоминаний запущен")

# Инициализация при запуске (только один раз)
try:
    cleanup_old_states()
    
    # Восстанавливаем активные смены
    print("🔄 Восстанавливаем активные смены из БД...")
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute('''
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='shifts' AND column_name='is_active'
        ''')
        
        if cur.fetchone():
            cur.execute("SELECT DISTINCT driver_id FROM shifts WHERE is_active = TRUE")
            active_drivers = cur.fetchall()
            
            for driver in active_drivers:
                user_id = driver['driver_id']
                get_user_state(user_id)
                print(f"   Восстановлена смена для водителя {user_id}")
            
            print(f"✅ Восстановлено {len(active_drivers)} активных смен")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"⚠️ Ошибка при восстановлении смен: {e}")
        import traceback
        traceback.print_exc()

except Exception as e:
    print(f"❌ Критическая ошибка при инициализации: {e}")
    import traceback
    traceback.print_exc()

@app.route('/', methods=['POST'])
def webhook():
    """Обработчик webhook от Telegram"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Bad request', 400

@app.route('/')
def index():
    return 'Bot is running!'

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Установить webhook (вызови в браузере после деплоя)"""
    webhook_url = f"https://{os.environ.get('RAILWAY_STATIC_URL', 'ваш-домен.railway.app')}/"
    bot.remove_webhook()
    time.sleep(1)
    result = bot.set_webhook(url=webhook_url)
    return f"Webhook set to {webhook_url}: {result}"

# Для локального тестирования можно оставить polling
if __name__ == '__main__':
    import os
    if os.environ.get('RAILWAY_ENVIRONMENT') is None:
        # Локальный запуск
        print("🚀 Локальный запуск (polling)...")
        bot.remove_webhook()
        time.sleep(1)
        bot.polling(none_stop=True)
    else:
        # На Railway - запускаем Flask
        print("🚀 Запуск на Railway (webhook)...")
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port)