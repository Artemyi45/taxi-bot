from flask import Flask, render_template_string
import json
import os

app = Flask(__name__)
ADMIN_PASSWORD = "taxi2024"  # Замени на свой пароль

@app.route('/admin/<password>')
def admin_dashboard(password):
    if password != ADMIN_PASSWORD:
        return "❌ Неверный пароль"
    
    try:
        with open('shifts.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return "📭 Данных пока нет"
    
    # Статистика
    total_shifts = len(data['shifts'])
    unique_drivers = len(set(shift['user_id'] for shift in data['shifts']))
    
    # HTML шаблон
    html = """
    <h1>🚕 Такси Бот - Админка</h1>
    <div style="background: #f5f5f5; padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        <h3>📊 Общая статистика:</h3>
        <p><strong>Всего смен:</strong> {{ total_shifts }}</p>
        <p><strong>Уникальных водителей:</strong> {{ unique_drivers }}</p>
    </div>
    
    <h3>📋 История смен:</h3>
    <table border="1" style="border-collapse: collapse; width: 100%;">
        <tr style="background: #e0e0e0;">
            <th>Водитель</th>
            <th>Дата</th>
            <th>Начало</th>
            <th>Конец</th>
            <th>Длительность</th>
        </tr>
        {% for shift in shifts %}
        <tr>
            <td>{{ shift.user_id }}</td>
            <td>{{ shift.date }}</td>
            <td>{{ shift.start_time[11:16] }}</td>
            <td>{{ shift.end_time[11:16] }}</td>
            <td>{{ shift.duration }}</td>
        </tr>
        {% endfor %}
    </table>
    """
    
    return render_template_string(html, 
                               total_shifts=total_shifts,
                               unique_drivers=unique_drivers,
                               shifts=data['shifts'][-20:])  # Последние 20 смен

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Берём порт из переменной окружения
    app.run(host='0.0.0.0', port=port, debug=False)