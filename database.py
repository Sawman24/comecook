import sqlite3
import os
import json
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get("COOKED_DB_PATH", os.path.join(os.path.dirname(__file__), "cooked.db"))

def get_db_connection():
    """Create a SQLite connection with foreign keys and WAL mode enabled."""
    db_path = os.environ.get("COOKED_DB_PATH", DB_PATH)
    parent_dir = os.path.dirname(os.path.abspath(db_path))
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db():
    """Initialize database schema with tables and indexes."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    -- 1. USERS TABLE
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL COLLATE NOCASE,
        email TEXT UNIQUE NOT NULL COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        avatar_url TEXT DEFAULT '',
        bio TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 2. SESSIONS TABLE
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );

    -- 3. LOGIN ATTEMPTS (For rate-limiting & brute force lockout)
    CREATE TABLE IF NOT EXISTS login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_address TEXT NOT NULL,
        username TEXT NOT NULL,
        attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        success INTEGER DEFAULT 0
    );

    -- 4. PASSWORD RESETS
    CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );

    -- 5. RECIPES TABLE
    CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        original_author_id INTEGER,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        prep_time_min INTEGER DEFAULT 0,
        cook_time_min INTEGER DEFAULT 0,
        servings INTEGER DEFAULT 4,
        difficulty TEXT DEFAULT 'Medium',
        cuisine TEXT DEFAULT 'Global',
        tags_json TEXT DEFAULT '[]',
        ingredients_json TEXT NOT NULL DEFAULT '[]',
        steps_json TEXT NOT NULL DEFAULT '[]',
        image_url TEXT DEFAULT '',
        source_url TEXT DEFAULT '',
        is_public INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (original_author_id) REFERENCES users (id) ON DELETE SET NULL
    );

    -- 6. SAVED RECIPES (Recipe Box bookmarks)
    CREATE TABLE IF NOT EXISTS saved_recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        recipe_id INTEGER NOT NULL,
        folder_name TEXT DEFAULT 'Favorites',
        notes TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE CASCADE,
        UNIQUE (user_id, recipe_id)
    );

    -- 7. KITCHEN STATIONS (Sub-Communities)
    CREATE TABLE IF NOT EXISTS stations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        slug TEXT NOT NULL UNIQUE,
        description TEXT NOT NULL,
        icon TEXT NOT NULL DEFAULT '🍳',
        banner_url TEXT DEFAULT '',
        rules_text TEXT DEFAULT '',
        member_count INTEGER DEFAULT 0,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
    );

    -- 8. STATION MEMBERS (Clocked In Chefs)
    CREATE TABLE IF NOT EXISTS station_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        station_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT DEFAULT 'chef', -- 'lead_cook', 'chef'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (station_id) REFERENCES stations (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        UNIQUE (station_id, user_id)
    );

    -- 9. COMMUNITY POSTS (Feed)
    CREATE TABLE IF NOT EXISTS community_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        image_url TEXT DEFAULT '',
        recipe_id INTEGER,
        station_id INTEGER,
        post_type TEXT DEFAULT 'post', -- 'post', 'question', 'showcase'
        report_count INTEGER DEFAULT 0,
        is_hidden INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE SET NULL,
        FOREIGN KEY (station_id) REFERENCES stations (id) ON DELETE SET NULL
    );

    -- 10. POST LIKES
    CREATE TABLE IF NOT EXISTS post_likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES community_posts (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        UNIQUE (post_id, user_id)
    );

    -- 11. POST COMMENTS (Supports nested replies)
    CREATE TABLE IF NOT EXISTS post_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        comment TEXT NOT NULL,
        parent_id INTEGER,
        reply_to_username TEXT DEFAULT '',
        is_hidden INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES community_posts (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (parent_id) REFERENCES post_comments (id) ON DELETE CASCADE
    );

    -- 12. POST & COMMENT REPORTS (Moderation)
    CREATE TABLE IF NOT EXISTS post_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER,
        comment_id INTEGER,
        reported_by INTEGER NOT NULL,
        reason TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES community_posts (id) ON DELETE CASCADE,
        FOREIGN KEY (comment_id) REFERENCES post_comments (id) ON DELETE CASCADE,
        FOREIGN KEY (reported_by) REFERENCES users (id) ON DELETE CASCADE
    );

    -- 13. FRIENDSHIPS / FOLLOWS
    CREATE TABLE IF NOT EXISTS friendships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        friend_id INTEGER NOT NULL,
        is_close_friend INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (friend_id) REFERENCES users (id) ON DELETE CASCADE,
        UNIQUE (user_id, friend_id)
    );

    -- 14. MEAL PLANNER
    CREATE TABLE IF NOT EXISTS planner (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        plan_date TEXT NOT NULL, -- YYYY-MM-DD
        meal_type TEXT NOT NULL, -- 'breakfast', 'lunch', 'dinner', 'snack'
        recipe_id INTEGER,
        custom_title TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (recipe_id) REFERENCES recipes (id) ON DELETE SET NULL
    );

    -- PERFORMANCE INDEXES
    CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);
    CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
    CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions (token);
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
    CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts (ip_address, attempt_time);
    CREATE INDEX IF NOT EXISTS idx_recipes_user ON recipes (user_id);
    CREATE INDEX IF NOT EXISTS idx_recipes_public ON recipes (is_public);
    CREATE INDEX IF NOT EXISTS idx_saved_recipes_user ON saved_recipes (user_id);
    CREATE INDEX IF NOT EXISTS idx_stations_slug ON stations (slug);
    CREATE INDEX IF NOT EXISTS idx_station_members_station ON station_members (station_id);
    CREATE INDEX IF NOT EXISTS idx_station_members_user ON station_members (user_id);
    CREATE INDEX IF NOT EXISTS idx_community_posts_created ON community_posts (created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_community_posts_user ON community_posts (user_id);
    CREATE INDEX IF NOT EXISTS idx_post_likes_post ON post_likes (post_id);
    CREATE INDEX IF NOT EXISTS idx_post_comments_post ON post_comments (post_id, created_at ASC);
    CREATE INDEX IF NOT EXISTS idx_friendships_user ON friendships (user_id);
    CREATE INDEX IF NOT EXISTS idx_planner_user_date ON planner (user_id, plan_date);
    """)

    # Dynamic migrations for existing databases
    try:
        cursor.execute("ALTER TABLE community_posts ADD COLUMN station_id INTEGER REFERENCES stations(id) ON DELETE SET NULL;")
    except Exception:
        pass

    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_community_posts_station ON community_posts (station_id);")
    except Exception:
        pass

    conn.commit()
    conn.close()

    # Ensure default stations exist
    seed_stations_if_empty()

