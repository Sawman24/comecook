import unittest
import os
import tempfile
import json

temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
os.environ["COOKED_DB_PATH"] = temp_db_path
os.environ["COOKED_SEED_DEMO"] = "0"
os.environ["ADMIN_USERNAMES"] = ""

from app import app
from database import init_db, get_db_connection

class FirstUserAdminAndSecurityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()
        os.environ["COOKED_DB_PATH"] = temp_db_path
        os.environ["ADMIN_USERNAMES"] = ""
        os.environ["COOKED_SEED_DEMO"] = "0"
        init_db()


    @classmethod
    def tearDownClass(cls):
        os.close(temp_db_fd)
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

    def test_01_health_endpoint(self):
        """Verify /api/health returns 200 OK and healthy status."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "cooked")
        self.assertIn("timestamp", data)

    def test_02_security_headers_applied(self):
        """Verify security headers are applied to HTTP responses."""
        res = self.client.get("/api/health")
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(res.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("camera=()", res.headers.get("Permissions-Policy"))

    def test_03_first_registered_user_becomes_owner_admin(self):
        """Verify the first user registered on an empty database is guaranteed admin=1."""
        # Ensure database starts with 0 users
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM users;")
        self.assertEqual(cursor.fetchone()["count"], 0)
        conn.close()

        # Register User 1
        res1 = self.client.post("/api/auth/register", json={
            "username": "executive_chef_owner",
            "email": "owner@cooked.community",
            "password": "StrongOwnerPassword2026!",
            "display_name": "Executive Chef Owner"
        })
        self.assertEqual(res1.status_code, 201)
        data1 = res1.get_json()
        self.assertTrue(data1["success"])
        self.assertEqual(data1["user"]["is_admin"], 1, "First registered user MUST be admin=1")

        # Verify in database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE username = 'executive_chef_owner';")
        user1_db = cursor.fetchone()
        self.assertEqual(user1_db["is_admin"], 1)
        conn.close()

    def test_04_subsequent_registered_user_is_standard_cook(self):
        """Verify second registered user is a standard user with admin=0."""
        res2 = self.client.post("/api/auth/register", json={
            "username": "line_cook_sam",
            "email": "sam@cooked.community",
            "password": "StrongSamPassword2026!",
            "display_name": "Line Cook Sam"
        })
        self.assertEqual(res2.status_code, 201)
        data2 = res2.get_json()
        self.assertTrue(data2["success"])
        self.assertEqual(data2["user"]["is_admin"], 0, "Second registered user MUST be standard user (is_admin=0)")

        # Verify in database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE username = 'line_cook_sam';")
        user2_db = cursor.fetchone()
        self.assertEqual(user2_db["is_admin"], 0)
        conn.close()

    def test_05_admin_user_deletion_and_moderation(self):
        """Verify admin can list and permanently delete user accounts."""
        # Login as owner admin
        self.client.post("/api/auth/login", json={
            "username": "executive_chef_owner",
            "password": "StrongOwnerPassword2026!"
        })

        # List users as admin
        users_res = self.client.get("/api/admin/users")
        self.assertEqual(users_res.status_code, 200)
        users = users_res.get_json()["users"]
        self.assertTrue(len(users) >= 2)

        sam_user = next((u for u in users if u["username"] == "line_cook_sam"), None)
        self.assertIsNotNone(sam_user)

        # Delete user
        del_res = self.client.delete(f"/api/admin/users/{sam_user['id']}")
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["success"])

        # Verify user is deleted
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id = ?;", (sam_user["id"],))
        self.assertIsNone(cursor.fetchone())
        conn.close()

if __name__ == "__main__":
    unittest.main()
