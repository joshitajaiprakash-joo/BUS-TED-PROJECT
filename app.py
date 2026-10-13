import os
import io
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

def utc_now():
    """Return timezone-naive UTC datetime for consistent SQLite comparison."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_file, abort
)
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
import qrcode.image.svg

import database

# Initialize Flask App
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'bustd-hackathon-secure-session-key-2024')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

# Initialize Flask-SocketIO (using simple-websocket or threading)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Ensure database is initialized and seeded on startup
database.init_db()
database.seed_demo_data(force=False)


# ==========================================
# CSRF PROTECTION & SECURITY HELPERS
# ==========================================

def get_csrf_token():
    """Get or generate CSRF token stored in session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


app.jinja_env.globals['csrf_token'] = get_csrf_token


@app.before_request
def verify_csrf():
    """Verify CSRF token for state-modifying requests."""
    if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
        # Exempt Socket.IO transport endpoints
        if request.path.startswith('/socket.io'):
            return

        token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')
        # Check if sent in JSON body
        if not token and request.is_json:
            token = request.get_json(silent=True, force=False)
            if isinstance(token, dict):
                token = token.get('csrf_token')

        session_token = session.get('_csrf_token')
        if not session_token or not token or not secrets.compare_digest(token, session_token):
            if request.is_json:
                return jsonify({'status': 'error', 'message': 'Invalid or missing CSRF token'}), 403
            flash('Security validation failed (CSRF token invalid). Please try again.', 'danger')
            return redirect(request.referrer or url_for('login'))


