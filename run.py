import sqlite3
import json
import re
from flask import Flask, request, Response
import requests
import datetime
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Настройки WhatsApp Business API
WHATSAPP_API_URL = "https://graph.facebook.com/v20.0/375495812322819/messages"
WHATSAPP_TOKEN = "EAAR7LlmQ5F4BOx4zcjQ1D3C4t2bUJIjQMtIi83ddUcDRYp8QgKuKSNUhCpXdBSsBZAnHp5FuVpCm18DsTso8Yh7BRPLlvpG0W0ox5dED1BSTZCptzlyP7lu0yfcFdyHAfLmw49BHMDRQR7ojhNZBnvnMJ5BOF6ESaIYZA65JJwxmtAJckmzBSPNI8XZB8M25ripe1jMPKfD3r6ud0A8W9D1joQSYZD"

# Подключение к базе данных SQLite
conn = sqlite3.connect('salon_appointments.db', check_same_thread=False)
cursor = conn.cursor()
def add_timestamp_column():
    try:
        cursor.execute('''
        ALTER TABLE appointments
        ADD COLUMN timestamp TEXT
        ''')
        conn.commit()
        logging.info("Колонка timestamp успешно добавлена.")
    except sqlite3.OperationalError as e:
        logging.error(f"Ошибка при добавлении колонки: {e}")

add_timestamp_column()
def recreate_table():
    try:
        cursor.execute('DROP TABLE IF EXISTS appointments')
        cursor.execute('''
        CREATE TABLE appointments
        (id INTEGER PRIMARY KEY, date TEXT, time TEXT, service TEXT, client_phone TEXT, timestamp TEXT)
        ''')
        conn.commit()
        logging.info("Таблица appointments была пересоздана с колонкой timestamp.")
    except sqlite3.OperationalError as e:
        logging.error(f"Ошибка при пересоздании таблицы: {e}")

recreate_table()

# Обновляем таблицу для записей (если она еще не существует)
cursor.execute('''
CREATE TABLE IF NOT EXISTS appointments
(id INTEGER PRIMARY KEY, date TEXT, time TEXT, service TEXT, client_phone TEXT, timestamp TEXT)
''')

# Временное хранилище для информации о записи
appointment_info = {}

def send_whatsapp_message(phone_number, message):
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message}
    }
    
    response = requests.post(WHATSAPP_API_URL, headers=headers, data=json.dumps(data))
    if response.status_code == 200:
        logging.info(f"Сообщение успешно отправлено на {phone_number}")
    else:
        logging.error(f"Ошибка при отправке сообщения: {response.status_code}, {response.text}")
    
    return response.json()

def handle_message(message, client_phone):
    if "записаться" in message.lower():
        return "Добрый день! Рады видеть вас в нашем салоне. На какую дату вы хотели бы записаться? (Пожалуйста, укажите дату в формате ДД.ММ.ГГГГ)"
    
    elif is_valid_date(message):
        save_appointment_info(client_phone, 'date', message)
        return "Отлично! На какое время вам удобно? У нас есть свободные окна: 10:00, 13:00, 16:00."
    
    elif is_valid_time(message):
        appointment = get_appointment(client_phone)
        if not appointment.get('date'):
            return "Пожалуйста, сначала укажите дату."
        
        if not is_time_slot_available(appointment['date'], message):
            return "Извините, выбранное время уже занято. Пожалуйста, выберите другое время."
        
        save_appointment_info(client_phone, 'time', message)
        return "Замечательно! Какую услугу вы хотели бы получить? (например, маникюр, педикюр, наращивание)"
    
    elif is_valid_service(message):
        appointment = get_appointment(client_phone)
        if not appointment.get('date') or not appointment.get('time'):
            return "Пожалуйста, сначала укажите дату и время."
        
        if not is_time_slot_available(appointment['date'], appointment['time']):
            return "Извините, выбранное время уже занято. Пожалуйста, выберите другое время."
        
        save_appointment_info(client_phone, 'service', message)
        save_to_database(appointment, client_phone)
        return f"Отлично! Я записал вас на {appointment['service']} {appointment['date']} в {appointment['time']}. Будем ждать вас в нашем салоне. Если у вас появятся вопросы или вам нужно будет изменить запись, пожалуйста, сообщите нам."
    
    else:
        return "Извините, я не совсем понял. Можете, пожалуйста, уточнить ваш запрос?"

        
def is_valid_date(date_string):
    try:
        datetime.strptime(date_string, '%d.%m.%Y')
        return True
    except ValueError:
        return False
def is_time_slot_available(date, time):
    cursor.execute('''
    SELECT COUNT(*) FROM appointments
    WHERE date = ? AND time = ?
    ''', (date, time))
    count = cursor.fetchone()[0]
    return count == 0

def is_valid_time(time_string):
    valid_times = ['10:00', '13:00', '16:00']
    return time_string in valid_times

def is_valid_service(service):
    valid_services = ['маникюр', 'педикюр', 'наращивание']
    return service.lower() in valid_services

def save_appointment_info(client_phone, key, value):
    if client_phone not in appointment_info:
        appointment_info[client_phone] = {}
    appointment_info[client_phone][key] = value

def get_appointment(client_phone):
    return appointment_info.get(client_phone, {})

def save_to_database(appointment, client_phone):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
    INSERT INTO appointments (date, time, service, client_phone, timestamp)
    VALUES (?, ?, ?, ?, ?)
    ''', (appointment.get('date'), appointment.get('time'), appointment.get('service'), client_phone, timestamp))
    conn.commit()

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    logging.info(f"Получены данные: {data}")
    
    if data["object"] == "whatsapp_business_account":
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        
        if "messages" in value:
            message = value["messages"][0]
            phone_number = message["from"]
            text = message["text"]["body"]
            
            logging.info(f"Получено сообщение от {phone_number}: {text}")
            
            response = handle_message(text, phone_number)
            send_whatsapp_message(phone_number, response)
        elif "statuses" in value:
            # Обработка статусных сообщений, если необходимо
            logging.info("Получено статусное сообщение")
        else:
            logging.warning("Получено неизвестное сообщение")
        
        return Response(status=200)
    else:
        logging.error("Неверный формат данных Webhook")
        return Response(status=404)
if __name__ == "__main__":
    app.run(debug=True, port=5001)