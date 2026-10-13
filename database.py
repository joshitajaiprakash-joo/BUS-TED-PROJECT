import os
import sqlite3
from werkzeug.security import generate_password_hash

# Path to SQLite database file
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
DB_PATH = os.path.join(DB_DIR, 'bus_ted.db')


def ensure_db_dir():
    """Ensure instance directory exists."""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR, exist_ok=True)


def get_db():
    """Get SQLite database connection with row factory and foreign keys enabled."""
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """Initialize all 11 required database tables and indexes."""
    ensure_db_dir()
    conn = get_db()
    cursor = conn.cursor()

    # 1. users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('student', 'driver', 'admin')),
        identifier TEXT UNIQUE NOT NULL,
        phone TEXT,
        approved INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. buses
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS buses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bus_number TEXT UNIQUE NOT NULL,
        registration_number TEXT UNIQUE NOT NULL,
        capacity INTEGER NOT NULL DEFAULT 50,
        model TEXT,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'maintenance', 'inactive'))
    );
    """)

    # 3. routes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS routes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        route_number TEXT UNIQUE NOT NULL,
        route_name TEXT NOT NULL,
        start_point TEXT NOT NULL,
        destination TEXT NOT NULL,
        estimated_duration_min INTEGER DEFAULT 45
    );
    """)

    # 4. route_stops
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS route_stops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        route_id INTEGER NOT NULL,
        stop_name TEXT NOT NULL,
        stop_order INTEGER NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE,
        UNIQUE(route_id, stop_order)
    );
    """)

    # 5. driver_assignments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS driver_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        driver_id INTEGER NOT NULL,
        bus_id INTEGER NOT NULL,
        route_id INTEGER NOT NULL,
        assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (driver_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE,
        FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
    );
    """)

    # 6. student_assignments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL UNIQUE,
        bus_id INTEGER NOT NULL,
        route_id INTEGER NOT NULL,
        default_stop_id INTEGER,
        FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE,
        FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE,
        FOREIGN KEY (default_stop_id) REFERENCES route_stops(id) ON DELETE SET NULL
    );
    """)

    # 7. trips
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bus_id INTEGER NOT NULL,
        route_id INTEGER NOT NULL,
        driver_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('scheduled', 'active', 'completed', 'cancelled')),
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP,
        passenger_count INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE,
        FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE,
        FOREIGN KEY (driver_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 8. bus_locations
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bus_locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id INTEGER NOT NULL,
        bus_id INTEGER NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        accuracy REAL,
        speed REAL,
        heading REAL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
        FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE
    );
    """)

    # 9. qr_tokens
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS qr_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id INTEGER NOT NULL,
        bus_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
        FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE
    );
    """)

    # 10. boarding_records (UNIQUE constraint on student_id + trip_id prevents duplicate attendance)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS boarding_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        trip_id INTEGER NOT NULL,
        bus_id INTEGER NOT NULL,
        stop_id INTEGER,
        scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(student_id, trip_id),
        FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
        FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE,
        FOREIGN KEY (stop_id) REFERENCES route_stops(id) ON DELETE SET NULL
    );
    """)

    # 11. notifications
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        type TEXT NOT NULL DEFAULT 'info',
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # Indexes for optimal query performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_bus_active ON trips(bus_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_driver_active ON trips(driver_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bus_locations_trip_time ON bus_locations(trip_id, recorded_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_qr_tokens_active ON qr_tokens(token, is_active);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_boarding_trip_student ON boarding_records(trip_id, student_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_route_stops_route_order ON route_stops(route_id, stop_order);")

    conn.commit()
    conn.close()