# ==========================================
# AUTHENTICATION & ACCESS DECORATORS
# ==========================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def role_required(required_role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login', next=request.path))
            if session.get('role') != required_role:
                flash('You do not have permission to access that area.', 'danger')
                if session.get('role') == 'driver':
                    return redirect(url_for('driver_dashboard'))
                return redirect(url_for('student_dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_current_user():
    """Fetch current user object from database."""
    if 'user_id' not in session:
        return None
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?;", (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    return user


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'driver':
            return redirect(url_for('driver_dashboard'))
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        if session.get('role') == 'driver':
            return redirect(url_for('driver_dashboard'))
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both email and password.', 'danger')
            return render_template('login.html')

        conn = database.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?;", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            if user['approved'] != 1:
                flash('Your account is pending administrator approval. Please contact campus transport.', 'warning')
                return render_template('login.html')

            session.clear()
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role']
            session['identifier'] = user['identifier']
            session.permanent = True
            # Re-generate CSRF token on login
            get_csrf_token()

            flash(f"Welcome back, {user['name']}!", 'success')
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)

            if user['role'] == 'driver':
                return redirect(url_for('driver_dashboard'))
            return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid email or password. Please check your credentials.', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', '').strip().lower()
        identifier = request.form.get('identifier', '').strip().upper()
        phone = request.form.get('phone', '').strip()

        # Validation
        if not all([name, email, password, confirm_password, role, identifier]):
            flash('All required fields must be filled.', 'danger')
            return render_template('register.html')

        if role not in ['student', 'driver']:
            flash('Invalid role selected.', 'danger')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('register.html')

        conn = database.get_db()
        cursor = conn.cursor()

        # Check existing email or identifier
        cursor.execute("SELECT id FROM users WHERE email = ? OR identifier = ?;", (email, identifier))
        if cursor.fetchone():
            conn.close()
            flash('An account with this email or ID already exists.', 'danger')
            return render_template('register.html')

        # Public driver registrations require admin approval; students auto-approved
        approved_status = 1 if role == 'student' else 0
        pw_hash = generate_password_hash(password)

        try:
            cursor.execute("""
            INSERT INTO users (name, email, password_hash, role, identifier, phone, approved)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (name, email, pw_hash, role, identifier, phone, approved_status))
            user_id = cursor.lastrowid

            # If student, assign to default Route 1 & BUS-12 for demo convenience if available
            if role == 'student':
                cursor.execute("""
                INSERT OR IGNORE INTO student_assignments (student_id, bus_id, route_id, default_stop_id)
                VALUES (?, 1, 1, 1);
                """, (user_id,))

                # Welcome notification
                cursor.execute("""
                INSERT INTO notifications (user_id, title, message, type)
                VALUES (?, 'Welcome to BUS-TED!', 'Registration successful. You are enrolled in campus transit tracking.', 'success');
                """, (user_id,))

            conn.commit()
            conn.close()

            if role == 'driver':
                flash('Driver registration submitted! For security, driver accounts must be approved by campus transit admin before starting trips.', 'info')
            else:
                flash('Registration successful! Please log in with your credentials.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            conn.rollback()
            conn.close()
            flash('Registration failed due to a system error. Please try again.', 'danger')

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


# ==========================================
# STUDENT DASHBOARD & ACTIONS
# ==========================================

@app.route('/student/dashboard')
@role_required('student')
def student_dashboard():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    # Get student info & assigned bus/route
    cursor.execute("""
    SELECT u.*, sa.bus_id, sa.route_id, sa.default_stop_id,
           b.bus_number, b.registration_number, b.capacity, b.model as bus_model,
           r.route_number, r.route_name, r.start_point, r.destination, r.estimated_duration_min,
           rs.stop_name as default_stop_name
    FROM users u
    LEFT JOIN student_assignments sa ON u.id = sa.student_id
    LEFT JOIN buses b ON sa.bus_id = b.id
    LEFT JOIN routes r ON sa.route_id = r.id
    LEFT JOIN route_stops rs ON sa.default_stop_id = rs.id
    WHERE u.id = ?;
    """, (user_id,))
    student_data = cursor.fetchone()

    # Route stops
    stops = []
    if student_data and student_data['route_id']:
        cursor.execute("""
        SELECT * FROM route_stops
        WHERE route_id = ?
        ORDER BY stop_order ASC;
        """, (student_data['route_id'],))
        stops = cursor.fetchall()

    # Driver details for this bus & route
    driver_info = None
    if student_data and student_data['bus_id']:
        cursor.execute("""
        SELECT u.name, u.phone, u.identifier
        FROM driver_assignments da
        JOIN users u ON da.driver_id = u.id
        WHERE da.bus_id = ? AND da.is_active = 1
        LIMIT 1;
        """, (student_data['bus_id'],))
        driver_info = cursor.fetchone()

    # Check for Active Trip on this bus
    active_trip = None
    latest_location = None
    is_live = False
    boarded = False

    if student_data and student_data['bus_id']:
        cursor.execute("""
        SELECT t.*, u.name as driver_name
        FROM trips t
        JOIN users u ON t.driver_id = u.id
        WHERE t.bus_id = ? AND t.status = 'active'
        ORDER BY t.started_at DESC LIMIT 1;
        """, (student_data['bus_id'],))
        active_trip = cursor.fetchone()

        if active_trip:
            # Check if student already boarded this active trip
            cursor.execute("""
            SELECT * FROM boarding_records
            WHERE trip_id = ? AND student_id = ?;
            """, (active_trip['id'], user_id))
            boarded_record = cursor.fetchone()
            if boarded_record:
                boarded = True

            # Get latest GPS location
            cursor.execute("""
            SELECT * FROM bus_locations
            WHERE trip_id = ?
            ORDER BY recorded_at DESC LIMIT 1;
            """, (active_trip['id'],))
            latest_location = cursor.fetchone()

            if latest_location:
                # Calculate if update is within last 90 seconds
                try:
                    loc_time = datetime.fromisoformat(latest_location['recorded_at'].replace('Z', ''))
                    age = (utc_now() - loc_time).total_seconds()
                    if age <= 90:
                        is_live = True
                except Exception:
                    is_live = True

    # Campus Wide Summary Stats (as seen on UI mockup)
    cursor.execute("SELECT COUNT(*) FROM trips WHERE status = 'active';")
    active_buses_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM routes;")
    active_routes_count = cursor.fetchone()[0]

    today_str = utc_now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM trips WHERE date(started_at) = date('now');")
    todays_trips_count = cursor.fetchone()[0]

    # Calculate current bus occupancy or average
    bus_capacity = student_data['capacity'] if student_data and student_data['capacity'] else 50
    current_passengers = active_trip['passenger_count'] if active_trip else 0
    seats_available = max(0, bus_capacity - current_passengers)

    # Recent notifications
    cursor.execute("""
    SELECT * FROM notifications
    WHERE user_id = ?
    ORDER BY created_at DESC LIMIT 5;
    """, (user_id,))
    recent_notifications = cursor.fetchall()

    cursor.execute("""
    SELECT COUNT(*) FROM notifications
    WHERE user_id = ? AND is_read = 0;
    """, (user_id,))
    unread_notif_count = cursor.fetchone()[0]

    conn.close()

    return render_template(
        'student_dashboard.html',
        student=student_data,
        stops=stops,
        driver=driver_info,
        active_trip=active_trip,
        latest_location=latest_location,
        is_live=is_live,
        boarded=boarded,
        active_buses_count=active_buses_count,
        active_routes_count=active_routes_count,
        todays_trips_count=todays_trips_count,
        bus_capacity=bus_capacity,
        current_passengers=current_passengers,
        seats_available=seats_available,
        recent_notifications=recent_notifications,
        unread_notif_count=unread_notif_count
    )


@app.route('/my-bus')
@login_required
def my_bus():
    user_id = session['user_id']
    role = session['role']
    conn = database.get_db()
    cursor = conn.cursor()

    if role == 'student':
        cursor.execute("""
        SELECT sa.bus_id, sa.route_id, b.bus_number, b.registration_number, b.capacity, b.model,
               r.route_number, r.route_name, r.start_point, r.destination, r.estimated_duration_min
        FROM student_assignments sa
        JOIN buses b ON sa.bus_id = b.id
        JOIN routes r ON sa.route_id = r.id
        WHERE sa.student_id = ?;
        """, (user_id,))
        bus_data = cursor.fetchone()
    else:
        cursor.execute("""
        SELECT da.bus_id, da.route_id, b.bus_number, b.registration_number, b.capacity, b.model,
               r.route_number, r.route_name, r.start_point, r.destination, r.estimated_duration_min
        FROM driver_assignments da
        JOIN buses b ON da.bus_id = b.id
        JOIN routes r ON da.route_id = r.id
        WHERE da.driver_id = ? AND da.is_active = 1;
        """, (user_id,))
        bus_data = cursor.fetchone()

    stops = []
    active_trip = None
    latest_location = None

    if bus_data:
        cursor.execute("""
        SELECT * FROM route_stops
        WHERE route_id = ?
        ORDER BY stop_order ASC;
        """, (bus_data['route_id'],))
        stops = cursor.fetchall()

        cursor.execute("""
        SELECT t.*, u.name as driver_name
        FROM trips t
        JOIN users u ON t.driver_id = u.id
        WHERE t.bus_id = ? AND t.status = 'active'
        ORDER BY t.started_at DESC LIMIT 1;
        """, (bus_data['bus_id'],))
        active_trip = cursor.fetchone()

        if active_trip:
            cursor.execute("""
            SELECT * FROM bus_locations
            WHERE trip_id = ?
            ORDER BY recorded_at DESC LIMIT 1;
            """, (active_trip['id'],))
            latest_location = cursor.fetchone()

    # Unread notifications
    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0;", (user_id,))
    unread_notif_count = cursor.fetchone()[0]

    conn.close()

    return render_template(
        'my_bus.html',
        bus=bus_data,
        stops=stops,
        active_trip=active_trip,
        latest_location=latest_location,
        unread_notif_count=unread_notif_count
    )


@app.route('/scan-qr')
@role_required('student')
def scan_qr():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT sa.bus_id, b.bus_number, r.route_name
    FROM student_assignments sa
    JOIN buses b ON sa.bus_id = b.id
    JOIN routes r ON sa.route_id = r.id
    WHERE sa.student_id = ?;
    """, (user_id,))
    assigned_bus = cursor.fetchone()

    # Check unread notifications count
    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0;", (user_id,))
    unread_notif_count = cursor.fetchone()[0]
    conn.close()

    return render_template('scan_qr.html', assigned_bus=assigned_bus, unread_notif_count=unread_notif_count)