def seed_stations_if_empty():
    """Seed the default culinary kitchen stations."""
    conn = get_db_connection()
    cursor = conn.cursor()

    default_stations = [
        (
            "Baking & Pastry Station",
            "baking-pastry",
            "Artisan sourdough, flaky laminated doughs, French pastries, sourdough starters, and dessert science.",
            "🥐",
            "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=1200&auto=format&fit=crop&q=80",
            "1. Always state flour type & hydration % when asking for crumb troubleshooting.\n2. Celebrate baking triumphs and flour dust.\n3. No commercial spam."
        ),
        (
            "Handmade Pasta Station",
            "pasta-craft",
            "Semolina shapes, sfoglina techniques, rolling pin mastery, extruded pasta, and regional Italian sauces.",
            "🍝",
            "https://images.unsplash.com/photo-1621996346565-e3d5d628169b?w=1200&auto=format&fit=crop&q=80",
            "1. Always reserve starchy pasta water for emulsions.\n2. State flour ratio (Tipo 00 vs Semola rimacinata).\n3. Respect regional traditions while welcoming experimentation."
        ),
        (
            "Smoke, Cast Iron & Grill",
            "smoke-castiron",
            "Hard sear techniques, cast iron seasoning, low-and-slow barbecue, smoking woods, and meat thermometer mastery.",
            "🥩",
            "https://images.unsplash.com/photo-1544025162-d76694265947?w=1200&auto=format&fit=crop&q=80",
            "1. Seasoning and rust restoration questions always welcome.\n2. Include internal target cook temps when showcasing cooks.\n3. Respect all barbecue regional styles."
        ),
        (
            "Plant-Based & Harvest",
            "plant-harvest",
            "Creative vegetarian & vegan gastronomy, seasonal harvest produce, umami extraction, and fermentation.",
            "🥗",
            "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=1200&auto=format&fit=crop&q=80",
            "1. Respectful and inspiring plant-based discussions.\n2. Focus on wholesome culinary techniques and flavor depth."
        ),
        (
            "Knife Skills & Technique",
            "prep-technique",
            "Mise en place, whetstone sharpening, classical French cuts (brunoise, julienne, chiffonade), pan sauces, and kitchen efficiency.",
            "🔪",
            "https://images.unsplash.com/photo-1556910103-1c02745aae4d?w=1200&auto=format&fit=crop&q=80",
            "1. Safety first: maintain proper pinch grip and claw guide.\n2. Constructive technique critiques only."
        ),
        (
            "30-Minute Weeknight Express",
            "30-min-express",
            "High-flavor, low-effort weeknight dinners, sheet-pan magic, pantry raids, and high-efficiency workflow cooking.",
            "⚡",
            "https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=1200&auto=format&fit=crop&q=80",
            "1. Total active prep + cook time should stay under 35 minutes.\n2. Keep dirty pans and cleanup minimal."
        ),
        (
            "Global Street Food & Bites",
            "global-streetfood",
            "Tacos, bao, satay, chaat, dumplings, empanadas, skewers, and vibrant street food traditions from across the globe.",
            "🌮",
            "https://images.unsplash.com/photo-1565299585323-38d6b0865b47?w=1200&auto=format&fit=crop&q=80",
            "1. Highlight culinary origin & cultural stories where possible.\n2. Street food fusions and regional variations welcome."
        )
    ]

    for name, slug, desc, icon, banner, rules in default_stations:
        cursor.execute("""
        INSERT INTO stations (name, slug, description, icon, banner_url, rules_text, member_count)
        VALUES (?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(slug) DO UPDATE SET
            description=excluded.description,
            icon=excluded.icon,
            banner_url=excluded.banner_url,
            rules_text=excluded.rules_text;
        """, (name, slug, desc, icon, banner, rules))

    # Auto-link existing posts to relevant stations if not linked
    cursor.execute("SELECT id FROM stations WHERE slug = 'pasta-craft';")
    pasta_station = cursor.fetchone()
    if pasta_station:
        cursor.execute("UPDATE community_posts SET station_id = ? WHERE station_id IS NULL AND (content LIKE '%cacio%' OR content LIKE '%pasta%' OR content LIKE '%carbonara%');", (pasta_station["id"],))

    cursor.execute("SELECT id FROM stations WHERE slug = 'baking-pastry';")
    baking_station = cursor.fetchone()
    if baking_station:
        cursor.execute("UPDATE community_posts SET station_id = ? WHERE station_id IS NULL AND (content LIKE '%sourdough%' OR content LIKE '%bread%' OR content LIKE '%pastry%');", (baking_station["id"],))

    cursor.execute("SELECT id FROM stations WHERE slug = 'smoke-castiron';")
    steak_station = cursor.fetchone()
    if steak_station:
        cursor.execute("UPDATE community_posts SET station_id = ? WHERE station_id IS NULL AND (content LIKE '%steak%' OR content LIKE '%cast iron%' OR content LIKE '%sear%');", (steak_station["id"],))

    # Seed initial memberships if users exist and memberships are empty
    cursor.execute("SELECT COUNT(*) AS count FROM station_members;")
    sm_count = cursor.fetchone()
    if sm_count and sm_count["count"] == 0:
        cursor.execute("SELECT id, username FROM users;")
        users = {u["username"]: u["id"] for u in cursor.fetchall()}
        cursor.execute("SELECT id, slug FROM stations;")
        stations_map = {s["slug"]: s["id"] for s in cursor.fetchall()}

        if "headchef" in users:
            for s_slug in ["smoke-castiron", "prep-technique", "30-min-express"]:
                if s_slug in stations_map:
                    cursor.execute("INSERT OR IGNORE INTO station_members (station_id, user_id, role) VALUES (?, ?, 'lead_cook');", (stations_map[s_slug], users["headchef"]))
        if "julia_bakes" in users:
            for s_slug in ["baking-pastry", "plant-harvest"]:
                if s_slug in stations_map:
                    role = "lead_cook" if s_slug == "baking-pastry" else "chef"
                    cursor.execute("INSERT OR IGNORE INTO station_members (station_id, user_id, role) VALUES (?, ?, ?);", (stations_map[s_slug], users["julia_bakes"], role))
        if "marco_pasta" in users:
            for s_slug in ["pasta-craft", "global-streetfood"]:
                if s_slug in stations_map:
                    role = "lead_cook" if s_slug == "pasta-craft" else "chef"
                    cursor.execute("INSERT OR IGNORE INTO station_members (station_id, user_id, role) VALUES (?, ?, ?);", (stations_map[s_slug], users["marco_pasta"], role))

    # Update member counts for all stations
    cursor.execute("""
    UPDATE stations SET member_count = (
        SELECT COUNT(*) FROM station_members WHERE station_members.station_id = stations.id
    );
    """)

    conn.commit()
    conn.close()

