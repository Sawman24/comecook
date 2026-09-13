import os
import tempfile
import unittest
import json
from app import app
from database import get_db_connection, init_db, seed_data_if_empty

class TestAdvancedSocialSuite(unittest.TestCase):
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

    # --------------------------------------------------------------------------
    # 1. DIRECT MESSAGING (KITCHEN WHISPERS)
    # --------------------------------------------------------------------------
    def test_01_direct_messaging_flow_and_attachments(self):
        c1 = self.register_and_login("whisperer1", "whisperer1@example.com")
        c2 = self.register_and_login("whisperer2", "whisperer2@example.com")

        # Get C2 profile to find ID
        c2_prof = c1.get("/api/users/whisperer2").get_json()["user"]
        c2_id = c2_prof["id"]
        c1_id = c2.get("/api/users/whisperer1").get_json()["user"]["id"]

        # C1 and C2 follow each other (friends)
        c1.post(f"/api/users/{c2_id}/follow")
        c2.post(f"/api/users/{c1_id}/follow")

        # C1 sends recipe to C2 via DM
        rec_res = c1.post("/api/recipes", json={
            "title": "Secret Truffle Sauce",
            "description": "Family secret",
            "ingredients": [{"name": "Truffle Oil", "amount": "1", "unit": "tbsp"}],
            "steps": [{"step_number": 1, "instruction": "Whisk into warm butter."}],
            "is_public": 1
        })
        recipe_id = rec_res.get_json()["recipe_id"]

        dm_res = c1.post(f"/api/messages/{c2_id}", json={
            "message": "Here is the secret recipe we talked about!",
            "recipe_id": recipe_id
        })
        self.assertEqual(dm_res.status_code, 201)
        dm_data = dm_res.get_json()["dm"]
        self.assertEqual(dm_data["recipe_title"], "Secret Truffle Sauce")

        # C2 checks unread count
        unread_res = c2.get("/api/messages/unread-count")
        self.assertEqual(unread_res.status_code, 200)
        self.assertEqual(unread_res.get_json()["unread_count"], 1)

        # C2 views conversations list
        convos_res = c2.get("/api/messages/conversations")
        self.assertEqual(convos_res.status_code, 200)
        convos = convos_res.get_json()["conversations"]
        self.assertTrue(len(convos) >= 1)
        self.assertEqual(convos[0]["partner"]["username"], "whisperer1")

        # C2 opens message thread with C1
        c1_id = c2.get("/api/users/whisperer1").get_json()["user"]["id"]
        thread_res = c2.get(f"/api/messages/{c1_id}")
        self.assertEqual(thread_res.status_code, 200)
        messages = thread_res.get_json()["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["recipe_title"], "Secret Truffle Sauce")

        # After viewing thread, unread count becomes 0
        unread_after = c2.get("/api/messages/unread-count").get_json()["unread_count"]
        self.assertEqual(unread_after, 0)

        # Notification verification for C2
        notifs = c2.get("/api/notifications").get_json()["notifications"]
        self.assertTrue(any(n["type"] == "dm" for n in notifs))

    # --------------------------------------------------------------------------
    # 2. CULINARY MULTI-REACTIONS
    # --------------------------------------------------------------------------
    def test_02_culinary_multi_reactions(self):
        c1 = self.register_and_login("reactor1", "reactor1@example.com")
        c2 = self.register_and_login("reactor2", "reactor2@example.com")

        # C1 posts a dish
        p_res = c1.post("/api/posts", json={
            "content": "Check out this 60-day dry aged ribeye sear!",
            "post_type": "showcase"
        })
        post_id = p_res.get_json()["post_id"]

        # C2 reacts with 'fire'
        rx_res = c2.post(f"/api/posts/{post_id}/react", json={"reaction": "fire"})
        self.assertEqual(rx_res.status_code, 200)
        rx_data = rx_res.get_json()
        self.assertEqual(rx_data["user_reaction"], "fire")
        self.assertEqual(rx_data["reactions"]["counts"]["fire"], 1)

        # C2 toggles to 'chef_kiss'
        rx_res2 = c2.post(f"/api/posts/{post_id}/react", json={"reaction": "chef_kiss"})
        self.assertEqual(rx_res2.status_code, 200)
        rx_data2 = rx_res2.get_json()
        self.assertEqual(rx_data2["user_reaction"], "chef_kiss")
        self.assertEqual(rx_data2["reactions"]["counts"]["fire"], 0)
        self.assertEqual(rx_data2["reactions"]["counts"]["chef_kiss"], 1)

        # C2 clicks 'chef_kiss' again to toggle off
        rx_res3 = c2.post(f"/api/posts/{post_id}/react", json={"reaction": "chef_kiss"})
        self.assertEqual(rx_res3.status_code, 200)
        self.assertIsNone(rx_res3.get_json()["user_reaction"])
        self.assertEqual(rx_res3.get_json()["reactions"]["counts"]["chef_kiss"], 0)

        # Invalid reaction returns 400
        bad_rx = c2.post(f"/api/posts/{post_id}/react", json={"reaction": "thumbs_up"})
        self.assertEqual(bad_rx.status_code, 400)

    # --------------------------------------------------------------------------
    # 3. COMMUNITY POLLS & VOTING
    # --------------------------------------------------------------------------
    def test_03_community_polls_creation_and_voting(self):
        c1 = self.register_and_login("poller1", "poller1@example.com")
        c2 = self.register_and_login("poller2", "poller2@example.com")

        # C1 creates post with attached poll
        p_res = c1.post("/api/posts", json={
            "content": "What is the superior fat for high-heat steak searing?",
            "post_type": "question",
            "poll": {
                "question": "Best high-heat sear fat?",
                "options": ["Avocado Oil", "Beef Tallow", "Ghee / Clarified Butter"]
            }
        })
        self.assertEqual(p_res.status_code, 201)

        # Retrieve feed to check poll hydration
        feed = c2.get("/api/posts?type=question").get_json()["posts"]
        poll_post = next((p for p in feed if p["content"].startswith("What is the superior fat")), None)
        self.assertIsNotNone(poll_post)
        self.assertIsNotNone(poll_post["poll"])
        poll_id = poll_post["poll"]["id"]
        self.assertEqual(len(poll_post["poll"]["options"]), 3)

        # C2 votes for Option 1 (Beef Tallow)
        vote_res = c2.post(f"/api/polls/{poll_id}/vote", json={"option_index": 1})
        self.assertEqual(vote_res.status_code, 200)
        v_data = vote_res.get_json()["poll"]
        self.assertEqual(v_data["total_votes"], 1)
        self.assertEqual(v_data["user_voted_index"], 1)
        self.assertEqual(v_data["options"][1]["percent"], 100)

        # C1 votes for Option 2 (Ghee)
        c1.post(f"/api/polls/{poll_id}/vote", json={"option_index": 2})
        feed_after = c2.get("/api/posts?type=question").get_json()["posts"]
        poll_after = next(p for p in feed_after if p["id"] == poll_post["id"])["poll"]
        self.assertEqual(poll_after["total_votes"], 2)
        self.assertEqual(poll_after["options"][1]["percent"], 50)
        self.assertEqual(poll_after["options"][2]["percent"], 50)

    # --------------------------------------------------------------------------
    # 4. @MENTIONS AUTOCOMPLETE & NOTIFICATIONS
    # --------------------------------------------------------------------------
    def test_04_mentions_in_posts_and_comments(self):
        c1 = self.register_and_login("mentioner", "mentioner@example.com")
        c2 = self.register_and_login("targetchef", "targetchef@example.com")

        # C1 posts with @targetchef mention
        p_res = c1.post("/api/posts", json={
            "content": "Hey @targetchef, what do you think of this hydration level?",
            "post_type": "post"
        })
        post_id = p_res.get_json()["post_id"]

        # C2 checks notifications
        notifs = c2.get("/api/notifications").get_json()["notifications"]
        mention_notif = next((n for n in notifs if n["type"] == "mention"), None)
        self.assertIsNotNone(mention_notif)
        self.assertIn("@mentioner mentioned you", mention_notif["message"])

        # C1 comments on post with mention
        c1.post(f"/api/posts/{post_id}/comments", json={
            "comment": "Also paging @targetchef to check the crumb!"
        })
        notifs2 = c2.get("/api/notifications").get_json()["notifications"]
        mention_comments = [n for n in notifs2 if n["type"] == "mention"]
        self.assertEqual(len(mention_comments), 2)

    # --------------------------------------------------------------------------
    # 5. GAMIFIED CHEF BADGES & PROGRESSION
    # --------------------------------------------------------------------------
    def test_05_gamified_badges_progression(self):
        # Admin user gets Executive Chef badge
        admin_client = self.register_and_login("adminbadge", "adminbadge@example.com")
        conn = get_db_connection()
        conn.execute("UPDATE users SET is_admin = 1 WHERE username = 'adminbadge';")
        conn.commit()
        conn.close()

        prof = admin_client.get("/api/users/adminbadge").get_json()
        badge_ids = [b["id"] for b in prof["badges"]]
        self.assertIn("admin", badge_ids)

        # Sourdough & Baking Specialist badge
        baker = self.register_and_login("sourdoughguy", "sourdoughguy@example.com")
        for i in range(2):
            baker.post("/api/recipes", json={
                "title": f"Artisan Loaf {i}",
                "description": "High hydration sourdough",
                "tags": ["Sourdough", "Baking", "Bread"],
                "ingredients": [{"name": "Flour", "amount": "500", "unit": "g"}],
                "steps": [{"step_number": 1, "instruction": "Stretch and fold."}],
                "is_public": 1
            })

        baker_prof = baker.get("/api/users/sourdoughguy").get_json()
        baker_badges = [b["id"] for b in baker_prof["badges"]]
        self.assertIn("sourdough_master", baker_badges)

    # --------------------------------------------------------------------------
    # 6. DISCOVERY FEEDS & DIETARY FILTERS
    # --------------------------------------------------------------------------
    def test_06_discovery_feeds_and_dietary_filters(self):
        vegan_chef = self.register_and_login("veganchef", "veganchef@example.com")
        keto_chef = self.register_and_login("ketochef", "ketochef@example.com")

        # Vegan recipe & post
        v_rec = vegan_chef.post("/api/recipes", json={
            "title": "Avocado Green Goddess Bowl",
            "description": "100% plant-based nourish bowl",
            "tags": ["Vegan", "Vegetarian", "Healthy", "Gluten-Free"],
            "ingredients": [{"name": "Avocado", "amount": "1", "unit": "piece"}],
            "steps": [{"step_number": 1, "instruction": "Toss with lemon dressing."}],
            "is_public": 1
        })
        v_rec_id = v_rec.get_json()["recipe_id"]

        vegan_chef.post("/api/posts", json={
            "content": "Fresh vegan harvest salad bowl ready for lunch!",
            "recipe_id": v_rec_id,
            "post_type": "showcase"
        })

        # Keto post
        keto_chef.post("/api/posts", json={
            "content": "Ribeye steak cooked in garlic butter! Strictly #keto",
            "post_type": "post"
        })

        # Test dietary filter: vegan
        vegan_feed = vegan_chef.get("/api/posts?dietary=vegan").get_json()["posts"]
        self.assertTrue(len(vegan_feed) >= 1)
        self.assertTrue(all("vegan" in p["content"].lower() or "plant-based" in p.get("recipe_title", "").lower() or "avocado" in p.get("recipe_title", "").lower() for p in vegan_feed))

        # Test dietary filter: keto
        keto_feed = keto_chef.get("/api/posts?dietary=keto").get_json()["posts"]
        self.assertTrue(len(keto_feed) >= 1)

        # Test feed algorithms: trending
        trending = vegan_chef.get("/api/posts?type=trending").get_json()["posts"]
        self.assertTrue(isinstance(trending, list))

        # Test user dietary profile update
        update_res = vegan_chef.put("/api/users/profile", json={
            "display_name": "Chef Vegan Pro",
            "dietary_preferences": ["Vegan", "Gluten-Free"]
        })
        self.assertEqual(update_res.status_code, 200)
        v_profile = vegan_chef.get("/api/users/veganchef").get_json()["user"]
        self.assertIn("Vegan", v_profile["dietary_preferences"])
        self.assertIn("Gluten-Free", v_profile["dietary_preferences"])

    # --------------------------------------------------------------------------
    # 7. USER SAFETY & BLOCKING
    # --------------------------------------------------------------------------
    def test_07_user_blocking_and_safety_enforcement(self):
        alice = self.register_and_login("alice_cook", "alice@example.com")
        bob = self.register_and_login("bob_cook", "bob@example.com")

        bob_id = alice.get("/api/users/bob_cook").get_json()["user"]["id"]
        alice_id = bob.get("/api/users/alice_cook").get_json()["user"]["id"]

        # Alice creates a post
        p_res = alice.post("/api/posts", json={"content": "Alice's secret soup recipe."})
        post_id = p_res.get_json()["post_id"]

        # Alice blocks Bob
        block_res = alice.post(f"/api/users/{bob_id}/block")
        self.assertEqual(block_res.status_code, 200)
        self.assertTrue(block_res.get_json()["is_blocked"])

        # Check blocked users list for Alice
        blocked_list = alice.get("/api/users/blocked").get_json()["blocked_users"]
        self.assertEqual(len(blocked_list), 1)
        self.assertEqual(blocked_list[0]["username"], "bob_cook")

        # Bob attempts to send DM to Alice -> 403 Forbidden
        dm_res = bob.post(f"/api/messages/{alice_id}", json={"message": "Hey Alice!"})
        self.assertEqual(dm_res.status_code, 403)

        # Bob attempts to comment on Alice's post -> 403 Forbidden
        comment_res = bob.post(f"/api/posts/{post_id}/comments", json={"comment": "Nice soup"})
        self.assertEqual(comment_res.status_code, 403)

        # Alice's feed does not show Bob's posts, and Bob's feed does not show Alice's posts
        bob_feed = bob.get("/api/posts").get_json()["posts"]
        self.assertFalse(any(p["id"] == post_id for p in bob_feed))

        # Alice unblocks Bob
        unblock_res = alice.delete(f"/api/users/{bob_id}/block")
        self.assertEqual(unblock_res.status_code, 200)
        self.assertFalse(unblock_res.get_json()["is_blocked"])

        # Now Bob can DM Alice
        dm_ok = bob.post(f"/api/messages/{alice_id}", json={"message": "Glad we made up!"})
        self.assertEqual(dm_ok.status_code, 201)

    # --------------------------------------------------------------------------
    # 8. PASSWORD RESET DISABLED CHECK
    # --------------------------------------------------------------------------
    def test_08_password_reset_is_safely_disabled(self):
        client = app.test_client()
        forgot_res = client.post("/api/auth/forgot-password", json={"email": "whisperer1@example.com"})
        self.assertEqual(forgot_res.status_code, 400)
        self.assertIn("disabled", forgot_res.get_json()["message"].lower())
        self.assertNotIn("dev_reset_token", forgot_res.get_json())

        reset_res = client.post("/api/auth/reset-password", json={"token": "sometoken", "new_password": "NewPassword123!"})
        self.assertEqual(reset_res.status_code, 400)
        self.assertIn("disabled", reset_res.get_json()["message"].lower())

if __name__ == "__main__":
    unittest.main()