# ==========================================
# SECURE QR SCAN & ATTENDANCE VERIFICATION API
# ==========================================

@app.route('/api/student/scan-qr', methods=['POST'])
@role_required('student')
def api_scan_qr():
    """Verify scanned QR token, prevent duplicates, record attendance, and notify driver."""
    user_id = session['user_id']
    data = request.get_json(silent=True) or request.form

    token_str = (data.get('qr_token') or data.get('token') or '').strip()
    if not token_str:
        return jsonify({'status': 'error', 'message': 'No QR code data provided.'}), 400

    conn = database.get_db()
    cursor = conn.cursor()

    try:
        # 1. Lookup QR token
        cursor.execute("""
        SELECT qt.*, t.id as active_trip_id, t.bus_id as trip_bus_id, t.route_id, t.driver_id, t.status as trip_status,
               b.bus_number, b.registration_number, r.route_name
        FROM qr_tokens qt
        JOIN trips t ON qt.trip_id = t.id
        JOIN buses b ON t.bus_id = b.id
        JOIN routes r ON t.route_id = r.id
        WHERE qt.token = ? AND qt.is_active = 1;
        """, (token_str,))
        token_record = cursor.fetchone()

        if not token_record:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Invalid or inactive QR code.'}), 400

        # 2. Check token expiry
        try:
            exp_time = datetime.fromisoformat(token_record['expires_at'].replace('Z', ''))
            if utc_now() > exp_time:
                conn.close()
                return jsonify({'status': 'error', 'message': 'This boarding QR code has expired. Please ask driver to refresh.'}), 400
        except Exception:
            pass

        # 3. Check Trip is currently active
        if token_record['trip_status'] != 'active':
            conn.close()
            return jsonify({'status': 'error', 'message': 'Trip is not currently active.'}), 400

        trip_id = token_record['active_trip_id']
        bus_id = token_record['trip_bus_id']

        # 4. Check if student already boarded this trip (UNIQUE constraint check)
        cursor.execute("""
        SELECT id, scanned_at FROM boarding_records
        WHERE student_id = ? AND trip_id = ?;
        """, (user_id, trip_id))
        existing_record = cursor.fetchone()
        if existing_record:
            conn.close()
            return jsonify({
                'status': 'error',
                'message': f"Duplicate scan: You have already boarded this trip on {token_record['bus_number']} at {existing_record['scanned_at']}."
            }), 409

        # 5. Insert new boarding record
        cursor.execute("""
        INSERT INTO boarding_records (student_id, trip_id, bus_id, scanned_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP);
        """, (user_id, trip_id, bus_id))

        # 6. Update passenger count in trips table
        cursor.execute("""
        UPDATE trips
        SET passenger_count = (SELECT COUNT(*) FROM boarding_records WHERE trip_id = ?)
        WHERE id = ?;
        """, (trip_id, trip_id))

        # Get updated count
        cursor.execute("SELECT passenger_count FROM trips WHERE id = ?;", (trip_id,))
        new_passenger_count = cursor.fetchone()[0]

        # 7. Add notification for student
        student_name = session.get('name', 'Student')
        cursor.execute("""
        INSERT INTO notifications (user_id, title, message, type)
        VALUES (?, 'Boarding Confirmed', ?, 'success');
        """, (user_id, f"Successfully boarded {token_record['bus_number']} ({token_record['route_name']}). Have a safe journey!"))

        # 8. Add notification for driver
        cursor.execute("""
        INSERT INTO notifications (user_id, title, message, type)
        VALUES (?, 'Passenger Boarded', ?, 'info');
        """, (token_record['driver_id'], f"{student_name} ({session.get('identifier')}) boarded {token_record['bus_number']}."))

        conn.commit()

        # Emit real-time Socket.IO event to driver and trip room!
        timestamp_str = utc_now().strftime('%H:%M:%S')
        socketio.emit('passenger_boarded_event', {
            'trip_id': trip_id,
            'bus_id': bus_id,
            'bus_number': token_record['bus_number'],
            'student_name': student_name,
            'student_id': session.get('identifier'),
            'scanned_at': timestamp_str,
            'passenger_count': new_passenger_count
        }, room=f"trip_{trip_id}")

        # Also emit to global live update for dashboard count
        socketio.emit('occupancy_updated', {
            'trip_id': trip_id,
            'bus_number': token_record['bus_number'],
            'passenger_count': new_passenger_count
        })

        conn.close()

        return jsonify({
            'status': 'success',
            'message': f"Boarding Verified! Welcome aboard {token_record['bus_number']}.",
            'bus_number': token_record['bus_number'],
            'route_name': token_record['route_name'],
            'time': timestamp_str,
            'passenger_count': new_passenger_count
        }), 200

    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify({'status': 'error', 'message': 'Duplicate attendance record detected.'}), 409
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'status': 'error', 'message': f'Server error processing boarding: {str(e)}'}), 500


