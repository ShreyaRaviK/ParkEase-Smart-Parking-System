from flask import Flask, request, render_template, session, redirect, url_for,flash
import sqlite3
from datetime import datetime
import joblib
import pandas as pd
from weatherAPI import TrichyWeatherClassifier

app = Flask(__name__)
app.secret_key = 'your_secret_key'
DB = 'parking.db'
MODEL_PATH = 'price_prediction_model.pkl'
WEATHER_API_KEY = '2cc77eedcd3b191bf76a5b2e2edce3c4'
classifier = TrichyWeatherClassifier(WEATHER_API_KEY)

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS parking_slots (slot_id INTEGER PRIMARY KEY, status TEXT NOT NULL)''')
    c.execute('SELECT COUNT(*) FROM parking_slots')
    if c.fetchone()[0] == 0:
        for i in range(1, 101):
            c.execute("INSERT INTO parking_slots (slot_id, status) VALUES (?, ?)", (i, 'free'))
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        vehicle_number TEXT NOT NULL,
        vehicle_type TEXT NOT NULL,
        electric TEXT NOT NULL,
        time TEXT NOT NULL,
        slot_id INTEGER NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        mobile TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS parking_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        vehicle_number TEXT NOT NULL,
        vehicle_type TEXT NOT NULL,
        electric TEXT NOT NULL,
        entry_time TEXT NOT NULL,
        exit_time TEXT,
        slot_id INTEGER NOT NULL,
        duration_min REAL,
        price REAL,
        weather TEXT,
        congestion REAL)''')
    conn.commit()
    conn.close()

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))   

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        vehicle_number = request.form['vehicle_number']
        vehicle_type = request.form['vehicle_type']
        electric = request.form['electric']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Validate vehicle type matches model expectations
        valid_vehicle_types = ['auto', 'car', '2-wheeler', 'suv/van']
        if vehicle_type not in valid_vehicle_types:
            flash('Invalid vehicle type selected', 'error')
            return redirect(url_for('index'))

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT slot_id FROM parking_slots WHERE status='free' ORDER BY slot_id ASC LIMIT 1")
        row = c.fetchone()
        if not row:
            return "<h2>No slots available</h2>", 400
        slot_id = row[0]
        c.execute("UPDATE parking_slots SET status='occupied' WHERE slot_id=?", (slot_id,))
        c.execute('''INSERT INTO users (name, phone, vehicle_number, vehicle_type, electric, time, slot_id)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                     (name, phone, vehicle_number, vehicle_type, electric, timestamp, slot_id))
        session['user_id'] = c.lastrowid
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT name, phone, vehicle_number, vehicle_type, electric, time, slot_id FROM users WHERE id=?',
              (session['user_id'],))
    user = c.fetchone()
    conn.close()
    user = list(user)
    user[4] = user[4].title()
    user[3] = user[3].title()
    user = tuple(user)

    if user:
        return render_template('dashboard.html', user=user)
    return "<h2>User not found</h2>", 404

@app.route('/exit', methods=['POST'])
def exit_parking():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT name, vehicle_number, vehicle_type, electric, time, slot_id FROM users WHERE id=?', (session['user_id'],))
    user_data = c.fetchone()

    if user_data:
        name, vehicle_number, vehicle_type, electric, start_time_str, slot_id = user_data
        start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
        exit_time = datetime.now()
        duration_min = round((exit_time - start_time).total_seconds() / 60, 1)
        weather = classifier.classify_weather()
        c.execute('SELECT COUNT(*) FROM parking_slots WHERE status="occupied"')
        filled = c.fetchone()[0]
        congestion = filled / 100.0
        
        # Ensure vehicle_type matches model expectations
        input_df = pd.DataFrame([[duration_min, vehicle_type,
                                "electric" if electric == "yes" else "non-electric",
                                weather, congestion]],
                              columns=["Duration (min)", "Vehicle Type", "Electric", "Weather", "Congestion Level"])
        model = joblib.load(MODEL_PATH)
        price = float(model.predict(input_df)[0])

        # Store exit data in session for the receipt page
        session['exit_data'] = {
            'name': name,
            'vehicle_number': vehicle_number,
            'entry_time': start_time_str,
            'exit_time': exit_time.strftime('%Y-%m-%d %H:%M:%S'),
            'duration_min': duration_min,
            'price': price,
            'slot_id': slot_id
        }
        
        return redirect(url_for('exit_receipt'))

    conn.close()
    return redirect(url_for('index'))

@app.route('/exit_receipt')
def exit_receipt():
    if 'exit_data' not in session or 'user_id' not in session:
        return redirect(url_for('index'))
    
    return render_template('exit.html', **session['exit_data'])

@app.route('/process_payment', methods=['POST'])
def process_payment():
    if 'exit_data' not in session or 'user_id' not in session:
        return redirect(url_for('index'))

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    exit_data = session['exit_data']
    
    # Log the parking session
    c.execute('''INSERT INTO parking_logs 
                (name, phone, vehicle_number, vehicle_type, electric, 
                 entry_time, exit_time, slot_id, duration_min, price, weather, congestion)
                SELECT name, phone, vehicle_number, vehicle_type, electric, 
                       time, ?, slot_id, ?, ?, ?, ?
                FROM users WHERE id=?''',
             (exit_data['exit_time'], exit_data['duration_min'], exit_data['price'], 
              classifier.classify_weather(), exit_data['duration_min']/600, session['user_id']))
    
    c.execute('UPDATE parking_slots SET status="free" WHERE slot_id=?', (exit_data['slot_id'],))
    c.execute('DELETE FROM users WHERE id=?', (session['user_id'],))
    conn.commit()
    conn.close()
    
    # Clear session data
    session.pop('user_id', None)
    session.pop('exit_data', None)
    
    return redirect(url_for('index'))

@app.route('/admin_signup', methods=['GET', 'POST'])
def admin_signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        mobile = request.form['mobile']
        org_password = request.form['org_password']
        if org_password != 'ParkEase@123':
            return "<h2>Invalid organization password!</h2>"
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        try:
            c.execute('INSERT INTO admin (username, password, mobile) VALUES (?, ?, ?)', (username, password, mobile))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "<h2>Username already exists.</h2>"
        conn.close()
        return redirect(url_for('admin_login'))
    return render_template('admin_signup.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('SELECT id FROM admin WHERE username=? AND password=?', (username, password))
        admin = c.fetchone()
        conn.close()
        if admin:
            session['admin_id'] = admin[0]
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'error')  # Add this line
    return render_template('admin_login.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    
    # Get all parking slots
    c.execute('SELECT slot_id, status FROM parking_slots ORDER BY slot_id')
    slots = [{'slot_id': row[0], 'status': row[1], 'user_details': None} for row in c.fetchall()]
    
    # Get all users with their slot information
    c.execute('SELECT * FROM users')
    users = c.fetchall()
    
    # Create a mapping of slot_id to user details
    user_map = {user[7]: user for user in users}
    
    # Update slots with user details if occupied
    for slot in slots:
        if slot['status'] == 'occupied' and slot['slot_id'] in user_map:
            slot['user_details'] = user_map[slot['slot_id']]
    
    # Calculate statistics
    c.execute('SELECT COUNT(*) FROM parking_slots WHERE status="occupied"')
    occupied_count = c.fetchone()[0]
    free_count = 100 - occupied_count
    occupancy_rate = round((occupied_count / 100) * 100, 1)
    
    conn.close()
    
    return render_template('admin_dashboard.html', 
                         slots=slots,
                         occupied_count=occupied_count,
                         free_count=free_count,
                         occupancy_rate=occupancy_rate)

@app.route('/admin_logs')
def admin_logs():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT * FROM parking_logs ORDER BY exit_time DESC')
    logs = c.fetchall()
    logs = [list(log) for log in logs]

    for log in logs:
        if isinstance(log[10], bytes):
            try:
                log[10] = float(int.from_bytes(log[10], byteorder='little', signed=False))
            except Exception:
                log[10] = None
        if isinstance(log[12], bytes):
            try:
                log[12] = float(int.from_bytes(log[12], byteorder='little', signed=False))
            except Exception:
                log[12] = None

    conn.close()
    
    return render_template('admin_logs.html', logs=logs)

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_id', None)
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
    