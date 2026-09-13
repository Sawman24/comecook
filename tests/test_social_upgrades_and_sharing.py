import os
import tempfile
import unittest
import json
from app import app
from database import get_db_connection, init_db, seed_data_if_empty

class TestSocialUpgradesAndSharing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_fd, cls.db_path = tempfile.mkstemp()
        os.environ["DATABASE_PATH"] = cls.db_path
        app.config["TESTING"] = True
        init_db()
        seed_data_if_empty()
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        os.close(cls.db_fd)
        if os.path.exists(cls.db_path):
            os.unlink(cls.db_path)

    def register_and_login(self, username, email, password="Password123!"):
        client = app.test_client()
        client.post("/api/auth/register", json={
            "username": username,
            "email": email,
            "password": password,
            "display_name": f"Chef {username.capitalize()}"
        })
        client.post("/api/auth/login", json={
            "username": username,
            "password": password
        })
        return client

    def test_01_recipe_reviews_crud_and_ratings(self):
        # Create author and reviewer
        author_client = self.register_and_login("author1", "author1@example.com")
        reviewer_client = self.register_and_login("reviewer1", "reviewer1@example.com")

        # Author creates recipe
        res = author_client.post("/api/recipes", json={
            "title": "Gourmet Risotto",
            "description": "Creamy mushroom risotto",
            "prep_time_min": 15,
            "cook_time_min": 30,
            "servings": 4,
            "difficulty": "Medium",
            "cuisine": "Italian",
            "ingredients": [{"name": "Arborio Rice", "amount": "2", "unit": "cups"}],
            "steps": [{"step_number": 1, "instruction": "Stir constantly with warm stock."}],
            "is_public": 1
        })
        self.assertEqual(res.status_code, 201)
        recipe_id = res.get_json()["recipe_id"]

        # Reviewer submits 5-star review with cook snap and shares to feed
        rev_res = reviewer_client.post(f"/api/recipes/{recipe_id}/reviews", json={
            "rating": 5,
            "review": "Turned out incredibly creamy! Added a splash of white wine.",
            "image_url": "https://images.unsplash.com/photo-1556910103-1c02745aae4d?w=600",
            "share_to_feed": True
        })
        self.assertEqual(rev_res.status_code, 200)

        # Get recipe reviews
        get_rev = self.client.get(f"/api/recipes/{recipe_id}/reviews")
        self.assertEqual(get_rev.status_code, 200)
        data = get_rev.get_json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["avg_rating"], 5.0)
        self.assertEqual(len(data["reviews"]), 1)
        self.assertEqual(data["reviews"][0]["username"], "reviewer1")

        # Verify recipe detail contains avg_rating
        rec_detail = self.client.get(f"/api/recipes/{recipe_id}")
        self.assertEqual(rec_detail.status_code, 200)
        self.assertEqual(rec_detail.get_json()["recipe"]["avg_rating"], 5.0)
        self.assertEqual(rec_detail.get_json()["recipe"]["reviews_count"], 1)

        # Check author received in-app notification
        notif_res = author_client.get("/api/notifications")
        self.assertEqual(notif_res.status_code, 200)
        notif_data = notif_res.get_json()
        self.assertGreaterEqual(notif_data["unread_count"], 1)
        found_review_notif = any(n["type"] == "review" for n in notif_data["notifications"])
        self.assertTrue(found_review_notif)

    def test_02_in_app_notifications_lifecycle(self):
        chef_a = self.register_and_login("chef_alpha", "alpha@example.com")
        chef_b = self.register_and_login("chef_beta", "beta@example.com")

        # Get chef_a ID
        me_res = chef_a.get("/api/auth/me")
        chef_a_id = me_res.get_json()["user"]["id"]

        # Chef B follows Chef A
        follow_res = chef_b.post(f"/api/users/{chef_a_id}/follow")
        self.assertEqual(follow_res.status_code, 200)

        # Chef A checks notifications
        notif_res = chef_a.get("/api/notifications")
        self.assertEqual(notif_res.status_code, 200)
        notifs = notif_res.get_json()["notifications"]
        follow_notifs = [n for n in notifs if n["type"] == "follow"]
        self.assertTrue(len(follow_notifs) > 0)
        notif_id = follow_notifs[0]["id"]

        # Chef A marks notification as read
        read_res = chef_a.post("/api/notifications/read", json={"notification_ids": [notif_id]})
        self.assertEqual(read_res.status_code, 200)

        # Chef A deletes notification
        del_res = chef_a.delete(f"/api/notifications/{notif_id}")
        self.assertEqual(del_res.status_code, 200)

    def test_03_station_leaderboard(self):
        chef = self.register_and_login("leader_chef", "leader@example.com")

        # Post to pasta-craft station
        post_res = chef.post("/api/posts", json={
            "content": "Handmade Tagliatelle with Sage Butter",
            "post_type": "showcase",
            "station_slug": "pasta-craft"
        })
        self.assertEqual(post_res.status_code, 201)
        post_id = post_res.get_json()["post_id"]

        # Another chef likes the post
        fan = self.register_and_login("fan_chef", "fan@example.com")
        fan.post(f"/api/posts/{post_id}/like")

        # Get station leaderboard
        lb_res = self.client.get("/api/stations/pasta-craft/leaderboard")
        self.assertEqual(lb_res.status_code, 200)
        lb_data = lb_res.get_json()
        self.assertTrue(lb_data["success"])
        self.assertIn("lead_cooks", lb_data)
        self.assertTrue(len(lb_data["lead_cooks"]) > 0)
        self.assertEqual(lb_data["lead_cooks"][0]["username"], "leader_chef")
        self.assertGreaterEqual(lb_data["lead_cooks"][0]["likes_received"], 1)

    def test_04_rich_social_sharing_meta_tags(self):
        # 1. Recipe Share Route
        chef = self.register_and_login("share_chef", "share@example.com")
        rec_res = chef.post("/api/recipes", json={
            "title": "Classic Bolognese",
            "description": "Slow simmered ragu",
            "prep_time_min": 20,
            "cook_time_min": 180,
            "servings": 6,
            "difficulty": "Medium",
            "cuisine": "Italian",
            "ingredients": [{"name": "Beef", "amount": "1", "unit": "lb"}],
            "steps": [{"step_number": 1, "instruction": "Simmer gently for 3 hours."}],
            "is_public": 1
        })
        recipe_id = rec_res.get_json()["recipe_id"]

        recipe_page = self.client.get(f"/recipes/{recipe_id}")
        self.assertEqual(recipe_page.status_code, 200)
        html = recipe_page.get_data(as_text=True)
        self.assertIn("Classic Bolognese", html)
        self.assertIn("og:title", html)
        self.assertIn("twitter:card", html)

        # 2. Chef Profile Share Route
        chef_page = self.client.get("/chefs/share_chef")
        self.assertEqual(chef_page.status_code, 200)
        chef_html = chef_page.get_data(as_text=True)
        self.assertIn("og:title", chef_html)
        self.assertIn("share_chef", chef_html)

        # 3. Station Share Route
        station_page = self.client.get("/stations/pasta-craft")
        self.assertEqual(station_page.status_code, 200)
        station_html = station_page.get_data(as_text=True)
        self.assertIn("Handmade Pasta", station_html)
        self.assertIn("og:title", station_html)

if __name__ == "__main__":
    unittest.main()