# ==========================================
# DRIVER DASHBOARD & TRIP MANAGEMENT
# ==========================================

@app.route('/driver/dashboard')
@role_required('driver')
def driver_dashboard():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    # Driver assignment
    cursor.execute("""
    SELECT da.*, b.bus_number, b.registration_number, b.capacity, b.model,
           r.route_number, r.route_name, r.start_point, r.destination, r.estimated_duration_min
    FROM driver_assignments da
    JOIN buses b ON da.bus_id = b.id
    JOIN routes r ON da.route_id = r.id
    WHERE da.driver_id = ? AND da.is_active = 1
    LIMIT 1;
    """, (user_id,))
    driver_assignment = cursor.fetchone()

    # Check for Active Trip
    active_trip = None
    qr_token = None
    passengers = []
    latest_location = None

    if driver_assignment:
        cursor.execute("""
        SELECT * FROM trips
        WHERE driver_id = ? AND status = 'active'
        ORDER BY started_at DESC LIMIT 1;
        """, (user_id,))
        active_trip = cursor.fetchone()

        if active_trip:
            # Active QR Token
            cursor.execute("""
            SELECT * FROM qr_tokens
            WHERE trip_id = ? AND is_active = 1
            ORDER BY created_at DESC LIMIT 1;
            """, (active_trip['id'],))
            qr_token = cursor.fetchone()

            # Passenger list
            cursor.execute("""
            SELECT br.*, u.name as student_name, u.identifier as student_code, u.phone
            FROM boarding_records br
            JOIN users u ON br.student_id = u.id
            WHERE br.trip_id = ?
            ORDER BY br.scanned_at DESC;
            """, (active_trip['id'],))
            passengers = cursor.fetchall()

            # Latest GPS
            cursor.execute("""
            SELECT * FROM bus_locations
            WHERE trip_id = ?
            ORDER BY recorded_at DESC LIMIT 1;
            """, (active_trip['id'],))
            latest_location = cursor.fetchone()

    # Route stops
    stops = []
    if driver_assignment and driver_assignment['route_id']:
        cursor.execute("""
        SELECT * FROM route_stops
        WHERE route_id = ?
        ORDER BY stop_order ASC;
        """, (driver_assignment['route_id'],))
        stops = cursor.fetchall()

    # Trip history
    cursor.execute("""
    SELECT t.*, r.route_name, b.bus_number
    FROM trips t
    JOIN routes r ON t.route_id = r.id
    JOIN buses b ON t.bus_id = b.id
    WHERE t.driver_id = ? AND t.status = 'completed'
    ORDER BY t.ended_at DESC LIMIT 5;
    """, (user_id,))
    recent_completed_trips = cursor.fetchall()

    # Unread notifications
    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0;", (user_id,))
    unread_notif_count = cursor.fetchone()[0]

    conn.close()

    return render_template(
        'driver_dashboard.html',
        assignment=driver_assignment,
        active_trip=active_trip,
        qr_token=qr_token,
        passengers=passengers,
        latest_location=latest_location,
        stops=stops,
        recent_trips=recent_completed_trips,
        unread_notif_count=unread_notif_count
    )


