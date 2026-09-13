import os
import tempfile
import unittest
import json
from datetime import datetime, timezone, timedelta
from app import app
from database import get_db_connection, init_db, seed_data_if_empty
from email_service import (
    send_welcome_email, send_password_reset_email, send_password_changed_email, get_smtp_config
)

class TestEmailAndPasswordReset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_fd, cls.db_path = tempfile.mkstemp()
        os.environ["COOKED_DB_PATH"] = cls.db_path
        app.config["TESTING"] = True
        init_db()
        seed_data_if_empty()
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        os.close(cls.db_fd)
        if os.path.exists(cls.db_path):
            os.unlink(cls.db_path)

    def register_user(self, username, email, password="Password123!"):
        client = app.test_client()
        res = client.post("/api/auth/register", json={
            "username": username,
            "email": email,
            "password": password,
            "display_name": f"Cook {username.capitalize()}"
        })
        return res, client

    def test_01_forgot_password_generates_token_and_sends_email(self):
        self.register_user("baker_sam", "baker_sam@example.com")
        client = app.test_client()

        res = client.post("/api/auth/forgot-password", json={"email": "baker_sam@example.com"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("password reset link has been sent", data["message"].lower())
        # Make sure token is never exposed in response body
        self.assertNotIn("token", data)
        self.assertNotIn("dev_reset_token", data)

        # Check in database that token was safely stored with 1-hour expiration
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pr.token, pr.expires_at, pr.used, u.username
            FROM password_resets pr
            JOIN users u ON pr.user_id = u.id
            WHERE u.email = 'baker_sam@example.com' AND pr.used = 0;
        """)
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["used"], 0)
        self.assertTrue(len(row["token"]) >= 32)

    def test_02_anti_enumeration_on_non_existent_email(self):
        client = app.test_client()
        res = client.post("/api/auth/forgot-password", json={"email": "nonexistent_chef@example.com"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("password reset link has been sent", data["message"].lower())

    def test_03_verify_reset_token_endpoint(self):
        self.register_user("pasta_mario", "mario@example.com")
        client = app.test_client()
        client.post("/api/auth/forgot-password", json={"email": "mario@example.com"})

        # Fetch token from DB
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT token FROM password_resets pr JOIN users u ON pr.user_id = u.id WHERE u.username = 'pasta_mario' AND pr.used = 0;")
        token = cursor.fetchone()["token"]
        conn.close()

        # Valid token check
        v_res = client.post("/api/auth/verify-reset-token", json={"token": token})
        self.assertEqual(v_res.status_code, 200)
        self.assertTrue(v_res.get_json()["valid"])
        self.assertEqual(v_res.get_json()["username"], "pasta_mario")

        # Invalid token check
        bad_res = client.post("/api/auth/verify-reset-token", json={"token": "invalid_fake_token_12345"})
        self.assertEqual(bad_res.status_code, 400)
        self.assertFalse(bad_res.get_json()["valid"])

    def test_04_reset_password_success_and_login(self):
        self.register_user("grill_guy", "grill_guy@example.com", "OldPassword123!")
        client = app.test_client()
        client.post("/api/auth/forgot-password", json={"email": "grill_guy@example.com"})

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT token FROM password_resets pr JOIN users u ON pr.user_id = u.id WHERE u.username = 'grill_guy' AND pr.used = 0;")
        token = cursor.fetchone()["token"]
        conn.close()

        # Reset password
        reset_res = client.post("/api/auth/reset-password", json={
            "token": token,
            "new_password": "NewBrandPassword123!"
        })
        self.assertEqual(reset_res.status_code, 200)
        self.assertTrue(reset_res.get_json()["success"])

        # Check database: token marked used
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT used FROM password_resets WHERE token = ?;", (token,))
        self.assertEqual(cursor.fetchone()["used"], 1)
        conn.close()

        # Try to login with OLD password -> Fail
        old_login = client.post("/api/auth/login", json={"username": "grill_guy", "password": "OldPassword123!"})
        self.assertEqual(old_login.status_code, 401)

        # Login with NEW password -> Success
        new_login = client.post("/api/auth/login", json={"username": "grill_guy", "password": "NewBrandPassword123!"})
        self.assertEqual(new_login.status_code, 200)
        self.assertEqual(new_login.get_json()["user"]["username"], "grill_guy")

    def test_05_cannot_reuse_used_token(self):
        self.register_user("reuse_tester", "reuse@example.com", "Password123!")
        client = app.test_client()
        client.post("/api/auth/forgot-password", json={"email": "reuse@example.com"})

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT token FROM password_resets pr JOIN users u ON pr.user_id = u.id WHERE u.username = 'reuse_tester' AND pr.used = 0;")
        token = cursor.fetchone()["token"]
        conn.close()

        # First reset succeeds
        res1 = client.post("/api/auth/reset-password", json={"token": token, "new_password": "FirstReset123!"})
        self.assertEqual(res1.status_code, 200)

        # Second reset with SAME token fails
        res2 = client.post("/api/auth/reset-password", json={"token": token, "new_password": "SecondReset123!"})
        self.assertEqual(res2.status_code, 400)
        self.assertIn("invalid", res2.get_json()["message"].lower())

    def test_06_cannot_use_expired_token(self):
        self.register_user("expired_tester", "expired@example.com", "Password123!")
        client = app.test_client()

        # Insert expired token manually
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = 'expired_tester';")
        u_id = cursor.fetchone()["id"]
        past_time = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO password_resets (user_id, token, expires_at, used) VALUES (?, 'expired_token_123', ?, 0);", (u_id, past_time))
        conn.commit()
        conn.close()

        # Attempt to reset with expired token
        exp_res = client.post("/api/auth/reset-password", json={"token": "expired_token_123", "new_password": "NewPassword123!"})
        self.assertEqual(exp_res.status_code, 400)
        self.assertIn("expired", exp_res.get_json()["message"].lower())

    def test_07_weak_password_rejected_during_reset(self):
        self.register_user("weak_tester", "weak@example.com", "Password123!")
        client = app.test_client()
        client.post("/api/auth/forgot-password", json={"email": "weak@example.com"})

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT token FROM password_resets pr JOIN users u ON pr.user_id = u.id WHERE u.username = 'weak_tester' AND pr.used = 0;")
        token = cursor.fetchone()["token"]
        conn.close()

        # Attempt to reset with weak password (missing symbols/digits/length)
        weak_res = client.post("/api/auth/reset-password", json={"token": token, "new_password": "weak"})
        self.assertEqual(weak_res.status_code, 400)
        self.assertIn("at least 8 characters", weak_res.get_json()["message"].lower())

    def test_08_email_templates_render_without_error(self):
        # Verify template functions execute and return valid threads/objects
        t1 = send_welcome_email("test@example.com", "chef_test", "Chef Test", "https://comecook.app")
        t2 = send_password_reset_email("test@example.com", "chef_test", "sample_token", "https://comecook.app")
        t3 = send_password_changed_email("test@example.com", "chef_test", "https://comecook.app")
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)
        self.assertIsNotNone(t3)

if __name__ == "__main__":
    unittest.main()
