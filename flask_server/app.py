from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from Crypto.Cipher import AES
import base64
import sqlite3
import json
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta

app = Flask(__name__)
socketio = SocketIO(app)

DATABASE = 'weather_data.db'
key = b'This is a key123'
iv = b'This is an IV456'

def to_ist(utc_time):
    ist_time = utc_time + timedelta(hours=5, minutes=30)
    #seconds = int(ist_time.second)
    return ist_time

def get_db():
    conn = sqlite3.connect(DATABASE)
    return conn

def unpad(data):
    return data[:-ord(data[len(data)-1:])]

def decrypt(encrypted_data):
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted_data = unpad(cipher.decrypt(base64.b64decode(encrypted_data)))
    return decrypted_data.decode('utf-8')

def on_message(client, userdata, msg):
    data = json.loads(msg.payload)
    temperature = decrypt(data['temperature'])
    humidity = decrypt(data['humidity'])
    rain = decrypt(data['rain'])
    conn = get_db()
    cur = conn.cursor()
    timestamp = to_ist(datetime.utcnow())
    timestamp = f"{timestamp.hour:02d}:{timestamp.minute:02d}:{timestamp.second:02d}"
    #cur.execute("INSERT INTO weather_data (temperature, humidity, rain) VALUES (?, ?, ?)", (temperature, humidity, rain))
    cur.execute("INSERT INTO weather_data (temperature, humidity, rain, source, timestamp) VALUES (?, ?, ?, 'MQTT', ?)", (temperature, humidity, rain, timestamp))
    conn.commit()
    conn.close()
    print(f"Data received and stored: {temperature}, {humidity}, {rain}")
    
    # Emit data to all connected clients
    socketio.emit('new_weather_data', {'temperature': temperature, 'humidity': humidity, 'rain': rain})

mqtt_broker = "localhost"
client = mqtt.Client()
client.on_message = on_message
client.connect(mqtt_broker, 1883, 60)
client.subscribe("weather/data")
client.loop_start()

@app.route('/')
def index():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM weather_data ORDER BY timestamp DESC LIMIT 10")
    data = cur.fetchall()
    conn.close()
    return render_template('index.html', data=data)

# New API route to serve data as JSON
@app.route('/api/data', methods=['GET'])
def api_data():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    conn = get_db()
    cur = conn.cursor()
    #cur.execute("SELECT * FROM weather_data ORDER BY timestamp DESC LIMIT ? OFFSET ?", (per_page, offset))
    cur.execute("SELECT * FROM weather_data ORDER BY timestamp DESC")
    rows = cur.fetchall()
    conn.close()
    
    data = [
        {'id': row[0], 'temperature': row[1], 'humidity': row[2], 'rain': row[3], 'source': row[4], 'timestamp': row[5]}
        for row in rows
    ]
    return jsonify(data)

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('weather_data')
def handle_weather_data(data):
    temperature = decrypt(data['temperature'])
    humidity = decrypt(data['humidity'])
    rain = decrypt(data['rain'])
    conn = get_db()
    cur = conn.cursor()
    timestamp = to_ist(datetime.utcnow())
    timestamp = f"{timestamp.hour:02d}:{timestamp.minute:02d}:{timestamp.second:02d}"
    cur.execute("INSERT INTO weather_data (temperature, humidity, rain, source, timestamp) VALUES (?, ?, ?, 'SOCKET', ?)", (temperature, humidity, rain, timestamp))
    conn.commit()
    conn.close()
    emit('response', {'status': 'success'})
    print(f"Socket data received and stored: {temperature}, {humidity}, {rain}")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
