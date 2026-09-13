import unittest
import os
import json
import tempfile
from datetime import datetime, timezone

# Ensure test DB is used
temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
os.environ["COOKED_DB_PATH"] = temp_db_path
os.environ["ADMIN_USERNAMES"] = "testadmin,headchef"

from app import app
from database import init_db, seed_data_if_empty, get_db_connection

class CookedTestCase(unittest.TestCase):
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

    def test_01_registration_and_admin_role_immunity(self):
        """Verify registration ignores client is_admin parameter (Registration Injection Immunity)."""
        res = self.client.post("/api/auth/register", json={
            "username": "hacker_chef",
            "email": "hacker@cooked.community",
            "password": "SecretPassword123!",
            "display_name": "Wannabe Admin",
            "is_admin": 1  # Should be ignored
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["user"]["is_admin"], 0, "Client-provided is_admin must be ignored")

    def test_02_login_and_cookie_auth(self):
        """Verify login returns user info and sets session cookie."""
        res = self.client.post("/api/auth/login", json={
            "username": "hacker_chef",
            "password": "SecretPassword123!"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("cooked_session", res.headers.get("Set-Cookie", ""))

        # Check /api/auth/me
        me_res = self.client.get("/api/auth/me")
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.get_json()
        self.assertIsNotNone(me_data["user"])
        self.assertEqual(me_data["user"]["username"], "hacker_chef")

    def test_03_admin_route_protection(self):
        """Verify non-admin users receive 403 on admin endpoints."""
        # hacker_chef is logged in and not admin
        res = self.client.get("/api/admin/reports")
        self.assertEqual(res.status_code, 403, "Non-admin user should get 403 Forbidden")

        # Now login as headchef (admin)
        admin_login = self.client.post("/api/auth/login", json={
            "username": "headchef",
            "password": "ChefPass123!"
        })
        self.assertEqual(admin_login.status_code, 200)
        res_admin = self.client.get("/api/admin/reports")
        self.assertEqual(res_admin.status_code, 200)

        stats_admin = self.client.get("/api/admin/stats")
        self.assertEqual(stats_admin.status_code, 200)
        self.assertTrue(stats_admin.get_json()["success"])
        self.assertIn("total_users", stats_admin.get_json()["stats"])

    def test_04_idor_protection_recipes(self):
        """Verify users cannot update or delete other users' recipes."""
        # Login as julia_bakes
        self.client.post("/api/auth/login", json={
            "username": "julia_bakes",
            "password": "ChefPass123!"
        })

        # Create a recipe as Julia
        create_res = self.client.post("/api/recipes", json={
            "title": "Julia's Secret Brioche",
            "description": "Rich and buttery brioche loaf.",
            "prep_time_min": 60,
            "cook_time_min": 30,
            "servings": 6,
            "ingredients": [{"name": "Flour", "amount": "500", "unit": "g"}],
            "steps": [{"step_number": 1, "instruction": "Mix and knead."}],
            "is_public": 1
        })
        self.assertEqual(create_res.status_code, 201)
        recipe_id = create_res.get_json()["recipe_id"]

        # Now login as marco_pasta
        self.client.post("/api/auth/login", json={
            "username": "marco_pasta",
            "password": "ChefPass123!"
        })

        # Try to modify Julia's recipe
        edit_res = self.client.put(f"/api/recipes/{recipe_id}", json={
            "title": "Hacked Brioche"
        })
        self.assertEqual(edit_res.status_code, 403, "IDOR check should prevent modifying another user's recipe")

        # Try to delete Julia's recipe
        del_res = self.client.delete(f"/api/recipes/{recipe_id}")
        self.assertEqual(del_res.status_code, 403, "IDOR check should prevent deleting another user's recipe")

    def test_05_recipe_bookmark_and_fork(self):
        """Verify bookmarking to recipe box and forking recipes."""
        # Login as marco_pasta
        self.client.post("/api/auth/login", json={
            "username": "marco_pasta",
            "password": "ChefPass123!"
        })

        # Get public recipes
        recipes_res = self.client.get("/api/recipes?scope=all")
        self.assertEqual(recipes_res.status_code, 200)
        recipes = recipes_res.get_json()["recipes"]
        self.assertTrue(len(recipes) > 0)
        target_recipe = recipes[0]

        # Save to Recipe Box
        save_res = self.client.post(f"/api/recipes/{target_recipe['id']}/save", json={
            "folder_name": "Must Try",
            "notes": "Looks amazing!"
        })
        self.assertEqual(save_res.status_code, 200)
        self.assertTrue(save_res.get_json()["is_saved"])

        # Check saved list
        saved_list_res = self.client.get("/api/recipes?scope=saved")
        self.assertEqual(saved_list_res.status_code, 200)
        saved_recipes = saved_list_res.get_json()["recipes"]
        self.assertTrue(any(r["id"] == target_recipe["id"] for r in saved_recipes))

        # Fork recipe
        fork_res = self.client.post(f"/api/recipes/{target_recipe['id']}/fork")
        self.assertEqual(fork_res.status_code, 201)
        new_fork_id = fork_res.get_json()["recipe_id"]

        # Detail check
        fork_detail = self.client.get(f"/api/recipes/{new_fork_id}")
        self.assertEqual(fork_detail.status_code, 200)
        self.assertIn("(My Fork)", fork_detail.get_json()["recipe"]["title"])

    def test_06_community_feed_comments_likes(self):
        """Verify creating community posts, liking, and nested comments."""
        # Login as headchef
        self.client.post("/api/auth/login", json={
            "username": "headchef",
            "password": "ChefPass123!"
        })

        # Create Question Post
        post_res = self.client.post("/api/posts", json={
            "content": "What is everyone cooking for dinner tonight?",
            "post_type": "question"
        })
        self.assertEqual(post_res.status_code, 201)
        post_id = post_res.get_json()["post_id"]

        # Like post
        like_res = self.client.post(f"/api/posts/{post_id}/like")
        self.assertEqual(like_res.status_code, 200)
        self.assertTrue(like_res.get_json()["is_liked"])

        # Add comment
        comment_res = self.client.post(f"/api/posts/{post_id}/comments", json={
            "comment": "Making handmade gnocchi with sage brown butter!"
        })
        self.assertEqual(comment_res.status_code, 201)

        # Get comments
        get_comments = self.client.get(f"/api/posts/{post_id}/comments")
        self.assertEqual(get_comments.status_code, 200)
        self.assertEqual(len(get_comments.get_json()["comments"]), 1)

    def test_07_meal_planner(self):
        """Verify meal planner scheduling."""
        # Login as headchef
        self.client.post("/api/auth/login", json={
            "username": "headchef",
            "password": "ChefPass123!"
        })

        # Meal Planner
        plan_res = self.client.post("/api/planner", json={
            "plan_date": "2026-10-15",
            "meal_type": "dinner",
            "custom_title": "Homemade Pizza Night",
            "notes": "Cold ferment dough for 48 hours"
        })
        self.assertEqual(plan_res.status_code, 201)

        # Get planner
        get_res = self.client.get("/api/planner?start_date=2026-10-15&end_date=2026-10-15")
        self.assertEqual(get_res.status_code, 200)
        self.assertTrue(len(get_res.get_json()["planner"]) > 0)

    def test_08_login_rate_limiting_lockout(self):
        """Verify exceeding MAX_FAILED_ATTEMPTS (10) per (IP, username) triggers 429 lockout."""
        target_username = "brute_force_target_chef"
        for _ in range(10):
            self.client.post("/api/auth/login", json={
                "username": target_username,
                "password": "WrongPassword123!"
            })

        # 11th attempt on the same username/IP pair should return 429
        lockout_res = self.client.post("/api/auth/login", json={
            "username": target_username,
            "password": "WrongPassword123!"
        })
        self.assertEqual(lockout_res.status_code, 429, "10 failed logins on the same account must trigger rate-limit lockout")

        # A *different* username from the same IP must NOT be locked out
        other_res = self.client.post("/api/auth/login", json={
            "username": "completely_different_user",
            "password": "WrongPassword123!"
        })
        self.assertNotEqual(other_res.status_code, 429, "Different username must have its own independent counter")

        from auth import reset_auth_caches
        reset_auth_caches()

    def test_09_scraper_ingredient_parser(self):
        """Verify ingredient string regex parsing into quantity, unit, name."""
        from scraper import parse_ingredient_line
        res = parse_ingredient_line("2 cups of all-purpose flour")
        self.assertEqual(res["amount"], "2")
        self.assertEqual(res["unit"], "cups")
        self.assertIn("flour", res["name"].lower())
        self.assertEqual(res["category"], "Bakery")

        res2 = parse_ingredient_line("500g spaghetti")
        self.assertEqual(res2["amount"], "500")
        self.assertEqual(res2["unit"], "g")
        self.assertEqual(res2["name"], "spaghetti")

    def test_10_global_search_endpoint(self):
        """Verify unified /api/search returns matching recipes, chefs, stations, and posts."""
        # Empty query returns empty categories
        empty_res = self.client.get("/api/search?q=")
        self.assertEqual(empty_res.status_code, 200)
        empty_data = empty_res.get_json()
        self.assertEqual(len(empty_data["recipes"]), 0)

        # Search for 'pasta' (seeded recipe and station)
        search_res = self.client.get("/api/search?q=pasta")
        self.assertEqual(search_res.status_code, 200)
        data = search_res.get_json()
        self.assertEqual(data["query"], "pasta")
        self.assertTrue(len(data["recipes"]) > 0 or len(data["stations"]) > 0)
        self.assertIn("chefs", data)
        self.assertIn("posts", data)

        # Search for user with @ prefix
        user_res = self.client.get("/api/search?q=@headchef")
        self.assertEqual(user_res.status_code, 200)
        user_data = user_res.get_json()
        self.assertTrue(any(c["username"] == "headchef" for c in user_data["chefs"]))

        # Verify /api/users endpoint
        list_users_res = self.client.get("/api/users?q=chef")
        self.assertEqual(list_users_res.status_code, 200)
        self.assertIn("users", list_users_res.get_json())

if __name__ == "__main__":
    unittest.main()
