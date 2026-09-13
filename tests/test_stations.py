import unittest
import os
import json
import tempfile

temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
os.environ["COOKED_DB_PATH"] = temp_db_path
os.environ["ADMIN_USERNAMES"] = "testadmin,headchef"

from app import app
from database import init_db, seed_data_if_empty, get_db_connection

class KitchenStationsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()
        os.environ["COOKED_DB_PATH"] = temp_db_path
        os.environ["ADMIN_USERNAMES"] = "testadmin,headchef"
        init_db()
        seed_data_if_empty(force=True)



    @classmethod
    def tearDownClass(cls):
        os.close(temp_db_fd)
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

    def test_01_get_stations_list(self):
        """Verify GET /api/stations returns default kitchen stations."""
        res = self.client.get("/api/stations")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        stations = data["stations"]
        self.assertGreaterEqual(len(stations), 7)
        slugs = [s["slug"] for s in stations]
        self.assertIn("baking-pastry", slugs)
        self.assertIn("pasta-craft", slugs)
        self.assertIn("smoke-castiron", slugs)

    def test_02_get_station_detail(self):
        """Verify GET /api/stations/<slug> returns details, rules, and brigade members."""
        res = self.client.get("/api/stations/pasta-craft")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        station = data["station"]
        self.assertEqual(station["slug"], "pasta-craft")
        self.assertEqual(station["icon"], "🍝")
        self.assertIn("pasta water", station["rules_text"])
        self.assertIn("members_sample", station)

    def test_03_clock_in_and_clock_out(self):
        """Verify Clock In / Clock Out toggle increments/decrements member counts."""
        # Register a test user
        self.client.post("/api/auth/register", json={
            "username": "sous_chef_sam",
            "email": "sam@cooked.community",
            "password": "ChefPassword123!",
            "display_name": "Sous Chef Sam"
        })
        # Login
        login_res = self.client.post("/api/auth/login", json={
            "username": "sous_chef_sam",
            "password": "ChefPassword123!"
        })
        self.assertEqual(login_res.status_code, 200)

        # Clock In to plant-harvest
        res_join = self.client.post("/api/stations/plant-harvest/join")
        self.assertEqual(res_join.status_code, 200)
        join_data = res_join.get_json()
        self.assertTrue(join_data["is_member"])
        self.assertGreaterEqual(join_data["member_count"], 1)

        # Verify detail view reflects membership
        detail_res = self.client.get("/api/stations/plant-harvest")
        self.assertTrue(detail_res.get_json()["station"]["is_member"])

        # Clock Out
        res_leave = self.client.post("/api/stations/plant-harvest/join")
        self.assertEqual(res_leave.status_code, 200)
        leave_data = res_leave.get_json()
        self.assertFalse(leave_data["is_member"])

    def test_04_create_custom_station(self):
        """Verify user can open a new Kitchen Station."""
        # Login
        self.client.post("/api/auth/login", json={
            "username": "sous_chef_sam",
            "password": "ChefPassword123!"
        })

        res = self.client.post("/api/stations", json={
            "name": "Fermentation & Koji Lab",
            "description": "Miso, koji inoculations, garums, lacto-ferments, and microbial flavor alchemy.",
            "icon": "🧪",
            "rules_text": "1. Label all ferment jars with date & salinity %\n2. Respect temperature control"
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["station"]["slug"], "fermentation-koji-lab")
        self.assertEqual(data["station"]["user_role"], "lead_cook")

    def test_05_station_filtered_posts(self):
        """Verify posts can be tagged to a station and filtered by station slug."""
        # Login
        self.client.post("/api/auth/login", json={
            "username": "sous_chef_sam",
            "password": "ChefPassword123!"
        })

        # Post to pasta-craft station
        post_res = self.client.post("/api/posts", json={
            "content": "Fresh tagliatelle using 100% Semola rimacinata and whole duck eggs. Texture is incredible!",
            "post_type": "showcase",
            "station_slug": "pasta-craft"
        })
        self.assertEqual(post_res.status_code, 201)
        post_id = post_res.get_json()["post_id"]

        # Fetch posts filtered by pasta-craft
        feed_res = self.client.get("/api/posts?station=pasta-craft")
        self.assertEqual(feed_res.status_code, 200)
        posts = feed_res.get_json()["posts"]
        post_ids = [p["id"] for p in posts]
        self.assertIn(post_id, post_ids)

        # Tagged post should include station metadata
        matching_post = next(p for p in posts if p["id"] == post_id)
        self.assertEqual(matching_post["station_slug"], "pasta-craft")
        self.assertEqual(matching_post["station_icon"], "🍝")

if __name__ == "__main__":
    unittest.main()
