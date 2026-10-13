# BUS-TED! 🚌
### Smart College Bus Tracking, QR Attendance & Live Transportation Management System

**BUS-TED!** ("Your Campus. Your Bus. In Real Time.") is a complete, full-stack college transportation management system built for campus hackathons and live production transit management.

It allows students to track college buses in real time with OpenStreetMap and Leaflet, scan secure dynamic QR codes to register boarding attendance, and receive instant transit notifications. Drivers can start and end campus trips, broadcast real GPS coordinates directly from their browser, display active boarding QR passes, and monitor passenger manifests live via WebSockets.

---

## 📸 Key Features

- **Real-Time GPS Tracking**: Browser Geolocation API collects actual coordinates and streams them over Flask-SocketIO directly to Leaflet maps.
- **Anti-Fraud QR Attendance**: Cryptographically generated, expiring tokens (`secrets.token_urlsafe`). Enforces SQLite database-level `UNIQUE(student_id, trip_id)` constraints to mathematically eliminate duplicate scans.
- **Role-Based Access Control**: Strict segregation between **Student** and **Driver** portals with Werkzeug password hashing and custom CSRF protection.
- **Real-Time Passenger Manifest**: Drivers see student names, roll numbers, and exact boarding timestamps live without page reloads.
- **Campus Route Directory**: Ordered sequenced campus stops, schedule timelines, and live status badges.
- **Occupancy Overview**: Chart.js visual telemetry showing available seats, booked seats, and vehicle capacity.

---

## 🛠️ Technology Stack

| Layer | Technologies |
|---|---|
| **Frontend** | HTML5, CSS3, JavaScript (ES6+), FontAwesome |
| **Backend** | Python 3.12+, Flask 3.x, Flask-SocketIO |
| **Database** | SQLite3 with Foreign Key Enforcement & Indexed Constraints |
| **Real-Time WebSockets** | Socket.IO, Simple-WebSocket / Eventlet |
| **Mapping & GIS** | Leaflet.js, OpenStreetMap tiles |
| **QR Code Engine** | Python `qrcode[pil]`, browser `html5-qrcode` |
| **Data Visualization** | Chart.js |
| **Security** | Werkzeug password hashing, session cookies, CSRF defense |

---

## 🚀 Quick Start Guide (Windows PowerShell)

Follow these exact steps in Windows PowerShell to set up and run the system.

### 1. Clone & Navigate to Workspace
```powershell
cd e:\college\APP\BUS-TED
```

### 2. Create and Activate Python Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

