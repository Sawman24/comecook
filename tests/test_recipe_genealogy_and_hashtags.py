import os
import tempfile
import unittest
import json
from app import app
from database import get_db_connection, init_db, seed_data_if_empty

class TestRecipeGenealogyAndHashtags(unittest.TestCase):
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

    def test_01_recipe_fork_lineage_and_variations(self):
        # 1. Original author creates base recipe
        chef_a = self.register_and_login("chefa", "chefa@example.com")
        chef_b = self.register_and_login("chefb", "chefb@example.com")

        res_a = chef_a.post("/api/recipes", json={
            "title": "Classic Sourdough Bread",
            "description": "Authentic sourdough with wild yeast starter #sourdough #artisan",
            "prep_time_min": 30,
            "cook_time_min": 45,
            "servings": 8,
            "difficulty": "Hard",
            "cuisine": "Baking",
            "ingredients": [
                {"name": "Bread Flour", "amount": "500", "unit": "g"},
                {"name": "Water", "amount": "350", "unit": "g"},
                {"name": "Active Sourdough Starter", "amount": "100", "unit": "g"},
                {"name": "Salt", "amount": "10", "unit": "g"}
            ],
            "steps": [
                {"step_number": 1, "instruction": "Mix starter, water, and flour. Autolyse 45 min."},
                {"step_number": 2, "instruction": "Add salt, perform stretch and folds every 30 min."}
            ],
            "tags": ["sourdough", "artisan", "bread"],
            "is_public": 1
        })
        self.assertEqual(res_a.status_code, 201)
        orig_id = res_a.get_json()["recipe_id"]

        # 2. Chef B forks Chef A's recipe with a custom twist
        twist_notes = "Used 30% rye flour and added roasted walnuts and dried cranberries."
        res_fork = chef_b.post(f"/api/recipes/{orig_id}/fork", json={
            "title": "Cranberry Walnut Sourdough Twist",
            "fork_notes": twist_notes
        })
        self.assertEqual(res_fork.status_code, 201)
        fork_data = res_fork.get_json()
        fork_id = fork_data["recipe_id"]
        self.assertIn("forked_from", fork_data)
        self.assertEqual(fork_data["forked_from"]["id"], orig_id)

        # 3. Verify Child Recipe Detail has lineage and twist notes
        child_res = chef_b.get(f"/api/recipes/{fork_id}")
        self.assertEqual(child_res.status_code, 200)
        child_recipe = child_res.get_json()["recipe"]
        self.assertEqual(child_recipe["title"], "Cranberry Walnut Sourdough Twist")
        self.assertEqual(child_recipe["parent_recipe_id"], orig_id)
        self.assertEqual(child_recipe["fork_notes"], twist_notes)
        self.assertIsNotNone(child_recipe["parent_recipe"])
        self.assertEqual(child_recipe["parent_recipe"]["id"], orig_id)
        self.assertEqual(child_recipe["parent_recipe"]["title"], "Classic Sourdough Bread")
        self.assertEqual(child_recipe["parent_recipe"]["author_username"], "chefa")

        # 4. Verify Parent Recipe has incremented fork count
        parent_res = chef_a.get(f"/api/recipes/{orig_id}")
        self.assertEqual(parent_res.status_code, 200)
        parent_recipe = parent_res.get_json()["recipe"]
        self.assertEqual(parent_recipe["fork_count"], 1)

        # 5. Verify /api/recipes/<parent_id>/forks endpoint
        forks_res = chef_a.get(f"/api/recipes/{orig_id}/forks")
        self.assertEqual(forks_res.status_code, 200)
        forks_data = forks_res.get_json()
        self.assertEqual(forks_data["total_forks"], 1)
        self.assertEqual(len(forks_data["forks"]), 1)
        first_fork = forks_data["forks"][0]
        self.assertEqual(first_fork["id"], fork_id)
        self.assertEqual(first_fork["author_username"], "chefb")
        self.assertEqual(first_fork["fork_notes"], twist_notes)

        # 6. Verify notification sent to Chef A for the fork
        notif_res = chef_a.get("/api/notifications")
        self.assertEqual(notif_res.status_code, 200)
        notifs = notif_res.get_json()["notifications"]
        fork_notif = next((n for n in notifs if "chefb" in n["message"] and ("twist" in n["message"].lower() or "fork" in n["message"].lower())), None)
        self.assertIsNotNone(fork_notif)

    def test_02_hashtags_and_trending_topics(self):
        chef_c = self.register_and_login("chefc", "chefc@example.com")

        # 1. Create a post with hashtags in the content
        post_res = chef_c.post("/api/posts", json={
            "content": "Check out my new weekend bake! #baking #sourdough #croissant",
            "post_type": "post"
        })
        self.assertEqual(post_res.status_code, 201)
        post_id = post_res.get_json()["post_id"]

        # 2. Create another post with overlapping and new tags
        post_res_2 = chef_c.post("/api/posts", json={
            "content": "Morning coffee & French #croissant perfection. #baking",
            "post_type": "post"
        })
        self.assertEqual(post_res_2.status_code, 201)

        # 3. Query trending hashtags
        trending_res = chef_c.get("/api/hashtags/trending")
        self.assertEqual(trending_res.status_code, 200)
        trends = trending_res.get_json()["trending"]
        self.assertTrue(len(trends) >= 3)
        trend_tags = [t["tag"] for t in trends]
        self.assertIn("baking", trend_tags)
        self.assertIn("croissant", trend_tags)

        # 4. Query specific hashtag endpoint: GET /api/hashtags/croissant
        tag_res = chef_c.get("/api/hashtags/croissant")
        self.assertEqual(tag_res.status_code, 200)
        tag_data = tag_res.get_json()
        self.assertEqual(tag_data["tag"], "croissant")
        self.assertGreaterEqual(len(tag_data["posts"]), 2)

        # 5. Query hashtag with recipes: GET /api/hashtags/sourdough
        sourdough_res = chef_c.get("/api/hashtags/sourdough")
        self.assertEqual(sourdough_res.status_code, 200)
        sourdough_data = sourdough_res.get_json()
        self.assertGreaterEqual(len(sourdough_data["recipes"]), 1)
        self.assertGreaterEqual(len(sourdough_data["posts"]), 1)

if __name__ == "__main__":
    unittest.main()