def seed_demo_data(force=False):
    """Seed demo accounts, buses, routes, stops, and assignments."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users;")
    user_count = cursor.fetchone()[0]

    if user_count > 0 and not force:
        conn.close()
        return

    # Clear existing data if forced
    try:
        if force:
            tables = [
                "notifications", "boarding_records", "qr_tokens", "bus_locations",
                "trips", "student_assignments", "driver_assignments", "route_stops",
                "routes", "buses", "users"
            ]
            for t in tables:
                cursor.execute(f"DELETE FROM {t};")
            cursor.execute("DELETE FROM sqlite_sequence;")

        # 1. Seed Users (passwords hashed with werkzeug, explicit IDs)
        student_pw = generate_password_hash("student123")
        driver_pw = generate_password_hash("driver123")

        users_data = [
            # Students (IDs 1-4)
            (1, "Akshay Sharma", "akshay@bustd.edu", student_pw, "student", "STU-2024-042", "+91 98765 43210", 1),
            (2, "Priya Patel", "priya@bustd.edu", student_pw, "student", "STU-2024-089", "+91 98765 12345", 1),
            (3, "Rahul Verma", "rahul@bustd.edu", student_pw, "student", "STU-2024-115", "+91 98765 67890", 1),
            (4, "Ananya Rao", "ananya@bustd.edu", student_pw, "student", "STU-2024-204", "+91 98765 77889", 1),
            # Drivers (IDs 5-6)
            (5, "Rajesh Kumar", "rajesh@bustd.edu", driver_pw, "driver", "DRV-8801", "+91 91234 56789", 1),
            (6, "Suresh Gowda", "suresh@bustd.edu", driver_pw, "driver", "DRV-8802", "+91 91234 98765", 1),
        ]

        cursor.executemany("""
        INSERT INTO users (id, name, email, password_hash, role, identifier, phone, approved)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, users_data)

        # 2. Seed Buses (IDs 1-3)
        buses_data = [
            (1, "BUS-12", "KA-01-EQ-4421", 50, "Tata Starbus Ultra 50-Seater", "active"),
            (2, "BUS-07", "KA-01-EQ-3912", 45, "Ashok Leyland Sunshine 45-Seater", "active"),
            (3, "BUS-03", "KA-01-EQ-1845", 40, "Eicher Skyline Pro 40-Seater", "active"),
        ]

        cursor.executemany("""
        INSERT INTO buses (id, bus_number, registration_number, capacity, model, status)
        VALUES (?, ?, ?, ?, ?, ?);
        """, buses_data)

        # 3. Seed Routes (IDs 1-3)
        routes_data = [
            (1, "R-01", "North Campus Express", "Hebbal Junction", "Central College Campus", 40),
            (2, "R-02", "South Campus Shuttle", "Silk Board Junction", "Central College Campus", 45),
            (3, "R-03", "East Metro Feeder", "Indiranagar Metro", "Central College Campus", 35),
        ]

        cursor.executemany("""
        INSERT INTO routes (id, route_number, route_name, start_point, destination, estimated_duration_min)
        VALUES (?, ?, ?, ?, ?, ?);
        """, routes_data)

        # 4. Seed Route Stops (IDs 1-15)
        # Route 1: North Campus
        r1_stops = [
            (1, 1, "Hebbal Junction (Start)", 1, 13.0358, 77.5970),
            (2, 1, "RT Nagar Police Station", 2, 13.0185, 77.5960),
            (3, 1, "Mekhri Circle", 3, 13.0076, 77.5835),
            (4, 1, "Malleshwaram 8th Cross", 4, 13.0025, 77.5710),
            (5, 1, "Central College Campus (Main Gate)", 5, 12.9734, 77.5855),
        ]

        # Route 2: South Campus
        r2_stops = [
            (6, 2, "Silk Board Junction (Start)", 1, 12.9176, 77.6238),
            (7, 2, "Koramangala 5th Block", 2, 12.9352, 77.6245),
            (8, 2, "Sony World Signal", 3, 12.9398, 77.6290),
            (9, 2, "Domlur Flyover", 4, 12.9609, 77.6387),
            (10, 2, "Central College Campus (Main Gate)", 5, 12.9734, 77.5855),
        ]

        # Route 3: East Metro Feeder
        r3_stops = [
            (11, 3, "Indiranagar Metro (Start)", 1, 12.9784, 77.6408),
            (12, 3, "Ulsoor Lake North Gate", 2, 12.9822, 77.6200),
            (13, 3, "MG Road Metro Station", 3, 12.9756, 77.6066),
            (14, 3, "Vidhana Soudha North Gate", 4, 12.9797, 77.5907),
            (15, 3, "Central College Campus (Main Gate)", 5, 12.9734, 77.5855),
        ]

        all_stops = r1_stops + r2_stops + r3_stops
        cursor.executemany("""
        INSERT INTO route_stops (id, route_id, stop_name, stop_order, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?);
        """, all_stops)

        # 5. Driver Assignments
        # Driver 1 (Rajesh, ID: 5) -> BUS-12 (ID: 1), Route 1 (ID: 1)
        # Driver 2 (Suresh, ID: 6) -> BUS-07 (ID: 2), Route 2 (ID: 2)
        driver_assignments = [
            (5, 1, 1, 1),
            (6, 2, 2, 1),
        ]
        cursor.executemany("""
        INSERT INTO driver_assignments (driver_id, bus_id, route_id, is_active)
        VALUES (?, ?, ?, ?);
        """, driver_assignments)

        # 6. Student Assignments
        # Student 1 (Akshay, ID: 1) -> BUS-12, Route 1, Stop 1 (Hebbal)
        # Student 2 (Priya, ID: 2) -> BUS-12, Route 1, Stop 2 (RT Nagar)
        # Student 3 (Rahul, ID: 3) -> BUS-07, Route 2, Stop 6 (Silk Board)
        # Student 4 (Ananya, ID: 4) -> BUS-03, Route 3, Stop 11 (Indiranagar)
        student_assignments = [
            (1, 1, 1, 1),
            (2, 1, 1, 2),
            (3, 2, 2, 6),
            (4, 3, 3, 11),
        ]
        cursor.executemany("""
        INSERT INTO student_assignments (student_id, bus_id, route_id, default_stop_id)
        VALUES (?, ?, ?, ?);
        """, student_assignments)

        # 7. Initial Notifications
        notifications_data = [
            (1, "Welcome to BUS-TED!", "Your campus bus tracking and digital QR boarding pass is ready. Assigned to BUS-12.", "info"),
            (1, "Route 01 Scheduled", "Morning trip for Route 01 starts at 07:30 AM from Hebbal Junction.", "info"),
            (2, "Welcome to BUS-TED!", "Assigned to BUS-12 on Route 01. Scan driver's QR code on boarding.", "info"),
            (5, "Driver Assigned", "You are assigned to BUS-12 (KA-01-EQ-4421) on Route 01 - North Campus Express.", "info"),
        ]
        cursor.executemany("""
        INSERT INTO notifications (user_id, title, message, type)
        VALUES (?, ?, ?, ?);
        """, notifications_data)

        conn.commit()
    finally:
        conn.close()
    print("Database initialized and demo data seeded successfully.")


def reset_db():
    """Reset database and re-seed demo data."""
    init_db()
    seed_demo_data(force=True)


if __name__ == '__main__':
    init_db()
    seed_demo_data(force=True)
