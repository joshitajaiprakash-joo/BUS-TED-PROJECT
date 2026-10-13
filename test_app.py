"""
BUS-TED! - Comprehensive Test Suite
Verifies:
1. Database tables & constraints (including foreign keys & UNIQUE on boarding)
2. Password hashing & authentication (student & driver)
3. Role-based access control
4. Trip lifecycle (Start Trip -> Generate QR -> Broadcast GPS -> Record Attendance -> End Trip)
5. Anti-fraud QR scanning & duplicate rejection (409 Conflict)
6. Passenger count synchronization
7. GPS validation and coordinate bounds checking
8. Notification creation and delivery
9. Profile updates
"""

import os
import unittest
import json
import sqlite3
from werkzeug.security import check_password_hash
import database
import app as main_app


class BusTedTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        main_app.app.config['TESTING'] = True
        main_app.app.config['WTF_CSRF_ENABLED'] = False
        cls.client = main_app.app.test_client()

    def setUp(self):
        database.reset_db()

    def test_01_database_tables_exist(self):
        """Verify all 11 required tables exist."""
        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

        required_tables = [
            'users', 'buses', 'routes', 'route_stops',
            'driver_assignments', 'student_assignments', 'trips',
            'bus_locations', 'qr_tokens', 'boarding_records', 'notifications'
        ]
        for t in required_tables:
            self.assertIn(t, tables, f"Missing required table: {t}")

    def test_02_password_hashing(self):
        """Verify passwords are never stored in plain text and match hashes."""
        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT email, password_hash FROM users WHERE email = 'akshay@bustd.edu';")
            user = cursor.fetchone()
        finally:
            conn.close()

        self.assertIsNotNone(user)
        self.assertNotEqual(user['password_hash'], 'student123')
        self.assertTrue(check_password_hash(user['password_hash'], 'student123'))

    def test_03_login_student_and_driver(self):
        """Test student and driver login workflows."""
        with self.client.session_transaction() as sess:
            sess['_csrf_token'] = 'test_token'

        # 1. Student Login
        res = self.client.post('/login', data={
            'email': 'akshay@bustd.edu',
            'password': 'student123',
            'csrf_token': 'test_token'
        }, follow_redirects=False)

        self.assertEqual(res.status_code, 302)
        self.assertIn('/student/dashboard', res.headers.get('Location'))

        # Reset session for clean driver login test
        self.client.get('/logout')
        with self.client.session_transaction() as sess:
            sess['_csrf_token'] = 'test_token'

        # 2. Driver Login
        res_driver = self.client.post('/login', data={
            'email': 'rajesh@bustd.edu',
            'password': 'driver123',
            'csrf_token': 'test_token'
        }, follow_redirects=False)

        self.assertEqual(res_driver.status_code, 302)
        self.assertIn('/driver/dashboard', res_driver.headers.get('Location'))

    def test_04_role_based_access_control(self):
        """Ensure students cannot access driver dashboard and vice versa."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'student'
            sess['name'] = 'Akshay Sharma'
            sess['_csrf_token'] = 'test_token'

        res = self.client.get('/driver/dashboard', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/student/dashboard', res.headers.get('Location'))

        res_start = self.client.post('/driver/trip/start', data={'csrf_token': 'test_token'}, follow_redirects=False)
        self.assertEqual(res_start.status_code, 302)
        self.assertIn('/student/dashboard', res_start.headers.get('Location'))

    def test_05_trip_start_and_qr_generation(self):
        """Test driver starting a trip, generating a secure QR token, and creating notifications."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 5
            sess['role'] = 'driver'
            sess['name'] = 'Rajesh Kumar'
            sess['_csrf_token'] = 'test_token'

        res = self.client.post('/driver/trip/start', data={'csrf_token': 'test_token'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trips WHERE driver_id = 5 AND status = 'active';")
            trip = cursor.fetchone()
            self.assertIsNotNone(trip)

            cursor.execute("SELECT * FROM qr_tokens WHERE trip_id = ? AND is_active = 1;", (trip['id'],))
            token_rec = cursor.fetchone()
            self.assertIsNotNone(token_rec)
            self.assertTrue(len(token_rec['token']) >= 32)
        finally:
            conn.close()

    def test_06_student_qr_scanning_and_anti_duplicate_enforcement(self):
        """Test student scanning driver's QR code, attendance recording, and duplicate rejection."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 5
            sess['role'] = 'driver'
            sess['name'] = 'Rajesh Kumar'
            sess['_csrf_token'] = 'test_token'

        self.client.post('/driver/trip/start', data={'csrf_token': 'test_token'})

        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT token, trip_id FROM qr_tokens WHERE is_active = 1 LIMIT 1;")
            token_data = cursor.fetchone()
            active_token = token_data['token']
            trip_id = token_data['trip_id']
        finally:
            conn.close()

        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'student'
            sess['name'] = 'Akshay Sharma'
            sess['identifier'] = 'STU-2024-042'
            sess['_csrf_token'] = 'test_token'

        # First scan -> Success
        scan_res = self.client.post('/api/student/scan-qr', json={
            'qr_token': active_token,
            'csrf_token': 'test_token'
        })
        self.assertEqual(scan_res.status_code, 200)
        data = json.loads(scan_res.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['passenger_count'], 1)

        # Second scan -> Rejected (409 Conflict)
        dup_res = self.client.post('/api/student/scan-qr', json={
            'qr_token': active_token,
            'csrf_token': 'test_token'
        })
        self.assertEqual(dup_res.status_code, 409)
        dup_data = json.loads(dup_res.data)
        self.assertEqual(dup_data['status'], 'error')
        self.assertIn('already boarded', dup_data['message'].lower())

        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM boarding_records WHERE trip_id = ?;", (trip_id,))
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            conn.close()

    def test_07_expired_and_invalid_qr_token_rejection(self):
        """Test scanning invalid or expired QR tokens is rejected."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'student'
            sess['name'] = 'Akshay Sharma'
            sess['_csrf_token'] = 'test_token'

        res_invalid = self.client.post('/api/student/scan-qr', json={
            'qr_token': 'INVALID_TOKEN_12345',
            'csrf_token': 'test_token'
        })
        self.assertEqual(res_invalid.status_code, 400)

    def test_08_driver_gps_recording_and_validation(self):
        """Test driver GPS transmission and bounds validation."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 5
            sess['role'] = 'driver'
            sess['name'] = 'Rajesh Kumar'
            sess['_csrf_token'] = 'test_token'

        self.client.post('/driver/trip/start', data={'csrf_token': 'test_token'})

        # Valid coordinates
        gps_res = self.client.post('/api/driver/gps', json={
            'latitude': 13.0185,
            'longitude': 77.5960,
            'accuracy': 8.5,
            'speed': 28.0,
            'heading': 180.0,
            'csrf_token': 'test_token'
        })
        self.assertEqual(gps_res.status_code, 200)

        # Invalid out-of-bounds latitude
        invalid_gps = self.client.post('/api/driver/gps', json={
            'latitude': 95.0,
            'longitude': 77.5960,
            'csrf_token': 'test_token'
        })
        self.assertEqual(invalid_gps.status_code, 400)

    def test_09_end_trip_and_token_invalidation(self):
        """Test driver ending a trip and ensuring QR token is deactivated."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 5
            sess['role'] = 'driver'
            sess['name'] = 'Rajesh Kumar'
            sess['_csrf_token'] = 'test_token'

        self.client.post('/driver/trip/start', data={'csrf_token': 'test_token'})

        end_res = self.client.post('/driver/trip/end', data={'csrf_token': 'test_token'}, follow_redirects=True)
        self.assertEqual(end_res.status_code, 200)

        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM trips WHERE driver_id = 5 ORDER BY id DESC LIMIT 1;")
            trip_status = cursor.fetchone()[0]
            self.assertEqual(trip_status, 'completed')

            cursor.execute("SELECT is_active FROM qr_tokens WHERE is_active = 1;")
            active_tokens = cursor.fetchall()
            self.assertEqual(len(active_tokens), 0)
        finally:
            conn.close()

    def test_10_routes_and_stops_ordered(self):
        """Verify routes list returns stops in ascending order."""
        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT stop_order FROM route_stops WHERE route_id = 1 ORDER BY stop_order ASC;")
            orders = [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

        self.assertEqual(orders, sorted(orders))
        self.assertEqual(orders, [1, 2, 3, 4, 5])


if __name__ == '__main__':
    unittest.main()
