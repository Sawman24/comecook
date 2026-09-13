import os
import tempfile
import unittest
import json
from app import app, are_users_friends, get_message_request_info
from database import get_db_connection, init_db, seed_data_if_empty

class TestFriendMessagingAndRequests(unittest.TestCase):
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
            "display_name": f"Cook {username.capitalize()}"
        })
        client.post("/api/auth/login", json={
            "username": username,
            "password": password
        })
        return client

    def test_01_non_friends_message_creates_pending_request(self):
        c_alice = self.register_and_login("alice_chef", "alice@example.com")
        c_bob = self.register_and_login("bob_chef", "bob@example.com")

        # Get Bob's ID
        bob_id = c_alice.get("/api/users/bob_chef").get_json()["user"]["id"]
        alice_id = c_bob.get("/api/users/alice_chef").get_json()["user"]["id"]

        # Assert Alice and Bob are NOT friends yet
        self.assertFalse(are_users_friends(alice_id, bob_id))

        # Alice sends first message to non-friend Bob
        res = c_alice.post(f"/api/messages/{bob_id}", json={"message": "Hey Bob, love your pasta technique!"})
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["is_request"])
        self.assertIn("request", data["message"].lower())

        # Check Bob's unread counts (should have 1 unread request)
        unread_res = c_bob.get("/api/messages/unread-count").get_json()
        self.assertEqual(unread_res["unread_requests_count"], 1)

        # Check Bob's conversations (should appear in requests tab)
        convos = c_bob.get("/api/messages/conversations?tab=requests").get_json()
        self.assertEqual(len(convos["requests"]), 1)
        self.assertEqual(convos["requests"][0]["partner"]["username"], "alice_chef")
        self.assertTrue(convos["requests"][0]["is_request"])

        # Check Bob viewing Alice's thread
        thread_res = c_bob.get(f"/api/messages/{alice_id}").get_json()
        self.assertTrue(thread_res["is_pending_request"])
        self.assertTrue(thread_res["is_request_recipient"])
        self.assertFalse(thread_res["is_friend"])

        # Check Bob's notification inbox
        notifs = c_bob.get("/api/notifications").get_json()["notifications"]
        self.assertTrue(any(n["type"] == "message_request" and "alice_chef" in n["message"] for n in notifs))

    def test_02_spam_prevention_on_pending_request(self):
        c_alice = self.register_and_login("alice_chef2", "alice2@example.com")
        c_bob = self.register_and_login("bob_chef2", "bob2@example.com")

        bob_id = c_alice.get("/api/users/bob_chef2").get_json()["user"]["id"]

        # First message request succeeds
        res1 = c_alice.post(f"/api/messages/{bob_id}", json={"message": "Request #1"})
        self.assertEqual(res1.status_code, 201)

        # Second message before Bob accepts is blocked by anti-spam rule
        res2 = c_alice.post(f"/api/messages/{bob_id}", json={"message": "Request #2 (spam)"})
        self.assertEqual(res2.status_code, 400)
        self.assertIn("pending", res2.get_json()["message"].lower())

    def test_03_accept_message_request_enables_full_chat(self):
        c_alice = self.register_and_login("alice_chef3", "alice3@example.com")
        c_bob = self.register_and_login("bob_chef3", "bob3@example.com")

        bob_id = c_alice.get("/api/users/bob_chef3").get_json()["user"]["id"]
        alice_id = c_bob.get("/api/users/alice_chef3").get_json()["user"]["id"]

        # Alice sends request
        c_alice.post(f"/api/messages/{bob_id}", json={"message": "Can I get your sourdough starter ratio?"})

        # Bob accepts request
        accept_res = c_bob.post(f"/api/messages/requests/{alice_id}/accept")
        self.assertEqual(accept_res.status_code, 200)
        self.assertTrue(accept_res.get_json()["success"])

        # Verify they are now recognized as friends
        self.assertTrue(are_users_friends(alice_id, bob_id))

        # Bob replies freely
        bob_reply = c_bob.post(f"/api/messages/{alice_id}", json={"message": "Sure! I use 100% hydration."})
        self.assertEqual(bob_reply.status_code, 201)
        self.assertFalse(bob_reply.get_json()["is_request"])

        # Alice can now send ongoing messages freely without request blocker
        alice_reply = c_alice.post(f"/api/messages/{bob_id}", json={"message": "Awesome, thanks Chef!"})
        self.assertEqual(alice_reply.status_code, 201)
        self.assertFalse(alice_reply.get_json()["is_request"])

        # Check that thread is in primary for both
        a_convos = c_alice.get("/api/messages/conversations?tab=primary").get_json()
        self.assertTrue(any(c["partner"]["id"] == bob_id for c in a_convos["primary"]))

        b_convos = c_bob.get("/api/messages/conversations?tab=primary").get_json()
        self.assertTrue(any(c["partner"]["id"] == alice_id for c in b_convos["primary"]))

    def test_04_mutual_followers_are_friends_immediately(self):
        c_charlie = self.register_and_login("charlie_chef", "charlie@example.com")
        c_dana = self.register_and_login("dana_chef", "dana@example.com")

        dana_id = c_charlie.get("/api/users/dana_chef").get_json()["user"]["id"]
        charlie_id = c_dana.get("/api/users/charlie_chef").get_json()["user"]["id"]

        # Charlie follows Dana
        c_charlie.post(f"/api/users/{dana_id}/follow")
        # Dana follows Charlie (Mutual follows = Friends)
        c_dana.post(f"/api/users/{charlie_id}/follow")

        self.assertTrue(are_users_friends(charlie_id, dana_id))

        # Charlie messages Dana directly -> No request flow required
        msg_res = c_charlie.post(f"/api/messages/{dana_id}", json={"message": "Hey friend! Ready for service tonight?"})
        self.assertEqual(msg_res.status_code, 201)
        self.assertFalse(msg_res.get_json()["is_request"])

        # Check Dana's profile stats from Charlie's perspective
        prof = c_charlie.get("/api/users/dana_chef").get_json()
        self.assertTrue(prof["stats"]["is_friend"])

    def test_05_decline_message_request_cleans_up(self):
        c_edward = self.register_and_login("edward_chef", "edward@example.com")
        c_fiona = self.register_and_login("fiona_chef", "fiona@example.com")

        fiona_id = c_edward.get("/api/users/fiona_chef").get_json()["user"]["id"]
        edward_id = c_fiona.get("/api/users/edward_chef").get_json()["user"]["id"]

        # Edward sends request
        c_edward.post(f"/api/messages/{fiona_id}", json={"message": "Unsolicited message"})

        # Fiona declines request
        dec_res = c_fiona.post(f"/api/messages/requests/{edward_id}/decline")
        self.assertEqual(dec_res.status_code, 200)

        # Requests count for Fiona is now 0
        unread = c_fiona.get("/api/messages/unread-count").get_json()
        self.assertEqual(unread["unread_requests_count"], 0)

        # Direct message was removed
        thread = c_fiona.get(f"/api/messages/{edward_id}").get_json()
        self.assertEqual(len(thread["messages"]), 0)

    def test_06_blocked_user_cannot_send_requests_or_messages(self):
        c_gordon = self.register_and_login("gordon_chef", "gordon@example.com")
        c_helen = self.register_and_login("helen_chef", "helen@example.com")

        helen_id = c_gordon.get("/api/users/helen_chef").get_json()["user"]["id"]
        gordon_id = c_helen.get("/api/users/gordon_chef").get_json()["user"]["id"]

        # Helen blocks Gordon
        c_helen.post(f"/api/users/{gordon_id}/block")

        # Gordon attempts to send message request to Helen -> 403 Forbidden
        block_dm = c_gordon.post(f"/api/messages/{helen_id}", json={"message": "Hey Helen"})
        self.assertEqual(block_dm.status_code, 403)

if __name__ == "__main__":
    unittest.main()