@app.route('/driver/trip/start', methods=['POST'])
@role_required('driver')
def start_trip():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    # Check assignment
    cursor.execute("""
    SELECT * FROM driver_assignments
    WHERE driver_id = ? AND is_active = 1
    LIMIT 1;
    """, (user_id,))
    assignment = cursor.fetchone()

    if not assignment:
        conn.close()
        flash('You have no active bus or route assignment. Please contact administrator.', 'danger')
        return redirect(url_for('driver_dashboard'))

    bus_id = assignment['bus_id']
    route_id = assignment['route_id']

    # Check if this bus already has an active trip running
    cursor.execute("SELECT id FROM trips WHERE bus_id = ? AND status = 'active';", (bus_id,))
    if cursor.fetchone():
        conn.close()
        flash('An active trip is already running for this bus.', 'warning')
        return redirect(url_for('driver_dashboard'))

    # Check if driver has active trip running
    cursor.execute("SELECT id FROM trips WHERE driver_id = ? AND status = 'active';", (user_id,))
    if cursor.fetchone():
        conn.close()
        flash('You already have an active trip running.', 'warning')
        return redirect(url_for('driver_dashboard'))

    # Start Trip
    cursor.execute("""
    INSERT INTO trips (bus_id, route_id, driver_id, status, started_at, passenger_count)
    VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP, 0);
    """, (bus_id, route_id, user_id))
    trip_id = cursor.lastrowid

    # Generate cryptographically secure QR token (valid for 30 minutes)
    token = secrets.token_urlsafe(32)
    expires_at = (utc_now() + timedelta(minutes=30)).isoformat()

    cursor.execute("""
    INSERT INTO qr_tokens (trip_id, bus_id, token, expires_at, is_active)
    VALUES (?, ?, ?, ?, 1);
    """, (trip_id, bus_id, token, expires_at))

    # Notify students assigned to this bus and route
    cursor.execute("""
    SELECT student_id FROM student_assignments WHERE bus_id = ? OR route_id = ?;
    """, (bus_id, route_id))
    students = cursor.fetchall()

    for s in students:
        cursor.execute("""
        INSERT INTO notifications (user_id, title, message, type)
        VALUES (?, 'Trip Started', 'Your bus has started its trip. Live tracking is now active.', 'trip');
        """, (s['student_id'],))

    conn.commit()

    # Broadcast event via Socket.IO
    socketio.emit('trip_status_changed', {
        'trip_id': trip_id,
        'bus_id': bus_id,
        'route_id': route_id,
        'status': 'active',
        'message': 'Trip has started.'
    })

    conn.close()
    flash('Trip started successfully! QR code generated and GPS broadcasting is now active.', 'success')
    return redirect(url_for('driver_dashboard'))


