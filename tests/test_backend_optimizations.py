import os
import io
import json
import gzip
import tempfile
import unittest
from PIL import Image

temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
os.environ["COOKED_DB_PATH"] = temp_db_path
os.environ["ADMIN_USERNAMES"] = "optadmin,headchef"

from app import app, sanitize_fts_query
from database import init_db, seed_data_if_empty, get_db_connection

class BackendOptimizationsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()
        init_db()
        seed_data_if_empty(force=True)

    @classmethod
    def tearDownClass(cls):
        os.close(temp_db_fd)
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

    def test_01_gzip_compression_on_json_and_static(self):
        """Verify server compresses responses when Accept-Encoding: gzip is requested."""
        # Uncompressed request
        res_plain = self.client.get("/api/stations")
        self.assertEqual(res_plain.status_code, 200)
        self.assertNotIn("gzip", res_plain.headers.get("Content-Encoding", "").lower())

        # Gzip compressed request
        res_gzip = self.client.get("/api/stations", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(res_gzip.status_code, 200)
        self.assertIn("gzip", res_gzip.headers.get("Content-Encoding", "").lower())
        self.assertIn("Accept-Encoding", res_gzip.headers.get("Vary", ""))

        # Verify decompressed payload is valid JSON
        decompressed_data = gzip.decompress(res_gzip.data)
        parsed = json.loads(decompressed_data.decode("utf-8"))
        self.assertTrue(parsed.get("success"))
        self.assertTrue(len(parsed.get("stations", [])) > 0)

    def test_02_cache_control_headers(self):
        """Verify immutable caching for versioned static assets and no-cache for APIs."""
        # Dynamic API route
        api_res = self.client.get("/api/stations")
        self.assertIn("no-store", api_res.headers.get("Cache-Control", ""))

        # Versioned static asset
        static_res = self.client.get("/css/style.css?v=2.7.0")
        self.assertIn("immutable", static_res.headers.get("Cache-Control", ""))
        self.assertIn("max-age=31536000", static_res.headers.get("Cache-Control", ""))

    def test_03_fts5_sanitization_and_search(self):
        """Verify FTS5 query sanitization and full-text search across recipes and posts."""
        # Test sanitizer
        raw_query = 'sourdough + "baking" (pasta)* :test^'
        sanitized = sanitize_fts_query(raw_query)
        self.assertIn('"sourdough"*', sanitized)
        self.assertIn('"baking"*', sanitized)
        self.assertIn('"pasta"*', sanitized)

        # Execute search
        res = self.client.get("/api/search?q=sourdough")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("recipes", data)
        self.assertIn("posts", data)

    def test_04_keyset_cursor_pagination(self):
        """Verify keyset cursor pagination with before_id / cursor on recipes and posts."""
        # Recipes pagination
        res1 = self.client.get("/api/recipes?limit=2")
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertEqual(len(data1["recipes"]), 2)
        next_cursor = data1.get("next_cursor")
        self.assertIsNotNone(next_cursor)

        # Fetch next page using cursor
        res2 = self.client.get(f"/api/recipes?limit=2&before_id={next_cursor}")
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertTrue(len(data2["recipes"]) > 0)
        # Ensure all IDs on page 2 are strictly smaller than cursor
        for r in data2["recipes"]:
            self.assertLess(r["id"], next_cursor)

    def test_05_webp_image_upload_and_downsampling(self):
        """Verify image uploads are converted to WebP with Pillow."""
        # Login
        self.client.post("/api/auth/login", json={
            "username": "headchef",
            "password": "ChefPass123!"
        })

        # Generate sample PNG image
        img = Image.new("RGB", (1600, 1200), color=(100, 200, 150))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        res = self.client.post("/api/upload", data={
            "image": (buf, "recipe_dish.png")
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["filename"].endswith(".webp"))
        self.assertTrue(data["url"].endswith(".webp"))

if __name__ == "__main__":
    unittest.main()
