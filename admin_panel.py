import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from datetime import datetime, date, time, timedelta
import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла (для локальной разработки)
load_dotenv()

# Настройки страницы
st.set_page_config(
    page_title="Админ-панель Такси-бота",
    page_icon="🚕",
    layout="wide"
)

# --- КОНФИГУРАЦИЯ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
DATABASE_URL = os.environ.get('DATABASE_URL', '')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# Проверка что переменные установлены
if not DATABASE_URL:
    st.error("❌ Ошибка: не установлена переменная DATABASE_URL")
    st.info("Для локальной разработки создайте файл .env с содержимым:")
    st.code("""
DATABASE_URL=postgresql://postgres:пароль@хост:порт/railway
ADMIN_PASSWORD=ваш_пароль
    """)
    st.stop()

# --- Аутентификация ---
def check_auth():
    """Проверка пароля администратора"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        st.title("🔐 Аутентификация")
        password = st.text_input("Пароль администратора", type="password")
        
        if st.button("Войти"):
            if password == ADMIN_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Неверный пароль")
        st.stop()

# --- Функции работы с БД ---
def get_connection():
    """Создаёт подключение к БД"""
    return psycopg2.connect(DATABASE_URL)

def search_shifts(driver_id=None, date_filter=None, min_cash=None, max_cash=None):
    """Поиск смен по фильтрам"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM shifts WHERE 1=1"
    params = []
    
    if driver_id:
        query += " AND driver_id = %s"
        params.append(driver_id)
    
    if date_filter:
        query += " AND DATE(start_time) = %s"
        params.append(date_filter)
    
    if min_cash:
        query += " AND cash >= %s"
        params.append(min_cash)
    
    if max_cash:
        query += " AND cash <= %s"
        params.append(max_cash)
    
    query += " ORDER BY start_time DESC LIMIT 100"
    
    cur.execute(query, params)
    shifts = cur.fetchall()
    
    cur.close()
    conn.close()
    return shifts

def get_shift_by_id(shift_id):
    """Получить смену по ID"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM shifts WHERE id = %s", (shift_id,))
    shift = cur.fetchone()
    
    cur.close()
    conn.close()
    return shift

def get_edit_history(shift_id):
    """Получить историю изменений смены"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT * FROM shift_edits 
        WHERE shift_id = %s 
        ORDER BY edited_at DESC
    """, (shift_id,))
    
    history = cur.fetchall()
    
    cur.close()
    conn.close()
    return history

def save_shift_edit(shift_id, editor_id, reason, old_start, new_start, old_end, new_end, old_cash, new_cash):
    """Сохраняет изменения смены через функцию log_shift_edit"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT log_shift_edit(
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s
            )
        """, (
            shift_id, editor_id, reason,
            old_start, new_start,
            old_end, new_end,
            old_cash, new_cash
        ))
        
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()

def get_all_shifts_paginated(offset=0, limit=20, driver_id=None, start_date=None, end_date=None):
    """Получает смены с пагинацией и фильтрами"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT 
            id,
            driver_id,
            start_time,
            end_time,
            duration_text,
            cash,
            hourly_rate,
            is_active,
            is_paused,
            created_at
        FROM shifts 
        WHERE 1=1
    """
    params = []
    
    if driver_id:
        query += " AND driver_id = %s"
        params.append(driver_id)
    
    if start_date:
        query += " AND DATE(start_time) >= %s"
        params.append(start_date)
    
    if end_date:
        query += " AND DATE(start_time) <= %s"
        params.append(end_date)
    
    query += " ORDER BY start_time DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    cur.execute(query, params)
    shifts = cur.fetchall()
    
    # Получаем общее количество для пагинации
    count_query = "SELECT COUNT(*) as total FROM shifts WHERE 1=1"
    count_params = []
    
    if driver_id:
        count_query += " AND driver_id = %s"
        count_params.append(driver_id)
    
    if start_date:
        count_query += " AND DATE(start_time) >= %s"
        count_params.append(start_date)
    
    if end_date:
        count_query += " AND DATE(start_time) <= %s"
        count_params.append(end_date)
    
    cur.execute(count_query, count_params)
    total = cur.fetchone()['total']
    
    cur.close()
    conn.close()
    
    return shifts, total

def delete_shift(shift_id):
    """Удаляет смену и связанные записи"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Сначала удаляем историю изменений
        cur.execute("DELETE FROM shift_edits WHERE shift_id = %s", (shift_id,))
        
        # Затем удаляем саму смену
        cur.execute("DELETE FROM shifts WHERE id = %s RETURNING id", (shift_id,))
        
        deleted_id = cur.fetchone()
        
        conn.commit()
        cur.close()
        conn.close()
        
        if deleted_id:
            print(f"✅ Смена #{shift_id} удалена")
            return True, None
        else:
            return False, "Смена не найдена"
            
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return False, str(e)