@app.route('/driver/trip/end', methods=['POST'])
@role_required('driver')
def end_trip():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    # Find driver's active trip
    cursor.execute("""
    SELECT * FROM trips WHERE driver_id = ? AND status = 'active' LIMIT 1;
    """, (user_id,))
    active_trip = cursor.fetchone()

    if not active_trip:
        conn.close()
        flash('No active trip found to end.', 'warning')
        return redirect(url_for('driver_dashboard'))

    trip_id = active_trip['id']
    bus_id = active_trip['bus_id']
    route_id = active_trip['route_id']

    # Update trip
    cursor.execute("""
    UPDATE trips
    SET status = 'completed', ended_at = CURRENT_TIMESTAMP
    WHERE id = ?;
    """, (trip_id,))

    # Invalidate QR tokens
    cursor.execute("UPDATE qr_tokens SET is_active = 0 WHERE trip_id = ?;", (trip_id,))

    # Notify students
    cursor.execute("""
    SELECT student_id FROM student_assignments WHERE bus_id = ? OR route_id = ?;
    """, (bus_id, route_id))
    students = cursor.fetchall()
    for s in students:
        cursor.execute("""
        INSERT INTO notifications (user_id, title, message, type)
        VALUES (?, 'Trip Ended', 'The bus trip has completed. Thank you for riding BUS-TED!', 'info');
        """, (s['student_id'],))

    conn.commit()

    # Broadcast trip ended via Socket.IO
    socketio.emit('trip_status_changed', {
        'trip_id': trip_id,
        'bus_id': bus_id,
        'route_id': route_id,
        'status': 'completed',
        'message': 'Trip has ended.'
    })

    conn.close()
    flash('Trip ended successfully. QR token invalidated and passenger records archived.', 'info')
    return redirect(url_for('driver_dashboard'))


@app.route('/driver/trip/refresh-qr', methods=['POST'])
@role_required('driver')
def refresh_qr():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT * FROM trips WHERE driver_id = ? AND status = 'active' LIMIT 1;
    """, (user_id,))
    active_trip = cursor.fetchone()

    if not active_trip:
        conn.close()
        return jsonify({'status': 'error', 'message': 'No active trip running.'}), 400

    trip_id = active_trip['id']
    bus_id = active_trip['bus_id']

    # Invalidate old tokens
    cursor.execute("UPDATE qr_tokens SET is_active = 0 WHERE trip_id = ?;", (trip_id,))

    # Create new token
    new_token = secrets.token_urlsafe(32)
    expires_at = (utc_now() + timedelta(minutes=30)).isoformat()

    cursor.execute("""
    INSERT INTO qr_tokens (trip_id, bus_id, token, expires_at, is_active)
    VALUES (?, ?, ?, ?, 1);
    """, (trip_id, bus_id, new_token, expires_at))

    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': 'Boarding QR refreshed successfully.',
        'qr_token': new_token,
        'expires_at': expires_at
    })


@app.route('/api/driver/qr-code/<int:trip_id>')
@login_required
def get_qr_image(trip_id):
    """Generate PNG QR code image directly using Python's qrcode library."""
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT token FROM qr_tokens
    WHERE trip_id = ? AND is_active = 1
    ORDER BY created_at DESC LIMIT 1;
    """, (trip_id,))
    record = cursor.fetchone()
    conn.close()

    if not record:
        abort(404, description="No active QR token found for this trip.")

    token = record['token']

    # Generate QR Code using Python qrcode
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(token)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#0e1726", back_color="#ffffff")

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    return send_file(buf, mimetype='image/png')


# ==========================================
# REAL-TIME GPS TRACKING & BROADCASTING
# ==========================================

@app.route('/driver/gps-broadcast')
@role_required('driver')
def gps_broadcast():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT da.*, b.bus_number, b.registration_number, r.route_name
    FROM driver_assignments da
    JOIN buses b ON da.bus_id = b.id
    JOIN routes r ON da.route_id = r.id
    WHERE da.driver_id = ? AND da.is_active = 1;
    """, (user_id,))
    assignment = cursor.fetchone()

    cursor.execute("""
    SELECT * FROM trips WHERE driver_id = ? AND status = 'active' LIMIT 1;
    """, (user_id,))
    active_trip = cursor.fetchone()

    stops = []
    if assignment and assignment['route_id']:
        cursor.execute("SELECT * FROM route_stops WHERE route_id = ? ORDER BY stop_order ASC;", (assignment['route_id'],))
        stops = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0;", (user_id,))
    unread_notif_count = cursor.fetchone()[0]

    conn.close()

    return render_template(
        'gps_broadcast.html',
        assignment=assignment,
        active_trip=active_trip,
        stops=stops,
        unread_notif_count=unread_notif_count
    )


