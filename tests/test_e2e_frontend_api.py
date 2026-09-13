import unittest
import os
import io
import json
import tempfile
from PIL import Image

temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
os.environ["COOKED_DB_PATH"] = temp_db_path
os.environ["ADMIN_USERNAMES"] = "headchef,admin"

from app import app
from database import init_db, seed_data_if_empty
from scraper import fallback_json_ld_scrape

class E2EComprehensiveTestCase(unittest.TestCase):
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

    def test_01_static_files_served(self):
        """Verify frontend assets are served correctly."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Cooked", res.data)
        self.assertIn(b"Recipe Box", res.data)

        css_res = self.client.get("/css/style.css")
        self.assertEqual(css_res.status_code, 200)
        self.assertIn(b"--primary", css_res.data)

        js_res = self.client.get("/js/app.js")
        self.assertEqual(js_res.status_code, 200)

    def test_02_image_upload_and_pillow_processing(self):
        """Verify image upload downsamples to max 1280x1280 JPEG with Pillow."""
        # Login first
        self.client.post("/api/auth/login", json={
            "username": "headchef",
            "password": "ChefPass123!"
        })

        # Create a large dummy image in memory (2000x1500 RGBA)
        img = Image.new("RGBA", (2000, 1500), color=(255, 100, 50, 255))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)

        res = self.client.post("/api/upload", data={
            "image": (img_byte_arr, "test_dish.png")
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["url"].startswith("/uploads/"))
        self.assertTrue(data["filename"].endswith((".webp", ".jpg")))

        # Verify the saved image was resized
        from app import UPLOAD_FOLDER
        saved_img_path = os.path.join(UPLOAD_FOLDER, data["filename"])
        self.assertTrue(os.path.exists(saved_img_path))
        with Image.open(saved_img_path) as saved_img:
            self.assertLessEqual(saved_img.width, 1280)
            self.assertLessEqual(saved_img.height, 1280)
            self.assertIn(saved_img.format, ("WEBP", "JPEG"))

    def test_03_scraper_json_ld_fallback(self):
        """Verify fallback JSON-LD parser extracts structured recipe data from HTML."""
        sample_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Recipe",
                "name": "Classic French Omelette",
                "description": "Silky, custardy French omelette with fresh herbs.",
                "recipeYield": "2 servings",
                "recipeIngredient": [
                    "3 large eggs",
                    "1 tbsp unsalted butter",
                    "1 tbsp minced chives",
                    "Pinch of sea salt"
                ],
                "recipeInstructions": [
                    {"@type": "HowToStep", "text": "Whisk eggs with salt until completely smooth."},
                    {"@type": "HowToStep", "text": "Melt butter in a non-stick pan over medium-low heat."},
                    {"@type": "HowToStep", "text": "Pour eggs and shake pan rapidly while stirring vigorously."},
                    {"@type": "HowToStep", "text": "Roll tightly into an almond cylinder and brush with butter."}
                ]
            }
            </script>
        </head>
        <body></body>
        </html>
        """
        extracted = fallback_json_ld_scrape("https://culinary.test/french-omelette", sample_html)
        self.assertEqual(extracted["title"], "Classic French Omelette")
        self.assertEqual(len(extracted["ingredients"]), 4)
        self.assertEqual(len(extracted["steps"]), 4)
        self.assertEqual(extracted["servings"], 2)

    def test_04_weekly_meal_plan_scheduling(self):
        """Verify weekly meal planner scheduling and retrieval."""
        self.client.post("/api/auth/login", json={
            "username": "headchef",
            "password": "ChefPass123!"
        })

        # Get cacio e pepe recipe id
        recipes = self.client.get("/api/recipes?scope=all").get_json()["recipes"]
        recipe_id = recipes[0]["id"]

        # Schedule meal
        plan_res = self.client.post("/api/planner", json={
            "plan_date": "2026-11-20",
            "meal_type": "dinner",
            "recipe_id": recipe_id
        })
        self.assertEqual(plan_res.status_code, 201)

        # Check planner retrieval
        p_res = self.client.get("/api/planner?start_date=2026-11-19&end_date=2026-11-21")
        self.assertEqual(p_res.status_code, 200)
        self.assertTrue(len(p_res.get_json()["planner"]) > 0)

    def test_05_weekly_grocery_list_and_clear_week(self):
        """Verify on-demand weekly grocery checklist generation and clear-week endpoint."""
        self.client.post("/api/auth/login", json={
            "username": "headchef",
            "password": "ChefPass123!"
        })

        # Get seeded recipe
        recipes = self.client.get("/api/recipes?scope=all").get_json()["recipes"]
        recipe_id = recipes[0]["id"]

        # Schedule 2 meals for a specific week
        self.client.post("/api/planner", json={
            "plan_date": "2026-12-01",
            "meal_type": "dinner",
            "recipe_id": recipe_id
        })
        self.client.post("/api/planner", json={
            "plan_date": "2026-12-02",
            "meal_type": "lunch",
            "recipe_id": recipe_id
        })

        # Fetch aggregated grocery list
        g_res = self.client.get("/api/planner/grocery-list?start_date=2026-12-01&end_date=2026-12-07")
        self.assertEqual(g_res.status_code, 200)
        g_data = g_res.get_json()
        self.assertTrue(g_data["success"])
        self.assertGreater(g_data["total_items"], 0)
        self.assertIn("categories", g_data)

        # Clear the week
        clear_res = self.client.post("/api/planner/clear-week", json={
            "start_date": "2026-12-01",
            "end_date": "2026-12-07"
        })
        self.assertEqual(clear_res.status_code, 200)
        self.assertEqual(clear_res.get_json()["deleted_count"], 2)

        # Verify cleared
        check_res = self.client.get("/api/planner?start_date=2026-12-01&end_date=2026-12-07")
        self.assertEqual(len(check_res.get_json()["planner"]), 0)

    def test_06_profile_update_with_uploaded_avatar(self):
        """Verify user can upload an image and save it as their profile avatar."""
        self.client.post("/api/auth/login", json={
            "username": "headchef",
            "password": "ChefPass123!"
        })

        # 1. Upload avatar photo
        img = Image.new("RGB", (400, 400), color=(100, 200, 150))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="JPEG")
        img_byte_arr.seek(0)

        upload_res = self.client.post("/api/upload", data={
            "image": (img_byte_arr, "profile_pic.jpg")
        }, content_type="multipart/form-data")
        self.assertEqual(upload_res.status_code, 200)
        uploaded_url = upload_res.get_json()["url"]
        self.assertTrue(uploaded_url.startswith("/uploads/"))

        # 2. Update profile with uploaded avatar
        update_res = self.client.put("/api/users/profile", json={
            "display_name": "Chef Head Master",
            "avatar_url": uploaded_url,
            "bio": "Passionate about artisanal bread, homemade pasta, and farm-to-table dining."
        })
        self.assertEqual(update_res.status_code, 200)

        # 3. Verify user profile returns updated avatar and info
        profile_res = self.client.get("/api/users/headchef")
        self.assertEqual(profile_res.status_code, 200)
        user_info = profile_res.get_json()["user"]
        self.assertEqual(user_info["display_name"], "Chef Head Master")
        self.assertEqual(user_info["avatar_url"], uploaded_url)
        self.assertEqual(user_info["bio"], "Passionate about artisanal bread, homemade pasta, and farm-to-table dining.")

        # 4. Verify uploaded image is served via static route
        served_img_res = self.client.get(uploaded_url)
        self.assertEqual(served_img_res.status_code, 200)

if __name__ == "__main__":
    unittest.main()

