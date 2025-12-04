import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from datetime import datetime, timedelta
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

def search_shifts(driver_id=None, date=None, min_cash=None, max_cash=None):
    """Поиск смен по фильтрам"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM shifts WHERE 1=1"
    params = []
    
    if driver_id:
        query += " AND driver_id = %s"
        params.append(driver_id)
    
    if date:
        query += " AND DATE(start_time) = %s"
        params.append(date)
    
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

# --- Основной интерфейс ---
def main():
    check_auth()
    
    st.title("🚕 Админ-панель Такси-бота")
    st.markdown("---")
    
    # Боковая панель для поиска
    with st.sidebar:
        st.header("🔍 Поиск смен")
        
        search_method = st.radio(
            "Способ поиска:",
            ["По ID смены", "По фильтрам"]
        )
        
        if search_method == "По ID смены":
            shift_id = st.number_input("ID смены", min_value=1, step=1, value=1)
            if st.button("Найти смену", type="primary"):
                shift = get_shift_by_id(shift_id)
                if shift:
                    st.session_state.selected_shift = shift
                    st.success(f"Найдена смена #{shift_id}")
                else:
                    st.error(f"Смена #{shift_id} не найдена")
        
        else:  # По фильтрам
            driver_id = st.number_input("ID водителя", min_value=1, step=1, value=638440886)
            date = st.date_input("Дата", value=datetime.now().date())
            min_cash = st.number_input("Касса от", min_value=0, value=0)
            max_cash = st.number_input("Касса до", min_value=0, value=100000)
            
            if st.button("Найти", type="primary"):
                shifts = search_shifts(driver_id, date, min_cash, max_cash)
                if shifts:
                    st.session_state.search_results = shifts
                    st.success(f"Найдено {len(shifts)} смен")
                else:
                    st.error("Смены не найдены")
        
        st.markdown("---")
        st.markdown("**Статистика:**")
        
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM shifts")
        total_shifts = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM shift_edits")
        total_edits = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(DISTINCT driver_id) FROM shifts")
        total_drivers = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        st.metric("Всего смен", total_shifts)
        st.metric("Всего правок", total_edits)
        st.metric("Уникальных водителей", total_drivers)
        
        st.markdown("---")
        if st.button("🔄 Обновить страницу"):
            st.rerun()
    
    # Основная область
    tab1, tab2, tab3 = st.tabs(["📋 Список смен", "✏️ Редактирование", "📊 История"])
    
    with tab1:
        st.header("Список смен")
        
        if 'search_results' in st.session_state:
            df = pd.DataFrame(st.session_state.search_results)
            
            # Форматируем даты
            if not df.empty:
                df['start_time'] = pd.to_datetime(df['start_time']).dt.strftime('%d.%m.%Y %H:%M')
                df['end_time'] = pd.to_datetime(df['end_time']).dt.strftime('%d.%m.%Y %H:%M')
                df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%d.%m.%Y %H:%M')
                
                # Показываем таблицу
                st.dataframe(
                    df[['id', 'driver_id', 'start_time', 'end_time', 'cash', 'hourly_rate']],
                    use_container_width=True,
                    column_config={
                        'id': st.column_config.NumberColumn("ID", width="small"),
                        'driver_id': st.column_config.NumberColumn("Водитель", width="small"),
                        'cash': st.column_config.NumberColumn("Касса", format="%d руб"),
                        'hourly_rate': st.column_config.NumberColumn("Средний", format="%d руб/ч"),
                    }
                )
                
                # Кнопка выбора смены для редактирования
                selected_id = st.selectbox(
                    "Выберите смену для редактирования:",
                    df['id'].tolist(),
                    format_func=lambda x: f"Смена #{x}"
                )
                
                if st.button("Редактировать выбранную смену"):
                    shift = get_shift_by_id(selected_id)
                    if shift:
                        st.session_state.selected_shift = shift
                        st.success(f"Смена #{selected_id} загружена для редактирования")
                        st.rerun()
        
        else:
            st.info("Используйте панель поиска слева")
            
            # Быстрый поиск популярных ID
            st.subheader("Быстрый поиск:")
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Смена #1"):
                    shift = get_shift_by_id(1)
                    if shift:
                        st.session_state.selected_shift = shift
                        st.rerun()
            with col2:
                if st.button("Смена #2"):
                    shift = get_shift_by_id(2)
                    if shift:
                        st.session_state.selected_shift = shift
                        st.rerun()
            with col3:
                if st.button("Смена #3"):
                    shift = get_shift_by_id(3)
                    if shift:
                        st.session_state.selected_shift = shift
                        st.rerun()
    
    with tab2:
        st.header("Редактирование смены")
        
        if 'selected_shift' in st.session_state:
            shift = st.session_state.selected_shift
            
            st.subheader(f"Смена #{shift['id']} • Водитель {shift['driver_id']}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Текущие значения:**")
                st.write(f"Начало: `{shift['start_time']}`")
                st.write(f"Окончание: `{shift['end_time']}`")
                st.write(f"Касса: `{shift['cash']} руб`")
                st.write(f"Средний час: `{shift['hourly_rate']} руб/ч`")
                st.write(f"Продолжительность: `{shift['duration_text']}`")
            
            with col2:
                st.markdown("**Новые значения:**")
                
                # Поля для редактирования
                new_start = st.datetime_input(
                    "Новое время начала",
                    value=shift['start_time']
                )
                
                new_end = st.datetime_input(
                    "Новое время окончания", 
                    value=shift['end_time']
                )
                
                new_cash = st.number_input(
                    "Новая касса (руб)",
                    min_value=0,
                    value=shift['cash']
                )
                
                reason = st.text_area("Причина изменения", placeholder="Почему вносите правки?")
            
            # Кнопки действий
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("💾 Сохранить изменения", type="primary"):
                    if reason.strip() == "":
                        st.error("Укажите причину изменения")
                    else:
                        success, error = save_shift_edit(
                            shift_id=shift['id'],
                            editor_id=shift['driver_id'],  # пока используем ID водителя как редактора
                            reason=reason,
                            old_start=shift['start_time'],
                            new_start=new_start,
                            old_end=shift['end_time'],
                            new_end=new_end,
                            old_cash=shift['cash'],
                            new_cash=new_cash
                        )
                        
                        if success:
                            st.success("✅ Изменения сохранены!")
                            st.info("Обновите страницу (F5) чтобы увидеть обновлённые данные")
                            # Очищаем выбранную смену чтобы обновить данные
                            if 'selected_shift' in st.session_state:
                                del st.session_state.selected_shift
                        else:
                            st.error(f"❌ Ошибка при сохранении: {error}")
            
            with col2:
                if st.button("📊 Показать историю"):
                    history = get_edit_history(shift['id'])
                    if history:
                        st.session_state.show_history = True
                        st.rerun()
            
            with col3:
                if st.button("❌ Отмена"):
                    if 'selected_shift' in st.session_state:
                        del st.session_state.selected_shift
                    st.rerun()
        
        else:
            st.info("Выберите смену для редактирования во вкладке 'Список смен'")
    
    with tab3:
        st.header("История изменений")
        
        if 'show_history' in st.session_state and 'selected_shift' in st.session_state:
            shift = st.session_state.selected_shift
            history = get_edit_history(shift['id'])
            
            if history:
                df_history = pd.DataFrame(history)
                
                # Форматируем
                df_history['edited_at'] = pd.to_datetime(df_history['edited_at']).dt.strftime('%d.%m.%Y %H:%M')
                
                # Показываем в виде таблицы
                st.dataframe(
                    df_history[['edited_at', 'editor_id', 'reason', 'old_cash', 'new_cash', 'old_hourly_rate', 'new_hourly_rate']],
                    use_container_width=True,
                    column_config={
                        'edited_at': "Время",
                        'editor_id': "Редактор",
                        'reason': "Причина",
                        'old_cash': "Было (руб)",
                        'new_cash': "Стало (руб)",
                        'old_hourly_rate': "Было (руб/ч)",
                        'new_hourly_rate': "Стало (руб/ч)",
                    }
                )
                
                # Кнопка возврата
                if st.button("← Назад к редактированию"):
                    del st.session_state.show_history
                    st.rerun()
            else:
                st.info("Нет истории изменений для этой смены")
                if st.button("← Назад"):
                    del st.session_state.show_history
                    st.rerun()
        else:
            st.info("Выберите смену чтобы увидеть историю изменений")

if __name__ == "__main__":
    main()