*(If PowerShell script execution is restricted, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` first)*.

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Initialize Database and Seed Demo Data
The database initializes automatically on app startup, or you can run:
```powershell
python database.py
```

### 5. Launch Application
```powershell
python app.py
```
Expected output:
```text
============================================================
  BUS-TED! Smart College Bus Tracking System
  Running locally at: http://127.0.0.1:5000
============================================================
```

Open your browser and navigate to: **`http://127.0.0.1:5000`**

---

## 🔑 Safe Local Demo Accounts

The database comes pre-seeded with safe local demo accounts. Click the fast demo buttons on the login page or enter credentials manually:

| Role | Name | Email | Password | Assigned Vehicle & Route |
|---|---|---|---|---|
| **Student** | Akshay Sharma | `akshay@bustd.edu` | `student123` | BUS-12 &bull; Route 01 (North Express) |
| **Student** | Priya Patel | `priya@bustd.edu` | `student123` | BUS-12 &bull; Route 01 (North Express) |
| **Student** | Rahul Verma | `rahul@bustd.edu` | `student123` | BUS-07 &bull; Route 02 (South Shuttle) |
| **Driver** | Rajesh Kumar | `rajesh@bustd.edu` | `driver123` | BUS-12 &bull; Route 01 (North Express) |
| **Driver** | Suresh Gowda | `suresh@bustd.edu` | `driver123` | BUS-07 &bull; Route 02 (South Shuttle) |

---

## 🧪 Testing Hackathon Workflows

### Testing Driver Workflow
1. Open an Incognito window or separate browser and log in as `rajesh@bustd.edu` (`driver123`).
2. On the **Driver Console**, click **"Start Campus Trip"**.
3. Notice:
   - Trip status updates to **TRIP IN PROGRESS**.
   - An active cryptographic QR code is generated.
   - Click **"GPS Broadcaster"** &rarr; Browser will ask for Location permission. Click **Allow**.
   - Your actual latitude, longitude, speed, and accuracy will stream live!

### Testing Student Live Tracking & QR Scanning
1. In another browser window, log in as `akshay@bustd.edu` (`student123`).
2. On the **Student Dashboard**:
   - The status pill turns green with a pulsing **LIVE** indicator.
   - The Leaflet map shows the bus marker at the driver's real location with popup details.
3. Click **"Scan Boarding QR Code"**:
   - Camera mode: Point camera at driver's QR code.
   - Desktop / No-Camera fallback: Click "Test Token Manual Entry", paste the token, and click **Verify**.
4. **Anti-Fraud Verification**:
   - Boarding is verified instantly!
   - Student dashboard updates to "Boarding Confirmed".
   - The Driver console and **Passenger Feed** immediately increment passenger count and show Akshay Sharma's name and timestamp live without reloading.
   - Try scanning a second time: System returns `409 Conflict` ("Duplicate scan: You have already boarded this trip").

---

## 🔒 Security Architecture

1. **Password Security**: Passwords hashed using Werkzeug's `generate_password_hash` (`scrypt`/`pbkdf2:sha256`).
2. **Anti-Duplicate Attendance**: SQLite `UNIQUE(student_id, trip_id)` constraint on `boarding_records` prevents race conditions and replay attacks.
3. **Expiring QR Passes**: Tokens expire after 30 minutes or immediately when the driver clicks **End Trip**.
4. **GPS Validation**: Backend ensures `-90.0 <= lat <= 90.0` and `-180.0 <= lng <= 180.0` and verifies trip driver ownership.
5. **CSRF Protection**: State-changing POST endpoints validate session CSRF tokens.

---

## 🧪 Running Automated Unit Tests

A comprehensive 10-point test suite is included in `test_app.py`:
```powershell
python -m unittest test_app.py
```
Tests:
- Database schema and foreign key enforcement
- Password hashing
- Role-based route redirection
- Trip start/end state machine
- QR token generation, validation, and expiration
- Duplicate scan prevention (409 Conflict)
- Real GPS bounds validation
- Sequenced route stop ordering

---

## 🌐 Geolocation & Deployment Notes

- **Localhost Testing**: The browser Geolocation API (`navigator.geolocation`) permits GPS access over `http://localhost` and `http://127.0.0.1` without HTTPS.
- **Production / Remote Devices**: Modern browsers require HTTPS (or local SSL via mkcert) when accessing camera and GPS from external mobile phones over local Wi-Fi.

---

## 📁 Project Structure

```text
BUS-TED/
├── app.py                     # Flask application routes, Socket.IO & API endpoints
├── database.py                # SQLite schema creation, foreign keys & demo seeds
├── test_app.py                # Automated integration test suite
├── requirements.txt           # Python package dependencies
├── README.md                  # System manual and PowerShell guide
├── .gitignore                 # Git ignore rules for venv and databases
├── instance/
│   └── bus_ted.db             # Local SQLite database
├── templates/
│   ├── base.html              # Shared layout, navigation & socket listener
│   ├── login.html             # Login portal with 1-click demo accounts
│   ├── register.html          # Registration for students and drivers
│   ├── student_dashboard.html # Live tracking map, occupancy donut, stops timeline
│   ├── driver_dashboard.html  # Trip controls, active QR code, passenger counter
│   ├── my_bus.html            # Focused bus tracker & vehicle details
│   ├── scan_qr.html           # HTML5 camera scanner with fallback entry
│   ├── routes.html            # Routes directory with Leaflet visualizer
│   ├── gps_broadcast.html     # Driver telemetry and Geolocation broadcaster
│   ├── passenger_feed.html    # Live driver passenger manifest
│   ├── notifications.html     # Transit alert center
│   ├── profile.html           # Profile manager with locked role/assignment
│   ├── trip_history.html      # Past student boarding and driver trip logs
│   └── errors/
│       ├── 403.html           # Access forbidden
│       ├── 404.html           # Not found
│       └── 500.html           # Server error
└── static/
    ├── css/
    │   └── style.css          # Design system matching UI mockup
    └── js/
        ├── app.js             # UI mobile toggle & global Socket.IO setup
        ├── map.js             # Leaflet live bus markers, stops & polylines
        ├── qr_scanner.js      # html5-qrcode camera handler & verification
        ├── gps_tracking.js    # Browser Geolocation API transmission
        └── notifications.js   # Notification mark-as-read handler
```