@app.route('/api/driver/gps', methods=['POST'])
@role_required('driver')
def record_driver_gps():
    """Accept real browser GPS coordinates from authenticated driver and broadcast in real-time."""
    user_id = session['user_id']
    data = request.get_json(silent=True) or request.form

    try:
        lat = float(data.get('latitude'))
        lng = float(data.get('longitude'))
        accuracy = float(data.get('accuracy', 0))
        speed = float(data.get('speed', 0)) if data.get('speed') is not None else None
        heading = float(data.get('heading', 0)) if data.get('heading') is not None else None
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid GPS coordinates format.'}), 400

    # Strict coordinate bounds validation
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return jsonify({'status': 'error', 'message': 'GPS coordinates outside valid planetary range.'}), 400

    conn = database.get_db()
    cursor = conn.cursor()

    # Verify driver has active trip
    cursor.execute("""
    SELECT t.*, b.bus_number
    FROM trips t
    JOIN buses b ON t.bus_id = b.id
    WHERE t.driver_id = ? AND t.status = 'active'
    LIMIT 1;
    """, (user_id,))
    active_trip = cursor.fetchone()

    if not active_trip:
        conn.close()
        return jsonify({'status': 'error', 'message': 'No active trip found for this driver.'}), 403

    trip_id = active_trip['id']
    bus_id = active_trip['bus_id']
    bus_number = active_trip['bus_number']

    # Insert location in database
    cursor.execute("""
    INSERT INTO bus_locations (trip_id, bus_id, latitude, longitude, accuracy, speed, heading, recorded_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
    """, (trip_id, bus_id, lat, lng, accuracy, speed, heading))
    conn.commit()

    recorded_at = utc_now().strftime('%Y-%m-%d %H:%M:%S UTC')
    conn.close()

    # Real-time Broadcast via Socket.IO
    socketio.emit('bus_location_updated', {
        'trip_id': trip_id,
        'bus_id': bus_id,
        'bus_number': bus_number,
        'latitude': lat,
        'longitude': lng,
        'accuracy': accuracy,
        'speed': speed,
        'heading': heading,
        'recorded_at': recorded_at,
        'is_live': True
    })

    return jsonify({
        'status': 'success',
        'trip_id': trip_id,
        'recorded_at': recorded_at
    }), 200


@app.route('/driver/passenger-feed')
@role_required('driver')
def passenger_feed():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    # Active trip
    cursor.execute("""
    SELECT t.*, b.bus_number, b.registration_number, b.capacity, r.route_name
    FROM trips t
    JOIN buses b ON t.bus_id = b.id
    JOIN routes r ON t.route_id = r.id
    WHERE t.driver_id = ? AND t.status = 'active'
    LIMIT 1;
    """, (user_id,))
    active_trip = cursor.fetchone()

    passengers = []
    if active_trip:
        cursor.execute("""
        SELECT br.*, u.name as student_name, u.identifier as student_code, u.phone, rs.stop_name
        FROM boarding_records br
        JOIN users u ON br.student_id = u.id
        LEFT JOIN route_stops rs ON br.stop_id = rs.id
        WHERE br.trip_id = ?
        ORDER BY br.scanned_at DESC;
        """, (active_trip['id'],))
        passengers = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0;", (user_id,))
    unread_notif_count = cursor.fetchone()[0]

    conn.close()

    return render_template(
        'passenger_feed.html',
        active_trip=active_trip,
        passengers=passengers,
        unread_notif_count=unread_notif_count
    )


# ==========================================
# ROUTES & STOPS PAGE
# ==========================================

@app.route('/routes')
@login_required
def routes_list():
    conn = database.get_db()
    cursor = conn.cursor()

    # Fetch all routes
    cursor.execute("SELECT * FROM routes ORDER BY route_number ASC;")
    routes = cursor.fetchall()

    # Fetch all stops grouped by route
    cursor.execute("SELECT * FROM route_stops ORDER BY route_id, stop_order ASC;")
    all_stops = cursor.fetchall()

    # Fetch active trips and buses
    cursor.execute("""
    SELECT t.route_id, t.bus_id, b.bus_number, b.registration_number, u.name as driver_name
    FROM trips t
    JOIN buses b ON t.bus_id = b.id
    JOIN users u ON t.driver_id = u.id
    WHERE t.status = 'active';
    """)
    active_trips_raw = cursor.fetchall()
    active_trips_by_route = {item['route_id']: item for item in active_trips_raw}

    # Group stops by route_id
    stops_by_route = {}
    for stop in all_stops:
        rid = stop['route_id']
        if rid not in stops_by_route:
            stops_by_route[rid] = []
        stops_by_route[rid].append(dict(stop))

    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0;", (session['user_id'],))
    unread_notif_count = cursor.fetchone()[0]

    conn.close()

    return render_template(
        'routes.html',
        routes=routes,
        stops_by_route=stops_by_route,
        active_trips=active_trips_by_route,
        unread_notif_count=unread_notif_count
    )


# ==========================================
# NOTIFICATIONS MANAGEMENT
# ==========================================

