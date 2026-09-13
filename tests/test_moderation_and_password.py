import unittest
import os
import json
import tempfile

temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
os.environ["COOKED_DB_PATH"] = temp_db_path
os.environ["ADMIN_USERNAMES"] = "testadmin,headchef"

from app import app
from database import init_db, seed_data_if_empty
from auth import validate_password_strength
from moderation_filter import contains_profanity, validate_clean_content

class ModerationAndPasswordTestCase(unittest.TestCase):
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

    def test_01_password_strength_validator(self):
        """Test unit validation of password strength policy."""
        # Too short
        valid, msg = validate_password_strength("Ab1!")
        self.assertFalse(valid)
        self.assertIn("at least 8 characters", msg)

        # No uppercase
        valid, msg = validate_password_strength("chefpass123!")
        self.assertFalse(valid)
        self.assertIn("uppercase", msg)

        # No lowercase
        valid, msg = validate_password_strength("CHEFPASS123!")
        self.assertFalse(valid)
        self.assertIn("lowercase", msg)

        # No digit
        valid, msg = validate_password_strength("ChefPassWord!")
        self.assertFalse(valid)
        self.assertIn("number", msg)

        # No special symbol
        valid, msg = validate_password_strength("ChefPass1234")
        self.assertFalse(valid)
        self.assertIn("special symbol", msg)

        # Common weak password
        valid, msg = validate_password_strength("Password123")
        self.assertFalse(valid)

        # Valid strong password
        valid, msg = validate_password_strength("ArtisanBake_2026!")
        self.assertTrue(valid)
        self.assertIsNone(msg)

    def test_02_profanity_filter_unit(self):
        """Test profanity, slurs, hate speech, slavery terms, and dogwhistles detection."""
        # Innocent culinary words must NOT be flagged
        safe_words = [
            "cocktail sauce", "shiitake mushrooms", "sea bass",
            "cassava flour", "pass the black pepper", "butter basted steak",
            "14 grams", "50 grams", "shaved parmesan"
        ]
        for item in safe_words:
            bad, term = contains_profanity(item)
            self.assertFalse(bad, f"False positive on safe culinary phrase: '{item}'")

        # Prohibited slurs, severe profanity, hate dogwhistles & slavery terms MUST be flagged
        bad_words = [
            "fuck", "f u c k", "f.u.c.k", "b1tch", "b i t c h",
            "sh1t", "asshole", "dickhead", "nigger", "n1gger", "faggot",
            "kike", "chink", "spic", "retard", "kill yourself",
            "Slave", "slave", "s_l_a_v_e", "$lave", "5lave", "slavemaster", "slave_master",
            "13%=50%", "13% = 50%", "13=50", "13/50", "1350", "13_50",
            "1488", "14/88", "14 88", "14 words",
            "kkk", "k_k_k", "ku klux klan", "hitler", "h1tler", "nazi", "neo-nazi",
            "lynching", "white power"
        ]
        for item in bad_words:
            bad, term = contains_profanity(item)
            self.assertTrue(bad, f"Failed to flag prohibited term: '{item}'")

    def test_03_registration_rejects_weak_passwords(self):
        """Verify POST /api/auth/register rejects basic/weak passwords."""
        res = self.client.post("/api/auth/register", json={
            "username": "baker_bob",
            "email": "bob@cooked.community",
            "password": "simplepassword",  # Missing upper, number, symbol
            "display_name": "Baker Bob"
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("Validation Error", data["error"])

    def test_04_registration_rejects_inappropriate_names(self):
        """Verify POST /api/auth/register rejects offensive usernames, hate dogwhistles, and slavery names."""
        offensive_candidates = [
            ("f_u_c_k_chef", "Good Chef"),
            ("chef_claire", "b1tch_in_the_kitchen"),
            ("Slave", "Chef Sam"),
            ("chef_sam", "SlaveMaster"),
            ("1350_chef", "Pro Baker"),
            ("chef_leo", "13%=50%"),
            ("1488_baker", "Baker 88"),
            ("kkk_member", "Sous Chef"),
            ("BlGBLACNlggзrDlCK", "Offensive User"),
            ("chef_bad", "BlGBLACNlggзrDlCK")
        ]
        for username, display_name in offensive_candidates:
            res = self.client.post("/api/auth/register", json={
                "username": username,
                "email": f"{username.lower().replace('%','').replace('=','')}@cooked.community",
                "password": "StrongPassword123!",
                "display_name": display_name
            })
            self.assertEqual(res.status_code, 400, f"Allowed inappropriate account: {username} / {display_name}")
            self.assertIn("prohibited", res.get_json()["message"])

    def test_05_post_and_comment_profanity_block(self):
        """Verify community posts and comments with profanity and hate speech are blocked."""
        # Register a valid user
        self.client.post("/api/auth/register", json={
            "username": "clean_cook_carol",
            "email": "carol@cooked.community",
            "password": "CleanPassWord123!",
            "display_name": "Carol Clean"
        })
        # Login
        self.client.post("/api/auth/login", json={
            "username": "clean_cook_carol",
            "password": "CleanPassWord123!"
        })

        # Attempt to post profane content
        res_post = self.client.post("/api/posts", json={
            "content": "This recipe is total sh1t and f.u.c.k.i.n.g useless!",
            "post_type": "post"
        })
        self.assertEqual(res_post.status_code, 400)
        self.assertIn("prohibited", res_post.get_json()["message"])

        # Attempt to post dogwhistle / hate speech content
        res_hate_post = self.client.post("/api/posts", json={
            "content": "Did you know that 13%=50% according to the stats?",
            "post_type": "post"
        })
        self.assertEqual(res_hate_post.status_code, 400)
        self.assertIn("prohibited", res_hate_post.get_json()["message"])

        # Attempt to add profane comment to post 1
        res_comment = self.client.post("/api/posts/1/comments", json={
            "comment": "You are a complete dumbass and dickhead."
        })
        self.assertEqual(res_comment.status_code, 400)
        self.assertIn("prohibited", res_comment.get_json()["message"])

    def test_06_recipe_and_station_profanity_block(self):
        """Verify recipe titles and station names reject profanity and hate tropes."""
        self.client.post("/api/auth/login", json={
            "username": "clean_cook_carol",
            "password": "CleanPassWord123!"
        })

        # Recipe title with profanity
        res_recipe = self.client.post("/api/recipes", json={
            "title": "Fucking Good Truffle Risotto",
            "description": "Delicious risotto"
        })
        self.assertEqual(res_recipe.status_code, 400)
        self.assertIn("prohibited", res_recipe.get_json()["message"])

        # Station name with hate speech / dogwhistle
        res_station = self.client.post("/api/stations", json={
            "name": "Station 1488",
            "description": "Baking with hate"
        })
        self.assertEqual(res_station.status_code, 400)
        self.assertIn("prohibited", res_station.get_json()["message"])

if __name__ == "__main__":
    unittest.main()