def save_manual_shift(driver_id, start_time, end_time, cash, duration_str, hourly_rate):
    """Сохраняет смену, созданную вручную"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Рассчитываем секунды
        duration_seconds = int((end_time - start_time).total_seconds())
        
        # Сохраняем смену
        cur.execute('''
            INSERT INTO shifts 
            (driver_id, start_time, end_time, duration_text, 
             duration_seconds, cash, hourly_rate, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NOW())
            RETURNING id
        ''', (driver_id, start_time, end_time, duration_str, 
              duration_seconds, cash, hourly_rate))
        
        shift_id = cur.fetchone()[0]
        
        # Записываем в историю что создано вручную
        cur.execute('''
            INSERT INTO shift_edits 
            (shift_id, editor_id, edited_at, reason,
             old_start_time, new_start_time, old_end_time, new_end_time,
             old_cash, new_cash, old_hourly_rate, new_hourly_rate)
            VALUES (%s, %s, NOW(), 'Создано вручную через админ-панель',
                    NULL, %s, NULL, %s, NULL, %s, NULL, %s)
        ''', (shift_id, 0, start_time, end_time, cash, hourly_rate))
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Смена #{shift_id} создана вручную для водителя {driver_id}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при сохранении ручной смены: {e}")
        import traceback
        traceback.print_exc()
        return False

# --- Вспомогательные функции ---
def parse_datetime(dt_value):
    """Преобразует значение даты-времени из БД в datetime объект"""
    if isinstance(dt_value, datetime):
        return dt_value
    elif isinstance(dt_value, str):
        # Пробуем разные форматы
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S.%fZ'
        ]
        for fmt in formats:
            try:
                return datetime.strptime(dt_value, fmt)
            except ValueError:
                continue
        # Если ни один формат не подошел, возвращаем текущее время
        return datetime.now()
    elif isinstance(dt_value, date):
        return datetime.combine(dt_value, time())
    else:
        return datetime.now()

# --- Основной интерфейс ---
def main():
    check_auth()
    
    st.title("🚕 Админ-панель Такси-бота")
    st.markdown("---")
    
    # Инициализация состояний
    if 'page' not in st.session_state:
        st.session_state.page = 0
    if 'selected_shift_id' not in st.session_state:
        st.session_state.selected_shift_id = None
    if 'filters' not in st.session_state:
        st.session_state.filters = {'driver_id': None, 'start_date': None, 'end_date': None}
    if 'show_add_shift' not in st.session_state:
        st.session_state.show_add_shift = False
    if 'show_stats' not in st.session_state:
        st.session_state.show_stats = False
    if 'show_export' not in st.session_state:
        st.session_state.show_export = False
    
    # ===== РЕЖИМЫ РАБОТЫ =====
    # Проверяем, какой режим активен
    
    # 1. Режим добавления смены
    if st.session_state.show_add_shift:
        show_add_shift_form()
        return
    
    # 2. Режим статистики
    if st.session_state.show_stats:
        show_general_stats()
        return
    
    # 3. Режим экспорта
    if st.session_state.show_export:
        show_export_data()
        return
    
    # 4. Режим деталей смены
    if st.session_state.selected_shift_id:
        show_shift_detail(st.session_state.selected_shift_id)
        return
    
    # ===== ОСНОВНОЙ РЕЖИМ - СПИСОК СМЕН =====
    
    # ===== ФИЛЬТРЫ =====
    st.subheader("🔍 Фильтры")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        filter_driver = st.number_input(
            "ID водителя (оставьте 0 для всех)",
            min_value=0,
            value=st.session_state.filters.get('driver_id', 0),
            key="filter_driver_input"
        )
    
    with col2:
        filter_start_date = st.date_input(
            "Дата с",
            value=st.session_state.filters.get('start_date') or (datetime.now().date() - timedelta(days=30)),
            key="filter_start_input"
        )
    
    with col3:
        filter_end_date = st.date_input(
            "Дата по",
            value=st.session_state.filters.get('end_date') or datetime.now().date(),
            key="filter_end_input"
        )
    
    # Кнопки фильтров
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Применить фильтры", type="primary", key="apply_filters"):
            st.session_state.filters = {
                'driver_id': filter_driver if filter_driver > 0 else None,
                'start_date': filter_start_date,
                'end_date': filter_end_date
            }
            st.session_state.page = 0
            st.rerun()
    
    with col2:
        if st.button("Сбросить фильтры", type="secondary", key="reset_filters"):
            st.session_state.filters = {'driver_id': None, 'start_date': None, 'end_date': None}
            st.session_state.page = 0
            st.rerun()
    
    with col3:
        # Быстрая статистика
        conn = get_connection()
        cur = conn.cursor()
        
        stats_query = "SELECT COUNT(*) as total, SUM(cash) as total_cash FROM shifts WHERE 1=1"
        stats_params = []
        
        if st.session_state.filters['driver_id']:
            stats_query += " AND driver_id = %s"
            stats_params.append(st.session_state.filters['driver_id'])
        
        if st.session_state.filters['start_date']:
            stats_query += " AND DATE(start_time) >= %s"
            stats_params.append(st.session_state.filters['start_date'])
        
        if st.session_state.filters['end_date']:
            stats_query += " AND DATE(start_time) <= %s"
            stats_params.append(st.session_state.filters['end_date'])
        
        cur.execute(stats_query, stats_params)
        stats = cur.fetchone()
        cur.close()
        conn.close()
        
        st.metric("Найдено смен", stats[0] if stats else 0)
    
    st.markdown("---")
    
    # ===== ТАБЛИЦА СМЕН =====
    col_title, col_button = st.columns([3, 1])
    with col_title:
        st.subheader("📋 Все смены")
    with col_button:
        if st.button("➕ Добавить смену", type="primary"):
            st.session_state.show_add_shift = True
            st.rerun()
    
    # Получаем смены для текущей страницы
    shifts, total = get_all_shifts_paginated(
        offset=st.session_state.page * 20,
        limit=20,
        driver_id=st.session_state.filters['driver_id'],
        start_date=st.session_state.filters['start_date'],
        end_date=st.session_state.filters['end_date']
    )
    
    if shifts:
        # Создаем DataFrame
        df = pd.DataFrame(shifts)
        
        # Форматируем данные
        df['start_time'] = pd.to_datetime(df['start_time']).dt.strftime('%d.%m.%Y %H:%M')
        df['end_time'] = pd.to_datetime(df['end_time']).dt.strftime('%d.%m.%Y %H:%M')
        
        # Добавляем колонку статуса
        df['status'] = df.apply(
            lambda row: '🟢 Активна' if row['is_active'] else ('⏸ На паузе' if row['is_paused'] else '✅ Завершена'),
            axis=1
        )
        
        # Показываем таблицу с возможностью выбора
        for _, shift in df.iterrows():
            col1, col2, col3, col4, col5, col6, col7 = st.columns([1, 2, 2, 2, 2, 2, 1])
            
            with col1:
                st.markdown(f"**#{shift['id']}**")
            
            with col2:
                st.markdown(f"👤 {shift['driver_id']}")
            
            with col3:
                st.markdown(f"📅 {shift['start_time']}")
            
            with col4:
                st.markdown(f"⏱ {shift['duration_text'] or '—'}")
            
            with col5:
                st.markdown(f"💰 {shift['cash']:,} руб")
            
            with col6:
                st.markdown(f"📊 {shift['hourly_rate'] or 0:,} руб/ч")
            
            with col7:
                if st.button("👁️", key=f"view_{shift['id']}"):
                    st.session_state.selected_shift_id = shift['id']
                    st.rerun()
            
            st.divider()
        
        # ===== ПАГИНАЦИЯ =====
        st.markdown("---")
        total_pages = (total + 19) // 20
        
        if total_pages > 1:
            st.write(f"Страница {st.session_state.page + 1} из {total_pages} (всего {total} смен)")
            
            cols = st.columns(5)
            
            with cols[0]:
                if st.button("⏮️ Первая", disabled=st.session_state.page == 0):
                    st.session_state.page = 0
                    st.rerun()
            
            with cols[1]:
                if st.button("◀️ Назад", disabled=st.session_state.page == 0):
                    st.session_state.page -= 1
                    st.rerun()
            
            with cols[2]:
                page_num = st.number_input(
                    "Страница",
                    min_value=1,
                    max_value=total_pages,
                    value=st.session_state.page + 1,
                    key="page_input"
                )
                if page_num != st.session_state.page + 1:
                    st.session_state.page = page_num - 1
                    st.rerun()
            
            with cols[3]:
                if st.button("Вперед ▶️", disabled=st.session_state.page >= total_pages - 1):
                    st.session_state.page += 1
                    st.rerun()
            
            with cols[4]:
                if st.button("Последняя ⏭️", disabled=st.session_state.page >= total_pages - 1):
                    st.session_state.page = total_pages - 1
                    st.rerun()
    else:
        st.info("🚫 Смены не найдены")
    
    # ===== БЫСТРЫЕ ДЕЙСТВИЯ =====
    st.markdown("---")
    st.subheader("⚡ Быстрые действия")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 Обновить страницу"):
            st.rerun()
    
    with col2:
        if st.button("📊 Общая статистика"):
            st.session_state.show_stats = True
            st.rerun()
    
    with col3:
        if st.button("📤 Экспорт данных"):
            st.session_state.show_export = True
            st.rerun()

def show_shift_detail(shift_id):
    """Показывает детальную информацию о смене"""
    
    shift = get_shift_by_id(shift_id)
    if not shift:
        st.error(f"Смена #{shift_id} не найдена")
        return
    
    st.title(f"📋 Смена #{shift['id']}")
    
    # Основная информация
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("👤 Водитель")
        st.info(f"**ID:** {shift['driver_id']}")
        
        # Здесь можно добавить информацию из таблицы drivers когда она будет
        st.markdown("---")
        
        st.subheader("📅 Время")
        start_time = parse_datetime(shift['start_time'])
        end_time = parse_datetime(shift['end_time'])
        
        st.write(f"**Начало:** {start_time.strftime('%d.%m.%Y %H:%M')}")
        st.write(f"**Окончание:** {end_time.strftime('%d.%m.%Y %H:%M')}")
        
        if shift.get('duration_text'):
            st.write(f"**Продолжительность:** {shift['duration_text']}")
        
        st.write(f"**Создана:** {parse_datetime(shift['created_at']).strftime('%d.%m.%Y %H:%M')}")
    
    with col2:
        st.subheader("💰 Финансы")
        st.success(f"**Касса:** {shift['cash']:,} руб")
        
        if shift.get('hourly_rate'):
            st.info(f"**Средний час:** {shift['hourly_rate']:,} руб/ч")
        
        st.markdown("---")
        
        st.subheader("📊 Статус")
        if shift.get('is_active'):
            if shift.get('is_paused'):
                st.warning("⏸ На паузе")
            else:
                st.success("🟢 Активна")
        else:
            st.info("✅ Завершена")
        
        if shift.get('awaiting_cash_input'):
            st.error("⏳ Ожидает ввода кассы")
    
    st.markdown("---")
    
    # Вкладки действий
    tab1, tab2, tab3 = st.tabs(["✏️ Редактировать", "📊 История изменений", "🗑️ Удалить"])
    
    with tab1:
        show_edit_form(shift)
    
    with tab2:
        show_edit_history(shift_id)
    
    with tab3:
        show_delete_form(shift)

def show_general_stats():
    """Показывает общую статистику"""
    st.subheader("📊 Общая статистика")
    
    if st.button("← Назад к списку", key="back_from_stats"):
        st.session_state.show_stats = False
        st.rerun()
    
    st.markdown("---")

    conn = get_connection()
    cur = conn.cursor()
    
    # Основные метрики
    col1, col2, col3, col4 = st.columns(4)
    
    cur.execute("SELECT COUNT(*) FROM shifts")
    total_shifts = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM shifts WHERE is_active = TRUE")
    active_shifts = cur.fetchone()[0]
    
    cur.execute("SELECT SUM(cash) FROM shifts")
    total_cash = cur.fetchone()[0] or 0
    
    cur.execute("SELECT AVG(hourly_rate) FROM shifts WHERE hourly_rate > 0")
    avg_hourly = cur.fetchone()[0] or 0
    
    with col1:
        st.metric("Всего смен", total_shifts)
    with col2:
        st.metric("Активных смен", active_shifts)  # ⚠️ УБРАЛ ЗАПЯТУЮ И КНОПКУ
    with col3:
        st.metric("Общая касса", f"{total_cash:,} руб")
    with col4:
        st.metric("Средний час", f"{avg_hourly:.0f} руб/ч")
    
    # Дополнительная статистика
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 По дням (последние 7 дней)")
        cur.execute("""
            SELECT DATE(start_time) as date, COUNT(*) as count, SUM(cash) as cash
            FROM shifts 
            WHERE start_time >= NOW() - INTERVAL '7 days'
            GROUP BY DATE(start_time)
            ORDER BY date DESC
        """)
        daily_stats = cur.fetchall()
        
        if daily_stats:
            df_daily = pd.DataFrame(daily_stats, columns=['date', 'count', 'cash'])
            st.dataframe(df_daily)
        else:
            st.info("Нет данных за последние 7 дней")
    
    with col2:
        st.subheader("👤 По водителям (топ 5)")
        cur.execute("""
            SELECT driver_id, COUNT(*) as shifts, SUM(cash) as total_cash
            FROM shifts 
            GROUP BY driver_id
            ORDER BY total_cash DESC
            LIMIT 5
        """)
        driver_stats = cur.fetchall()
        
        if driver_stats:
            df_drivers = pd.DataFrame(driver_stats, columns=['driver_id', 'shifts', 'total_cash'])
            st.dataframe(df_drivers)
        else:
            st.info("Нет данных по водителям")
    
    cur.close()
    conn.close()

# Эти функции нужно будет реализовать:
def show_edit_form(shift):
    """Форма редактирования смены"""
    st.subheader("✏️ Редактирование смены")
    
    # Преобразуем строки времени в datetime объекты
    start_time_obj = parse_datetime(shift['start_time'])
    end_time_obj = parse_datetime(shift['end_time'])
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Текущие значения:**")
        st.write(f"Начало: `{start_time_obj.strftime('%d.%m.%Y %H:%M')}`")
        st.write(f"Окончание: `{end_time_obj.strftime('%d.%m.%Y %H:%M')}`")
        st.write(f"Касса: `{shift['cash']} руб`")
        if shift.get('hourly_rate'):
            st.write(f"Средний час: `{shift['hourly_rate']} руб/ч`")
        if 'duration_text' in shift:
            st.write(f"Продолжительность: `{shift['duration_text']}`")
    
    with col2:
        st.markdown("**Новые значения:**")
        
        # Поля для редактирования времени начала
        st.markdown("**Время начала:**")
        col_start1, col_start2 = st.columns(2)
        with col_start1:
            new_start_date = st.date_input(
                "Дата начала",
                value=start_time_obj.date(),
                key=f"edit_start_date_{shift['id']}"
            )
        with col_start2:
            new_start_time = st.time_input(
                "Время начала",
                value=start_time_obj.time(),
                key=f"edit_start_time_{shift['id']}"
            )
        new_start = datetime.combine(new_start_date, new_start_time)
        
        # Поля для редактирования времени окончания
        st.markdown("**Время окончания:**")
        col_end1, col_end2 = st.columns(2)
        with col_end1:
            new_end_date = st.date_input(
                "Дата окончания",
                value=end_time_obj.date(),
                key=f"edit_end_date_{shift['id']}"
            )
        with col_end2:
            new_end_time = st.time_input(
                "Время окончания",
                value=end_time_obj.time(),
                key=f"edit_end_time_{shift['id']}"
            )
        new_end = datetime.combine(new_end_date, new_end_time)
        
        new_cash = st.number_input(
            "Новая касса (руб)",
            min_value=0,
            value=shift['cash'],
            key=f"edit_cash_{shift['id']}"
        )
        
        reason = st.text_area(
            "Причина изменения", 
            placeholder="Почему вносите правки?",
            key=f"edit_reason_{shift['id']}"
        )
    
    # Кнопки действий
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("💾 Сохранить изменения", type="primary", key=f"save_edit_{shift['id']}"):
            if reason.strip() == "":
                st.error("Укажите причину изменения")
            else:
                # Определяем ID редактора (пока используем системный)
                editor_id = 0  # 0 = системный пользователь
                
                success, error = save_shift_edit(
                    shift_id=shift['id'],
                    editor_id=editor_id,
                    reason=reason,
                    old_start=start_time_obj,
                    new_start=new_start,
                    old_end=end_time_obj,
                    new_end=new_end,
                    old_cash=shift['cash'],
                    new_cash=new_cash
                )
                
                if success:
                    st.success("✅ Изменения сохранены!")
                    st.info("Обновите страницу чтобы увидеть обновлённые данные")
                    st.rerun()
                else:
                    st.error(f"❌ Ошибка при сохранении: {error}")
    
    with col2:
        if st.button("🔄 Сбросить", type="secondary", key=f"reset_edit_{shift['id']}"):
            st.rerun()
    
    with col3:
        if st.button("❌ Отмена", key=f"cancel_edit_{shift['id']}"):
            st.session_state.selected_shift_id = None
            st.rerun()

def show_edit_history(shift_id):
    """История изменений смены"""
    history = get_edit_history(shift_id)
    if history:
        df_history = pd.DataFrame(history)
        df_history['edited_at'] = pd.to_datetime(df_history['edited_at']).dt.strftime('%d.%m.%Y %H:%M')
        st.dataframe(df_history)
    else:
        st.info("Нет истории изменений")

def show_delete_form(shift):
    """Форма удаления смены"""
    st.subheader("🗑️ Удаление смены")
    
    st.warning("⚠️ Внимание! Это действие необратимо.")
    
    st.write(f"**ID смены:** #{shift['id']}")
    st.write(f"**Водитель:** {shift['driver_id']}")
    st.write(f"**Дата начала:** {parse_datetime(shift['start_time']).strftime('%d.%m.%Y %H:%M')}")
    st.write(f"**Касса:** {shift['cash']} руб")
    
    if shift.get('is_active'):
        st.error("❌ Нельзя удалять активную смену!")
        st.info("Завершите смену в боте перед удалением.")
        return
    
    # Подтверждение удаления
    st.markdown("---")
    confirm_text = st.text_input(
        f"Введите 'УДАЛИТЬ {shift['id']}' для подтверждения:",
        key=f"confirm_delete_{shift['id']}"
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🗑️ Удалить смену", type="primary", key=f"delete_btn_{shift['id']}"):
            if confirm_text == f"УДАЛИТЬ {shift['id']}":
                with st.spinner("Удаление..."):
                    success, error = delete_shift(shift['id'])
                    
                    if success:
                        st.success(f"✅ Смена #{shift['id']} удалена")
                        st.balloons()
                        # Возвращаемся к списку через 2 секунды
                        import time
                        time.sleep(2)
                        st.session_state.selected_shift_id = None
                        st.rerun()
                    else:
                        st.error(f"❌ Ошибка при удалении: {error}")
            else:
                st.error("Неправильный текст подтверждения")
    
    with col2:
        if st.button("❌ Отмена", key=f"cancel_delete_{shift['id']}"):
            st.session_state.selected_shift_id = None
            st.rerun()

def show_export_data():
    """Форма экспорта данных"""
    st.subheader("📤 Экспорт данных")
    
    if st.button("← Назад к списку", key="back_from_export"):
        st.session_state.show_export = False
        st.rerun()

    col1, col2, col3 = st.columns(3)
    
    with col1:
        export_driver = st.number_input(
            "ID водителя (0 = все)",
            min_value=0,
            value=0,
            key="export_driver"
        )
    
    with col2:
        export_start = st.date_input(
            "Дата с",
            value=datetime.now().date() - timedelta(days=30),
            key="export_start"
        )
    
    with col3:
        export_end = st.date_input(
            "Дата по",
            value=datetime.now().date(),
            key="export_end"
        )
    
    if st.button("📊 Сформировать отчет", type="primary"):
        with st.spinner("Формирование отчета..."):
            # Используем существующую функцию поиска
            shifts = search_shifts(
                driver_id=export_driver if export_driver > 0 else None,
                date_filter=None,  # Используем диапазон дат через SQL
                min_cash=None,
                max_cash=None
            )
            
            if shifts:
                df = pd.DataFrame(shifts)
                
                # Форматируем даты
                df['start_time'] = pd.to_datetime(df['start_time']).dt.strftime('%Y-%m-%d %H:%M:%S')
                df['end_time'] = pd.to_datetime(df['end_time']).dt.strftime('%Y-%m-%d %H:%M:%S')
                df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
                
                # Фильтруем по дате
                if export_start:
                    df = df[pd.to_datetime(df['start_time']) >= pd.Timestamp(export_start)]
                if export_end:
                    df = df[pd.to_datetime(df['start_time']) <= pd.Timestamp(export_end + timedelta(days=1))]
                
                if not df.empty:
                    csv = df.to_csv(index=False, encoding='utf-8-sig')
                    
                    # Имя файла
                    filename = f"taxi_shifts_{export_start}_{export_end}"
                    if export_driver > 0:
                        filename += f"_driver_{export_driver}"
                    filename += ".csv"
                    
                    st.success(f"✅ Отчет готов: {len(df)} записей")
                    
                    st.download_button(
                        label="⬇️ Скачать CSV",
                        data=csv,
                        file_name=filename,
                        mime="text/csv",
                        key="download_csv"
                    )
                    
                    # Предпросмотр
                    st.subheader("Предпросмотр данных:")
                    st.dataframe(df.head(10))
                else:
                    st.warning("Нет данных для выбранного диапазона")
            else:
                st.warning("Нет данных для экспорта")

def show_add_shift_form():
    """Форма для ручного добавления смены"""
    st.title("➕ Добавить смену вручную")
    
    if st.button("← Назад к списку"):
        st.session_state.show_add_shift = False
        st.rerun()
    
    st.markdown("---")
    
    # Поля формы
    col1, col2 = st.columns(2)
    
    with col1:
        driver_id = st.number_input(
            "ID водителя",
            min_value=1,
            value=1,
            help="Telegram ID водителя"
        )
        
        st.markdown("**Время начала:**")
        col_start1, col_start2 = st.columns(2)
        with col_start1:
            start_date = st.date_input("Дата начала", value=datetime.now().date(), key="add_start_date")
        with col_start2:
            # Используем текстовое поле для времени
            start_time_str = st.text_input(
                "ЧЧ:ММ",
                value=datetime.now().strftime("%H:%M"),
                key="add_start_time",
                max_chars=5,
                help="Формат: ЧЧ:ММ"
            )
        
        # Парсим время
        try:
            if ':' in start_time_str:
                hour, minute = map(int, start_time_str.split(':'))
                start_time = time(hour % 24, minute % 60)
            else:
                start_time = datetime.time(0, 0)
                st.warning("Используйте формат ЧЧ:ММ. Установлено 00:00")
        except:
            start_time = time(0, 0)
            st.warning("Некорректное время. Установлено 00:00")
        
        start_datetime = datetime.combine(start_date, start_time)
    
    with col2:
        cash = st.number_input(
            "Касса (руб)",
            min_value=0,
            value=0,
            help="Сумма выручки за смену",
            key="add_cash"
        )
        
        st.markdown("**Время окончания:**")
        col_end1, col_end2 = st.columns(2)
        with col_end1:
            end_date = st.date_input("Дата окончания", value=datetime.now().date(), key="add_end_date")
        with col_end2:
            # Используем текстовое поле для времени
            end_time_str = st.text_input(
                "ЧЧ:ММ",
                value=(datetime.now() + timedelta(hours=1)).strftime("%H:%M"),
                key="add_end_time",
                max_chars=5,
                help="Формат: ЧЧ:ММ"
            )
        
        # Парсим время
        try:
            if ':' in end_time_str:
                hour, minute = map(int, end_time_str.split(':'))
                end_time = datetime.time(hour % 24, minute % 60)
            else:
                end_time = datetime.time(0, 0)
                st.warning("Используйте формат ЧЧ:ММ. Установлено 00:00")
        except:
            end_time = datetime.time(0, 0)
            st.warning("Некорректное время. Установлено 00:00")
        
        end_datetime = datetime.combine(end_date, end_time)
    
    # Проверка времени
    if end_datetime <= start_datetime:
        st.error("❌ Время окончания должно быть позже времени начала!")
        st.info(f"Начало: {start_datetime.strftime('%d.%m.%Y %H:%M')}")
        st.info(f"Окончание: {end_datetime.strftime('%d.%m.%Y %H:%M')}")
        return
    
    # Расчёт продолжительности
    duration = end_datetime - start_datetime
    total_seconds = duration.total_seconds()
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    
    if hours > 0 and minutes > 0:
        duration_str = f"{hours} ч {minutes} мин"
    elif hours > 0:
        duration_str = f"{hours} ч"
    else:
        duration_str = f"{minutes} мин"
    
    # Расчёт среднего часа
    if hours > 0:
        hourly_rate = int(cash / hours) if hours > 0 else 0
    else:
        hourly_rate = int(cash / (total_seconds / 3600)) if total_seconds > 0 else 0
    
    st.markdown("---")
    st.markdown("**📊 Итог:**")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"⏱ Продолжительность: {duration_str}")
    with col2:
        st.info(f"💰 Касса: {cash} руб")
    with col3:
        st.info(f"📊 Средний час: {hourly_rate} руб/ч")
    
    st.markdown("---")
    
    # Кнопки действий
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        if st.button("💾 Сохранить смену", type="primary", use_container_width=True):
            # Проверяем корректность времени
            if ':' not in start_time_str or ':' not in end_time_str:
                st.error("❌ Используйте формат ЧЧ:ММ для времени")
                return
            
            success = save_manual_shift(
                driver_id=driver_id,
                start_time=start_datetime,
                end_time=end_datetime,
                cash=cash,
                duration_str=duration_str,
                hourly_rate=hourly_rate
            )
            
            if success:
                st.success(f"✅ Смена для водителя {driver_id} сохранена!")
                st.balloons()
                st.session_state.show_add_shift = False
                st.rerun()
            else:
                st.error("❌ Ошибка при сохранении смены")

if __name__ == "__main__":
    main()