@app.route('/notifications')
@login_required
def notifications_view():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT * FROM notifications
    WHERE user_id = ?
    ORDER BY created_at DESC;
    """, (user_id,))
    notifs = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0;", (user_id,))
    unread_notif_count = cursor.fetchone()[0]

    conn.close()

    return render_template('notifications.html', notifications=notifs, unread_notif_count=unread_notif_count)


@app.route('/notifications/mark-read/<int:notif_id>', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE notifications
    SET is_read = 1
    WHERE id = ? AND user_id = ?;
    """, (notif_id, user_id))
    conn.commit()
    conn.close()

    if request.is_json:
        return jsonify({'status': 'success'})
    return redirect(url_for('notifications_view'))


@app.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE notifications
    SET is_read = 1
    WHERE user_id = ?;
    """, (user_id,))
    conn.commit()
    conn.close()

    if request.is_json:
        return jsonify({'status': 'success'})
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('notifications_view'))


# ==========================================
# TRIP HISTORY & PROFILE
# ==========================================

@app.route('/trip-history')
@login_required
def trip_history():
    user_id = session['user_id']
    role = session['role']
    conn = database.get_db()
    cursor = conn.cursor()

    history = []
    if role == 'student':
        cursor.execute("""
        SELECT br.scanned_at, t.started_at, t.ended_at, t.status as trip_status,
               b.bus_number, b.registration_number, r.route_name, r.route_number,
               u.name as driver_name
        FROM boarding_records br
        JOIN trips t ON br.trip_id = t.id
        JOIN buses b ON br.bus_id = b.id
        JOIN routes r ON t.route_id = r.id
        JOIN users u ON t.driver_id = u.id
        WHERE br.student_id = ?
        ORDER BY br.scanned_at DESC;
        """, (user_id,))
        history = cursor.fetchall()
    else:
        cursor.execute("""
        SELECT t.*, b.bus_number, b.registration_number, r.route_name, r.route_number
        FROM trips t
        JOIN buses b ON t.bus_id = b.id
        JOIN routes r ON t.route_id = r.id
        WHERE t.driver_id = ?
        ORDER BY t.started_at DESC;
        """, (user_id,))
        history = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0;", (user_id,))
    unread_notif_count = cursor.fetchone()[0]

    conn.close()

    return render_template('trip_history.html', history=history, unread_notif_count=unread_notif_count)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session['user_id']
    conn = database.get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        name = request.form.get('name', '').strip()

        if name:
            cursor.execute("""
            UPDATE users
            SET name = ?, phone = ?
            WHERE id = ?;
            """, (name, phone, user_id))
            conn.commit()
            session['name'] = name
            flash('Profile updated successfully!', 'success')
        else:
            flash('Name cannot be empty.', 'danger')

    # Get complete user details
    cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
    user = cursor.fetchone()

    # Assignment details
    assignment = None
    if session['role'] == 'student':
        cursor.execute("""
        SELECT sa.*, b.bus_number, b.registration_number, r.route_name, r.route_number, rs.stop_name
        FROM student_assignments sa
        JOIN buses b ON sa.bus_id = b.id
        JOIN routes r ON sa.route_id = r.id
        LEFT JOIN route_stops rs ON sa.default_stop_id = rs.id
        WHERE sa.student_id = ?;
        """, (user_id,))
        assignment = cursor.fetchone()
    else:
        cursor.execute("""
        SELECT da.*, b.bus_number, b.registration_number, r.route_name, r.route_number
        FROM driver_assignments da
        JOIN buses b ON da.bus_id = b.id
        JOIN routes r ON da.route_id = r.id
        WHERE da.driver_id = ? AND da.is_active = 1;
        """, (user_id,))
        assignment = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0;", (user_id,))
    unread_notif_count = cursor.fetchone()[0]

    conn.close()

    return render_template('profile.html', user=user, assignment=assignment, unread_notif_count=unread_notif_count)


# ==========================================
# REAL-TIME SOCKET.IO EVENT HANDLERS
# ==========================================

@socketio.on('connect')
def handle_connect():
    pass


@socketio.on('join_trip')
def handle_join_trip(data):
    trip_id = data.get('trip_id')
    if trip_id:
        join_room(f"trip_{trip_id}")


@socketio.on('leave_trip')
def handle_leave_trip(data):
    trip_id = data.get('trip_id')
    if trip_id:
        leave_room(f"trip_{trip_id}")


# ==========================================
# ERROR HANDLERS
# ==========================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('errors/500.html'), 500


@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


if __name__ == '__main__':
    # Print clean local URL for user
    print("=" * 60)
    print("  BUS-TED! Smart College Bus Tracking System")
    print("  Running locally at: http://127.0.0.1:5000")
    print("=" * 60)
    socketio.run(app, host='127.0.0.1', port=5000, debug=True, allow_unsafe_werkzeug=True)