def seed_data_if_empty(force=False):
    """Seed initial starter users, recipes, community posts, and planner if DB is fresh and demo mode is enabled."""
    should_seed = force or os.environ.get("COOKED_SEED_DEMO", "0").lower() in ("1", "true", "yes")
    if not should_seed:
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS count FROM users;")
    row = cursor.fetchone()
    if row and row["count"] > 0:
        conn.close()
        return


    # Seed Admin User and demo chefs
    admin_hash = generate_password_hash("ChefPass123!")
    cursor.execute("""
    INSERT INTO users (username, email, password_hash, display_name, avatar_url, bio, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, ("headchef", "admin@cooked.community", admin_hash, "Chef Ramsey (Admin)", "https://images.unsplash.com/photo-1577219491135-ce391730fb2c?w=400&auto=format&fit=crop&q=80", "Executive Chef & Founder of Cooked. Dedicated to authentic flavors, sharp knives, and culinary craft.", 1))
    admin_id = cursor.lastrowid

    chef_julia_hash = generate_password_hash("ChefPass123!")
    cursor.execute("""
    INSERT INTO users (username, email, password_hash, display_name, avatar_url, bio, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, ("julia_bakes", "julia@cooked.community", chef_julia_hash, "Julia Pastry", "https://images.unsplash.com/photo-1583394293214-28ded15ee548?w=400&auto=format&fit=crop&q=80", "Artisan baker specializing in sourdough, laminated doughs, and French patisserie.", 0))
    julia_id = cursor.lastrowid

    chef_marco_hash = generate_password_hash("ChefPass123!")
    cursor.execute("""
    INSERT INTO users (username, email, password_hash, display_name, avatar_url, bio, is_admin)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, ("marco_pasta", "marco@cooked.community", chef_marco_hash, "Marco Rossi", "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&auto=format&fit=crop&q=80", "3rd generation Roman pasta maker. Simplicity and quality ingredients are everything.", 0))
    marco_id = cursor.lastrowid

    # Seed Friendships
    cursor.execute("INSERT INTO friendships (user_id, friend_id, is_close_friend) VALUES (?, ?, ?);", (admin_id, julia_id, 1))
    cursor.execute("INSERT INTO friendships (user_id, friend_id, is_close_friend) VALUES (?, ?, ?);", (admin_id, marco_id, 1))
    cursor.execute("INSERT INTO friendships (user_id, friend_id, is_close_friend) VALUES (?, ?, ?);", (julia_id, marco_id, 0))

    # Seed Recipes
    # 1. Cacio e Pepe
    cacio_ingredients = [
        {"name": "Spaghetti or Tonnarelli", "amount": "400", "unit": "g", "category": "Pantry"},
        {"name": "Pecorino Romano DOP (finely grated)", "amount": "200", "unit": "g", "category": "Dairy"},
        {"name": "Whole Black Peppercorns", "amount": "2", "unit": "tbsp", "category": "Spices"},
        {"name": "Coarse Sea Salt for pasta water", "amount": "1", "unit": "tbsp", "category": "Spices"}
    ]
    cacio_steps = [
        {"step_number": 1, "instruction": "Toast whole black peppercorns in a large skillet over medium heat for 2 minutes until fragrant. Crush coarsely with a mortar and pestle."},
        {"step_number": 2, "instruction": "Bring a large pot of water to a gentle boil with salt. Drop pasta and cook 2 minutes shy of al dente."},
        {"step_number": 3, "instruction": "In a heatproof bowl, combine grated Pecorino Romano with a ladle of starchy pasta water. Whisk vigorously to form a thick, silky cheese paste."},
        {"step_number": 4, "instruction": "Transfer pasta directly into the pepper skillet with a splash of pasta water. Toss over low heat for 1 minute."},
        {"step_number": 5, "instruction": "Remove skillet from heat, let cool for 30 seconds, then pour over the Pecorino paste. Toss rapidly until an emulsion coats every strand. Serve immediately!"}
    ]
    cursor.execute("""
    INSERT INTO recipes (user_id, title, description, prep_time_min, cook_time_min, servings, difficulty, cuisine, tags_json, ingredients_json, steps_json, image_url, is_public)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        marco_id,
        "Authentic Roman Cacio e Pepe",
        "The quintessential Roman pasta dish relying solely on starchy water, cracked pepper, and aged Pecorino Romano.",
        10, 15, 4, "Medium", "Italian",
        json.dumps(["Pasta", "Italian", "Classic", "Vegetarian", "QuickMeals"]),
        json.dumps(cacio_ingredients),
        json.dumps(cacio_steps),
        "https://images.unsplash.com/photo-1621996346565-e3d5d628169b?w=800&auto=format&fit=crop&q=80",
        1
    ))
    cacio_id = cursor.lastrowid

    # 2. Rustic Sourdough Boule
    sourdough_ingredients = [
        {"name": "Bread Flour (unbleached)", "amount": "500", "unit": "g", "category": "Pantry"},
        {"name": "Warm Water (78°F)", "amount": "375", "unit": "ml", "category": "Pantry"},
        {"name": "Active Sourdough Starter (100% hydration)", "amount": "100", "unit": "g", "category": "Bakery"},
        {"name": "Fine Sea Salt", "amount": "10", "unit": "g", "category": "Spices"}
    ]
    sourdough_steps = [
        {"step_number": 1, "instruction": "Mix flour and 350ml water for 30 minutes autolyse in a large glass bowl."},
        {"step_number": 2, "instruction": "Add active starter and remaining 25ml water with salt. Dimple and incorporate with wet hands."},
        {"step_number": 3, "instruction": "Perform 4 sets of stretch-and-folds spaced 30 minutes apart over a 2-hour bulk fermentation."},
        {"step_number": 4, "instruction": "Pre-shape into a tight round boule, rest 20 minutes, then final shape into a floured banneton basket."},
        {"step_number": 5, "instruction": "Cold ferment in the refrigerator for 14-16 hours."},
        {"step_number": 6, "instruction": "Bake inside a preheated Dutch Oven at 475°F (245°C) with lid on for 20 mins, then lid off at 450°F for 22 mins until deep mahogany crust forms."}
    ]
    cursor.execute("""
    INSERT INTO recipes (user_id, title, description, prep_time_min, cook_time_min, servings, difficulty, cuisine, tags_json, ingredients_json, steps_json, image_url, is_public)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        julia_id,
        "Artisan Sourdough Boule with Blistered Crust",
        "A deeply flavored, high-hydration open crumb artisan sourdough loaf with golden blistered ears.",
        120, 45, 8, "Advanced", "French / Artisan",
        json.dumps(["Baking", "Sourdough", "Bread", "Fermentation"]),
        json.dumps(sourdough_ingredients),
        json.dumps(sourdough_steps),
        "https://images.unsplash.com/photo-1589367920969-ab8e050bbb04?w=800&auto=format&fit=crop&q=80",
        1
    ))
    sourdough_id = cursor.lastrowid

    # 3. Pan-Seared Cast Iron Ribeye
    steak_ingredients = [
        {"name": "Prime Ribeye Steak (1.5 inch thick)", "amount": "2", "unit": "steaks", "category": "Meat"},
        {"name": "Coarse Kosher Salt", "amount": "1.5", "unit": "tbsp", "category": "Spices"},
        {"name": "Unsalted Butter", "amount": "3", "unit": "tbsp", "category": "Dairy"},
        {"name": "Fresh Rosemary Sprigs", "amount": "3", "unit": "sprigs", "category": "Produce"},
        {"name": "Fresh Thyme Sprigs", "amount": "4", "unit": "sprigs", "category": "Produce"},
        {"name": "Garlic Cloves (crushed)", "amount": "4", "unit": "cloves", "category": "Produce"}
    ]
    steak_steps = [
        {"step_number": 1, "instruction": "Dry brine ribeye with coarse salt on a wire rack in the fridge for 4-12 hours."},
        {"step_number": 2, "instruction": "Heat a heavy cast-iron skillet over high heat until smoking hot. Add 1 tbsp avocado oil."},
        {"step_number": 3, "instruction": "Sear steak for 2 minutes undisturbed, flip, and sear another 2 minutes for deep crust."},
        {"step_number": 4, "instruction": "Lower heat to medium-low, add butter, crushed garlic, rosemary, and thyme. Tilt skillet and continuously baste foaming butter over the steak for 2 minutes."},
        {"step_number": 5, "instruction": "Rest steak on a cutting board for 8 minutes before carving against the grain."}
    ]
    cursor.execute("""
    INSERT INTO recipes (user_id, title, description, prep_time_min, cook_time_min, servings, difficulty, cuisine, tags_json, ingredients_json, steps_json, image_url, is_public)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        admin_id,
        "Butter-Basted Cast Iron Prime Ribeye",
        "Restaurant quality dry-brined ribeye basted in foaming garlic-herb butter.",
        15, 10, 2, "Medium", "American",
        json.dumps(["Meat", "Dinner", "Steak", "Keto", "HighProtein"]),
        json.dumps(steak_ingredients),
        json.dumps(steak_steps),
        "https://images.unsplash.com/photo-1544025162-d76694265947?w=800&auto=format&fit=crop&q=80",
        1
    ))
    steak_id = cursor.lastrowid

    # Admin bookmarks Cacio e Pepe and Sourdough to recipe box
    cursor.execute("INSERT INTO saved_recipes (user_id, recipe_id, folder_name, notes) VALUES (?, ?, ?, ?);", (admin_id, cacio_id, "Favorites", "Best cacio technique ever!"));
    cursor.execute("INSERT INTO saved_recipes (user_id, recipe_id, folder_name, notes) VALUES (?, ?, ?, ?);", (admin_id, sourdough_id, "Weekend Bakes", "Try adding rye flour next time"));

    # Seed Community Posts
    # 1. Question Post
    cursor.execute("""
    INSERT INTO community_posts (user_id, content, post_type, recipe_id, image_url)
    VALUES (?, ?, ?, ?, ?);
    """, (
        marco_id,
        "Fellow cooks: What is your secret trick to prevent emulsion breaking when preparing carbonara or cacio e pepe? Let me know your heat control tricks!",
        "question",
        cacio_id,
        ""
    ))
    post1_id = cursor.lastrowid

    # Comments on Post 1
    cursor.execute("""
    INSERT INTO post_comments (post_id, user_id, comment, reply_to_username)
    VALUES (?, ?, ?, ?);
    """, (post1_id, admin_id, "Take the pan completely off the heat before adding the cheese slurry! Residual heat is plenty.", "marco_pasta"))
    c1_id = cursor.lastrowid

    cursor.execute("""
    INSERT INTO post_comments (post_id, user_id, comment, parent_id, reply_to_username)
    VALUES (?, ?, ?, ?, ?);
    """, (post1_id, julia_id, "Agreed! Also using finely microplaned cheese ensures it melts instantaneously without clumps.", c1_id, "headchef"))

    # 2. Dish Showcase Post
    cursor.execute("""
    INSERT INTO community_posts (user_id, content, post_type, recipe_id, image_url)
    VALUES (?, ?, ?, ?, ?);
    """, (
        julia_id,
        "Fresh out of the Dutch oven this morning! 75% hydration sourdough boule with a wild blistered ear. Recipe attached to my profile.",
        "showcase",
        sourdough_id,
        "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=800&auto=format&fit=crop&q=80"
    ))
    post2_id = cursor.lastrowid

    # Likes
    cursor.execute("INSERT INTO post_likes (post_id, user_id) VALUES (?, ?);", (post1_id, admin_id))
    cursor.execute("INSERT INTO post_likes (post_id, user_id) VALUES (?, ?);", (post1_id, julia_id))
    cursor.execute("INSERT INTO post_likes (post_id, user_id) VALUES (?, ?);", (post2_id, admin_id))
    cursor.execute("INSERT INTO post_likes (post_id, user_id) VALUES (?, ?);", (post2_id, marco_id))

    # 3. Post with Steak
    cursor.execute("""
    INSERT INTO community_posts (user_id, content, post_type, recipe_id, image_url)
    VALUES (?, ?, ?, ?, ?);
    """, (
        admin_id,
        "Sunday evening steak night. Cast iron skillet, rosemary, garlic butter baste. Keep your meat dry before searing for maximum Maillard reaction!",
        "post",
        steak_id,
        "https://images.unsplash.com/photo-1558030006-450675393462?w=800&auto=format&fit=crop&q=80"
    ))

    # Seed Meal Planner for Admin
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cursor.execute("""
    INSERT INTO planner (user_id, plan_date, meal_type, recipe_id, custom_title, notes)
    VALUES (?, ?, ?, ?, ?, ?);
    """, (admin_id, today_str, "dinner", steak_id, "Sunday Steak Night", "Dry brine morning of!"))

    conn.commit()
    conn.close()
