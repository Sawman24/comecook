import os
import secrets
import json
import re
import time
import threading
import gzip
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, g, send_from_directory, make_response
from PIL import Image
import io
from werkzeug.middleware.proxy_fix import ProxyFix

from html import escape as html_escape

from database import get_db_connection, init_db, seed_data_if_empty
from auth import (
    hash_password, verify_password, create_user_session,
    get_authenticated_user, delete_user_session, require_auth, admin_required,
    is_ip_rate_limited, record_login_attempt, SESSION_COOKIE_NAME, ADMIN_USERNAMES,
    validate_password_strength, invalidate_user_sessions, reset_auth_caches
)
from moderation_filter import contains_profanity, validate_clean_content
from scraper import scrape_recipe_from_url
from email_service import (
    send_password_reset_email, send_welcome_email, send_password_changed_email, get_smtp_config
)

# Setup App
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max payload
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# Support reverse proxy HTTPS headers (Nginx, Caddy, Cloudflare, Traefik)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(os.path.dirname(__file__), "uploads"))
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Database Schema and Default Stations
init_db()
seed_data_if_empty()

def sanitize_fts_query(query: str) -> str:
    """Sanitize user search query for SQLite FTS5 MATCH operator with tokenized prefix matching."""
    if not query:
        return ""
    cleaned = re.sub(r'[\"\*\:\^\{\}\(\)\[\]\+\-\~]', ' ', query)
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    if not tokens:
        return ""
    return " ".join(f'"{t}"*' for t in tokens)

def is_request_secure() -> bool:
    """Check if the current request is HTTPS or running over a secure transport."""
    return (
        request.is_secure or
        request.headers.get("X-Forwarded-Proto", "").lower() == "https" or
        os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes")
    )


def get_request_base_url() -> str:
    """Determine absolute base URL of the site."""
    env_url = os.environ.get("APP_URL", os.environ.get("BASE_URL", "")).strip().rstrip("/")
    if env_url:
        return env_url.replace("comecook.net", "comecook.app")

    if request:
        try:
            proto = "https" if is_request_secure() else "http"
            host = request.host
            if host:
                host = host.replace("comecook.net", "comecook.app")
                return f"{proto}://{host}"
        except Exception:
            pass
    return "https://comecook.app"


@app.after_request
def apply_security_and_performance_headers(response):
    """Enforce browser security headers, static asset caching, and dynamic Gzip compression."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    # 1. Performance Caching Policy
    if request.path.startswith("/css/") or request.path.startswith("/js/") or request.path.startswith("/uploads/"):
        if request.args.get("v") or request.path.startswith("/uploads/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=86400, must-revalidate"
    elif request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    elif request.path == "/" or request.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"

    if is_request_secure():
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    # 2. HTTP Gzip Compression (reduces wire payload sizes by 70-85%)
    accept_encoding = request.headers.get("Accept-Encoding", "").lower()
    if "gzip" in accept_encoding and response.status_code in (200, 201, 204) and not response.direct_passthrough:
        c_type = response.headers.get("Content-Type", "").lower()
        if any(t in c_type for t in ("application/json", "text/html", "text/css", "application/javascript", "text/javascript", "text/plain", "image/svg+xml")):
            data = response.get_data()
            if len(data) >= 500:
                compressed = gzip.compress(data, compresslevel=6)
                response.set_data(compressed)
                response.headers["Content-Encoding"] = "gzip"
                response.headers["Content-Length"] = len(compressed)
                response.headers["Vary"] = "Accept-Encoding"

    return response


# ==============================================================================
# NOTIFICATION HELPER ENGINE
# ==============================================================================

def create_notification(user_id: int, actor_id: int, notif_type: str, entity_type: str, entity_id: int, message: str, conn=None):
    """Insert in-app notification if actor is not the recipient."""
    if not user_id or not actor_id or user_id == actor_id:
        return
    close_conn = False
    try:
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notifications (user_id, actor_id, type, entity_type, entity_id, message)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (user_id, actor_id, notif_type, entity_type, entity_id, message))
        if close_conn:
            conn.commit()
            conn.close()
    except Exception as e:
        app.logger.warning(f"Failed to create notification: {e}")


def is_user_blocked(user1_id: int, user2_id: int, conn=None) -> bool:
    """Check if either user has blocked the other."""
    if not user1_id or not user2_id or user1_id == user2_id:
        return False
    close_conn = False
    try:
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM user_blocks
            WHERE (user_id = ? AND blocked_user_id = ?)
               OR (user_id = ? AND blocked_user_id = ?);
        """, (user1_id, user2_id, user2_id, user1_id))
        blocked = bool(cursor.fetchone())
        if close_conn:
            conn.close()
        return blocked
    except Exception as e:
        app.logger.warning(f"Error checking user block: {e}")
        if close_conn:
            conn.close()
        return False


def are_users_friends(user1_id: int, user2_id: int, conn=None) -> bool:
    """
    Two users are considered 'Friends' if:
    1. They are mutual followers in `friendships` (user1 follows user2 AND user2 follows user1), OR
    2. An explicit message request between them has been accepted in `message_requests`.
    """
    if not user1_id or not user2_id or user1_id == user2_id:
        return False
    close_conn = False
    try:
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        cursor = conn.cursor()

        # 1. Check mutual following
        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM friendships
            WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?);
        """, (user1_id, user2_id, user2_id, user1_id))
        if cursor.fetchone()["count"] >= 2:
            return True

        # 2. Check accepted message request
        cursor.execute("""
            SELECT id FROM message_requests
            WHERE ((sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?))
              AND status = 'accepted';
        """, (user1_id, user2_id, user2_id, user1_id))
        if cursor.fetchone():
            return True

        return False
    except Exception as e:
        app.logger.warning(f"Error checking are_users_friends: {e}")
        return False
    finally:
        if close_conn and conn:
            conn.close()


def get_message_request_info(user1_id: int, user2_id: int, conn=None) -> dict:
    """
    Get message request status and details between user1 and user2.
    """
    default_info = {
        "has_request": False,
        "id": None,
        "status": "none",
        "sender_id": None,
        "recipient_id": None,
        "is_sender": False,
        "is_recipient": False
    }
    if not user1_id or not user2_id or user1_id == user2_id:
        return default_info
    close_conn = False
    try:
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, sender_id, recipient_id, status
            FROM message_requests
            WHERE (sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?);
        """, (user1_id, user2_id, user2_id, user1_id))
        row = cursor.fetchone()
        if not row:
            return default_info

        status = row["status"]
        s_id = row["sender_id"]
        r_id = row["recipient_id"]
        return {
            "has_request": True,
            "id": row["id"],
            "status": status,
            "sender_id": s_id,
            "recipient_id": r_id,
            "is_sender": (user1_id == s_id),
            "is_recipient": (user1_id == r_id)
        }
    except Exception as e:
        app.logger.warning(f"Error getting message request info: {e}")
        return default_info
    finally:
        if close_conn and conn:
            conn.close()


def parse_and_notify_mentions(text: str, actor_id: int, entity_type: str, entity_id: int, message_template: str, conn=None):
    """Extract @username mentions from text and dispatch in-app notifications."""
    if not text:
        return
    usernames = set(re.findall(r'@([a-zA-Z0-9_]{3,30})', text))
    if not usernames:
        return

    close_conn = False
    try:
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        cursor = conn.cursor()

        for uname in usernames:
            cursor.execute("SELECT id FROM users WHERE username = ? AND is_active = 1;", (uname,))
            target = cursor.fetchone()
            if target and target["id"] != actor_id:
                # Ensure no blocking relationship exists
                cursor.execute("""
                    SELECT id FROM user_blocks
                    WHERE (user_id = ? AND blocked_user_id = ?)
                       OR (user_id = ? AND blocked_user_id = ?);
                """, (target["id"], actor_id, actor_id, target["id"]))
                if not cursor.fetchone():
                    create_notification(
                        user_id=target["id"],
                        actor_id=actor_id,
                        notif_type="mention",
                        entity_type=entity_type,
                        entity_id=entity_id,
                        message=message_template,
                        conn=conn
                    )
        if conn:
            conn.commit()
        if close_conn:
            conn.close()
    except Exception as e:
        app.logger.warning(f"Failed to parse and notify mentions: {e}")
        if close_conn:
            conn.close()


# Thread-safe in-memory cache for high-frequency public listings (2s TTL)
class MicroCache:
    def __init__(self, ttl_sec=2.0):
        self.ttl = ttl_sec
        self.cache = {}
        self.lock = threading.Lock()

    def get(self, key):
        now = time.time()
        with self.lock:
            item = self.cache.get(key)
            if item and item[1] > now:
                return item[0]
        return None

    def set(self, key, value):
        now = time.time()
        with self.lock:
            self.cache[key] = (value, now + self.ttl)

    def invalidate(self, prefix=None):
        with self.lock:
            if prefix:
                keys = [k for k in list(self.cache.keys()) if k.startswith(prefix)]
                for k in keys:
                    self.cache.pop(k, None)
            else:
                self.cache.clear()

_FEED_CACHE = MicroCache(ttl_sec=2.0)

# Thread-safe in-memory cache for user culinary badges (60s TTL)
_BADGE_CACHE = {}  # user_id -> (badges_list, expire_timestamp)
_BADGE_CACHE_LOCK = threading.Lock()
_BADGE_CACHE_TTL = 60.0

def compute_user_badges(user_id: int, conn=None) -> list:
    """Compute and return dynamic culinary achievement badges for a user with memory caching."""
    now = time.time()
    with _BADGE_CACHE_LOCK:
        cached = _BADGE_CACHE.get(user_id)
        if cached and cached[1] > now:
            return list(cached[0])

    badges = []
    close_conn = False
    try:
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        cursor = conn.cursor()

        cursor.execute("SELECT id, username, is_admin, is_verified, created_at FROM users WHERE id = ?;", (user_id,))
        u = cursor.fetchone()
        if not u:
            if close_conn:
                conn.close()
            return badges

        if u["is_admin"] == 1:
            badges.append({
                "id": "admin",
                "name": "Executive Chef",
                "icon": "👑",
                "description": "Cooked Platform Founder & Head Moderator",
                "tier": "legendary"
            })

        if u["is_verified"] == 1:
            badges.append({
                "id": "verified",
                "name": "Verified Chef",
                "icon": "⭐",
                "description": "Verified Culinary Professional & Creator",
                "tier": "gold"
            })

        # Recipes count & stats
        cursor.execute("SELECT COUNT(*) AS count FROM recipes WHERE user_id = ? AND is_public = 1;", (user_id,))
        rec_count = cursor.fetchone()["count"]

        if rec_count >= 10:
            badges.append({
                "id": "master_author",
                "name": "Master Author",
                "icon": "📚",
                "description": "Published 10+ public recipes in the Recipe Box",
                "tier": "gold"
            })
        elif rec_count >= 3:
            badges.append({
                "id": "sous_chef",
                "name": "Sous Chef",
                "icon": "👨‍🍳",
                "description": "Active creator with 3+ published recipes",
                "tier": "silver"
            })

        # Remake reviews & average rating
        cursor.execute("""
            SELECT COUNT(rv.id) AS review_count, AVG(rv.rating) AS avg_rating
            FROM recipe_reviews rv
            JOIN recipes r ON rv.recipe_id = r.id
            WHERE r.user_id = ?;
        """, (user_id,))
        rev_row = cursor.fetchone()
        if rev_row and rev_row["review_count"] and rev_row["review_count"] >= 2 and (rev_row["avg_rating"] or 0) >= 4.5:
            badges.append({
                "id": "top_rated",
                "name": "Top Rated Author",
                "icon": "🌟",
                "description": f"Maintains a {rev_row['avg_rating']:.1f}★ rating across recipe remakes",
                "tier": "gold"
            })

        # Specialized Station Leadership
        cursor.execute("""
            SELECT s.slug, s.name, sm.role
            FROM station_members sm
            JOIN stations s ON sm.station_id = s.id
            WHERE sm.user_id = ? AND sm.role = 'lead_cook';
        """, (user_id,))
        lead_stations = cursor.fetchall()
        for ls in lead_stations:
            first_word = ls["name"].split()[0] if ls["name"] else "Station"
            badges.append({
                "id": f"lead_{ls['slug']}",
                "name": f"Lead Cook ({first_word})",
                "icon": "🥇",
                "description": f"Lead Cook brigade leader in {ls['name']}",
                "tier": "legendary"
            })

        # Culinary specialties from tags & cuisine
        cursor.execute("""
            SELECT COUNT(*) AS count FROM recipes
            WHERE user_id = ? AND (tags_json LIKE '%Sourdough%' OR tags_json LIKE '%Baking%' OR tags_json LIKE '%Bread%');
        """, (user_id,))
        if cursor.fetchone()["count"] >= 2:
            badges.append({
                "id": "sourdough_master",
                "name": "Sourdough Specialist",
                "icon": "🥖",
                "description": "Mastery of fermentation, high hydration doughs, and crumb craft",
                "tier": "silver"
            })

        cursor.execute("""
            SELECT COUNT(*) AS count FROM recipes
            WHERE user_id = ? AND (tags_json LIKE '%Pasta%' OR cuisine LIKE '%Italian%');
        """, (user_id,))
        if cursor.fetchone()["count"] >= 2:
            badges.append({
                "id": "pasta_artisan",
                "name": "Pasta Artisan",
                "icon": "🍝",
                "description": "Crafts handmade pasta shapes and traditional emulsions",
                "tier": "silver"
            })

        cursor.execute("""
            SELECT COUNT(*) AS count FROM recipes
            WHERE user_id = ? AND (tags_json LIKE '%Steak%' OR tags_json LIKE '%Meat%' OR tags_json LIKE '%Grill%');
        """, (user_id,))
        if cursor.fetchone()["count"] >= 2:
            badges.append({
                "id": "cast_iron_master",
                "name": "Cast Iron Master",
                "icon": "🥩",
                "description": "Expert in high-heat searing, cast iron basting, and meat cookery",
                "tier": "silver"
            })

        if close_conn:
            conn.close()
    except Exception as e:
        app.logger.warning(f"Error computing user badges: {e}")
        if close_conn:
            conn.close()

    with _BADGE_CACHE_LOCK:
        _BADGE_CACHE[user_id] = (badges, now + _BADGE_CACHE_TTL)
    return badges


def enrich_posts_batch(posts: list, current_user: dict, conn) -> list:
    """Enrich a list of posts with badges, reactions, user reactions/likes, and polls using fast batch queries."""
    if not posts:
        return posts

    cursor = conn.cursor()
    post_ids = [p["id"] for p in posts]
    placeholders = ",".join(["?"] * len(post_ids))

    # 1. Author badges (cached in memory)
    for p in posts:
        p["author_badges"] = compute_user_badges(p["user_id"], conn=conn)

    # 2. Batch reactions summary
    cursor.execute(f"""
        SELECT post_id, reaction, COUNT(*) AS count
        FROM post_reactions
        WHERE post_id IN ({placeholders})
        GROUP BY post_id, reaction;
    """, post_ids)

    reactions_by_post = {pid: {"heart": 0, "chef_kiss": 0, "fire": 0, "drool": 0, "genius": 0} for pid in post_ids}
    total_rx_by_post = {pid: 0 for pid in post_ids}
    for rx in cursor.fetchall():
        pid = rx["post_id"]
        rname = rx["reaction"]
        if pid in reactions_by_post and rname in reactions_by_post[pid]:
            reactions_by_post[pid][rname] = rx["count"]
            total_rx_by_post[pid] += rx["count"]

    # 3. Batch user reactions & likes
    user_reactions_by_post = {}
    user_likes_by_post = set()
    if current_user:
        cursor.execute(f"""
            SELECT post_id, reaction
            FROM post_reactions
            WHERE post_id IN ({placeholders}) AND user_id = ?;
        """, post_ids + [current_user["id"]])
        for row in cursor.fetchall():
            user_reactions_by_post[row["post_id"]] = row["reaction"]

        cursor.execute(f"""
            SELECT post_id
            FROM post_likes
            WHERE post_id IN ({placeholders}) AND user_id = ?;
        """, post_ids + [current_user["id"]])
        for row in cursor.fetchall():
            user_likes_by_post.add(row["post_id"])

    # 4. Batch Polls
    cursor.execute(f"""
        SELECT id, post_id, question, options_json
        FROM post_polls
        WHERE post_id IN ({placeholders});
    """, post_ids)
    poll_rows = cursor.fetchall()
    polls_by_post = {}
    if poll_rows:
        poll_ids = [pr["id"] for pr in poll_rows]
        poll_placeholders = ",".join(["?"] * len(poll_ids))

        cursor.execute(f"""
            SELECT poll_id, option_index, COUNT(*) AS count
            FROM poll_votes
            WHERE poll_id IN ({poll_placeholders})
            GROUP BY poll_id, option_index;
        """, poll_ids)
        votes_by_poll = {}
        for vr in cursor.fetchall():
            p_id = vr["poll_id"]
            if p_id not in votes_by_poll:
                votes_by_poll[p_id] = {}
            votes_by_poll[p_id][vr["option_index"]] = vr["count"]

        user_votes_by_poll = {}
        if current_user:
            cursor.execute(f"""
                SELECT poll_id, option_index
                FROM poll_votes
                WHERE poll_id IN ({poll_placeholders}) AND user_id = ?;
            """, poll_ids + [current_user["id"]])
            for uv in cursor.fetchall():
                user_votes_by_poll[uv["poll_id"]] = uv["option_index"]

        for pr in poll_rows:
            try:
                options_list = json.loads(pr["options_json"] or "[]")
            except Exception:
                options_list = []

            p_votes = votes_by_poll.get(pr["id"], {})
            total_votes = sum(p_votes.values())
            options_data = []
            for idx, opt_text in enumerate(options_list):
                votes = p_votes.get(idx, 0)
                pct = round((votes / total_votes * 100)) if total_votes > 0 else 0
                options_data.append({
                    "index": idx,
                    "text": opt_text,
                    "votes": votes,
                    "percent": pct
                })

            polls_by_post[pr["post_id"]] = {
                "id": pr["id"],
                "question": pr["question"],
                "options": options_data,
                "total_votes": total_votes,
                "user_voted_index": user_votes_by_poll.get(pr["id"])
            }

    # Attach enriched fields
    for p in posts:
        pid = p["id"]
        p["reactions"] = {
            "counts": reactions_by_post.get(pid, {"heart": 0, "chef_kiss": 0, "fire": 0, "drool": 0, "genius": 0}),
            "total": total_rx_by_post.get(pid, 0),
            "user_reaction": user_reactions_by_post.get(pid)
        }
        p["is_liked"] = (pid in user_likes_by_post)
        p["poll"] = polls_by_post.get(pid)

    return posts


# ==============================================================================
# HASHTAG EXTRACTION & INDEXING HELPERS
# ==============================================================================

def extract_hashtags(text: str) -> list[str]:
    """Extract unique lowercase hashtags (#sourdough, #baking_tips) from text."""
    if not text:
        return []
    raw_tags = re.findall(r'#([a-zA-Z0-9_]{2,40})', str(text))
    unique_tags = []
    seen = set()
    for tag in raw_tags:
        cleaned = tag.strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique_tags.append(cleaned)
    return unique_tags


def sync_entity_hashtags(cursor, entity_type: str, entity_id: int, tags: list[str]):
    """Sync hashtags and update usage counts in database."""
    try:
        # Collect previous tags to update counts later
        cursor.execute("SELECT hashtag_id FROM hashtag_references WHERE entity_type = ? AND entity_id = ?;", (entity_type, entity_id))
        old_hashtag_ids = [row["hashtag_id"] for row in cursor.fetchall()]

        cursor.execute("DELETE FROM hashtag_references WHERE entity_type = ? AND entity_id = ?;", (entity_type, entity_id))

        all_affected = set(old_hashtag_ids)
        for tag in tags:
            tag_clean = tag.strip().lower().lstrip("#")
            if not tag_clean or len(tag_clean) < 2:
                continue
            cursor.execute("INSERT OR IGNORE INTO hashtags (tag, usage_count) VALUES (?, 0);", (tag_clean,))
            cursor.execute("SELECT id FROM hashtags WHERE tag = ?;", (tag_clean,))
            tag_row = cursor.fetchone()
            if tag_row:
                h_id = tag_row["id"]
                all_affected.add(h_id)
                cursor.execute("""
                    INSERT OR IGNORE INTO hashtag_references (hashtag_id, entity_type, entity_id)
                    VALUES (?, ?, ?);
                """, (h_id, entity_type, entity_id))

        # Recalculate usage_count for affected hashtags
        for h_id in all_affected:
            cursor.execute("SELECT COUNT(*) AS cnt FROM hashtag_references WHERE hashtag_id = ?;", (h_id,))
            res = cursor.fetchone()
            cnt = res["cnt"] if res else 0
            cursor.execute("UPDATE hashtags SET usage_count = ? WHERE id = ?;", (cnt, h_id))
    except Exception as e:
        app.logger.warning(f"Error syncing hashtags for {entity_type} {entity_id}: {e}")
# HEALTHCHECK & SYSTEM STATUS
# ==============================================================================

@app.route("/api/health", methods=["GET"])
def health_check():
    """Service healthcheck endpoint for Docker, Kubernetes, and reverse proxies."""
    return jsonify({
        "status": "healthy",
        "service": "cooked",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


# ==============================================================================
# STATIC & RICH SOCIAL SHARING PREVIEWS (OpenGraph & Twitter Cards)
# ==============================================================================

def render_page_with_meta(og_title=None, og_desc=None, og_img=None, og_url=None):
    """Dynamically inject OpenGraph and Twitter card metadata into index.html."""
    default_title = "Cooked — Made for Cooks, By Cooks"
    default_desc = "The premier social culinary platform and digital recipe box. Ask cooking questions, share dish photos, import recipes, plan meals, and manage your kitchen pantry."
    default_img = "https://images.unsplash.com/photo-1556910103-1c02745aae4d?w=1200&auto=format&fit=crop&q=80"

    title = og_title or default_title
    desc = og_desc or default_desc
    img = og_img or default_img
    url = og_url or request.base_url

    # Normalize relative images to absolute URLs
    if img and img.startswith("/"):
        img = request.host_url.rstrip("/") + img

    index_path = os.path.join(app.static_folder, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    meta_tags = f"""  <title>{html_escape(title)}</title>
  <meta name="description" content="{html_escape(desc)}" />
  <!-- OpenGraph Social Sharing -->
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Cooked" />
  <meta property="og:title" content="{html_escape(title)}" />
  <meta property="og:description" content="{html_escape(desc)}" />
  <meta property="og:image" content="{html_escape(img)}" />
  <meta property="og:url" content="{html_escape(url)}" />
  <!-- Twitter Card Sharing -->
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{html_escape(title)}" />
  <meta name="twitter:description" content="{html_escape(desc)}" />
  <meta name="twitter:image" content="{html_escape(img)}" />"""

    pattern = r"<title>.*?</title>\s*<meta name=\"description\" content=\".*?\" />"
    if re.search(pattern, html_content, flags=re.DOTALL):
        html_content = re.sub(pattern, meta_tags, html_content, flags=re.DOTALL)
    else:
        html_content = html_content.replace("<head>", f"<head>\n{meta_tags}")

    response = make_response(html_content, 200)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response

@app.route("/")
def index():
    return render_page_with_meta()

@app.route("/recipes/<int:recipe_id>")
def recipe_share_page(recipe_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, r.title, r.description, r.prep_time_min, r.cook_time_min, r.image_url,
               u.username, u.display_name
        FROM recipes r
        JOIN users u ON r.user_id = u.id
        WHERE r.id = ? AND r.is_public = 1;
    """, (recipe_id,))
    recipe = cursor.fetchone()
    conn.close()

    if recipe:
        title = f"{recipe['title']} — by @{recipe['username']} on Cooked"
        total_time = (recipe['prep_time_min'] or 0) + (recipe['cook_time_min'] or 0)
        time_str = f" • Ready in {total_time} mins" if total_time else ""
        desc = (recipe['description'] or f"Check out this recipe for {recipe['title']} by {recipe['display_name']} on Cooked!") + time_str
        return render_page_with_meta(
            og_title=title,
            og_desc=desc,
            og_img=recipe['image_url'],
            og_url=f"https://comecook.app/recipes/{recipe_id}"
        )
    return render_page_with_meta()

@app.route("/posts/<int:post_id>")
def post_share_page(post_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.content, p.image_url, u.username, u.display_name
        FROM community_posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.id = ? AND p.is_hidden = 0;
    """, (post_id,))
    post = cursor.fetchone()
    conn.close()

    if post:
        title = f"Culinary Post by @{post['username']} on Cooked"
        desc = post['content'][:200] if post['content'] else "Check out this dish on Cooked!"
        return render_page_with_meta(
            og_title=title,
            og_desc=desc,
            og_img=post['image_url'],
            og_url=f"https://comecook.app/posts/{post_id}"
        )
    return render_page_with_meta()

@app.route("/chefs/<username>")
def chef_share_page(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.display_name, u.avatar_url, u.bio,
               (SELECT COUNT(*) FROM recipes r WHERE r.user_id = u.id AND r.is_public = 1) AS recipe_count
        FROM users u
        WHERE u.username = ? AND u.is_active = 1;
    """, (username,))
    user = cursor.fetchone()
    conn.close()

    if user:
        title = f"{user['display_name']} (@{user['username']}) on Cooked"
        desc = user['bio'] or f"Explore {user['recipe_count']} recipes and culinary creations from Chef @{user['username']} on Cooked."
        return render_page_with_meta(
            og_title=title,
            og_desc=desc,
            og_img=user['avatar_url'],
            og_url=f"https://comecook.app/chefs/{username}"
        )
    return render_page_with_meta()

@app.route("/stations/<slug>")
def station_share_page(slug):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, slug, description, icon, banner_url, member_count
        FROM stations
        WHERE slug = ?;
    """, (slug,))
    station = cursor.fetchone()
    conn.close()

    if station:
        title = f"{station['icon']} {station['name']} Kitchen Station on Cooked"
        desc = f"{station['description']} • {station['member_count']} chefs clocked in."
        return render_page_with_meta(
            og_title=title,
            og_desc=desc,
            og_img=station['banner_url'],
            og_url=f"https://comecook.app/stations/{slug}"
        )
    return render_page_with_meta()

@app.route("/uploads/<path:filename>")
@app.route("/api/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)




# ==============================================================================
# AUTHENTICATION ENDPOINTS
# ==============================================================================

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or username).strip()
    avatar_url = (data.get("avatar_url") or "").strip()
    bio = (data.get("bio") or "").strip()

    if not username or len(username) < 3:
        return jsonify({"error": "Validation Error", "message": "Username must be at least 3 characters"}), 400
    if len(username) > 30:
        return jsonify({"error": "Validation Error", "message": "Username must be 30 characters or fewer"}), 400
    if not email or "@" not in email:
        return jsonify({"error": "Validation Error", "message": "Valid email address is required"}), 400

    # Content Moderation: Profanity & Slur Filter on User Profile
    is_clean, err_msg = validate_clean_content(username, "Username")
    if not is_clean:
        return jsonify({"error": "Validation Error", "message": err_msg}), 400

    is_clean, err_msg = validate_clean_content(display_name, "Display Name")
    if not is_clean:
        return jsonify({"error": "Validation Error", "message": err_msg}), 400

    if bio:
        is_clean, err_msg = validate_clean_content(bio, "Culinary Bio")
        if not is_clean:
            return jsonify({"error": "Validation Error", "message": err_msg}), 400

    # Strong Password Policy Verification
    is_valid_pw, pw_err = validate_password_strength(password)
    if not is_valid_pw:
        return jsonify({"error": "Validation Error", "message": pw_err}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check for existing username or email
    cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?;", (username, email))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "Conflict", "message": "Username or email is already registered"}), 409

    # Security Mitigation: Registration Injection Immunity
    # Client-supplied is_admin is explicitly ignored.
    # Admin is granted ONLY if table is empty (first bootstrapping user) or username matches ADMIN_USERNAMES.
    cursor.execute("SELECT COUNT(*) AS count FROM users;")
    user_count = cursor.fetchone()["count"]
    is_admin = 1 if (user_count == 0 or username.lower() in ADMIN_USERNAMES) else 0

    pw_hash = hash_password(password)
    cursor.execute("""
        INSERT INTO users (username, email, password_hash, display_name, avatar_url, bio, is_admin)
        VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (username, email, pw_hash, display_name, avatar_url, bio, is_admin))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Dispatch welcome email asynchronously
    try:
        base_url = get_request_base_url()
        send_welcome_email(email, username, display_name, base_url=base_url)
    except Exception as e:
        app.logger.warning(f"Failed to dispatch welcome email: {e}")

    # Create session token and set HttpOnly cookie
    token = create_user_session(user_id)
    response = make_response(jsonify({
        "success": True,
        "message": "Account registered successfully",
        "user": {
            "id": user_id,
            "username": username,
            "email": email,
            "display_name": display_name,
            "avatar_url": avatar_url,
            "bio": bio,
            "is_admin": is_admin
        },
        "token": token
    }), 201)

    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=14 * 86400,
        httponly=True,
        samesite="Lax",
        secure=is_request_secure()
    )
    return response

@app.route("/api/auth/login", methods=["POST"])
def login():
    ip = request.remote_addr or "127.0.0.1"

    # Security Mitigation: Rate-Limiting & Brute Force Lockout
    if is_ip_rate_limited(ip):
        return jsonify({
            "error": "Rate Limited",
            "message": "Too many failed login attempts. Please try again after 5 minutes."
        }), 429

    data = request.get_json() or {}
    username_or_email = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username_or_email or not password:
        return jsonify({"error": "Validation Error", "message": "Username/email and password required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, email, password_hash, display_name, avatar_url, bio, is_active, is_admin
        FROM users
        WHERE username = ? OR email = ?;
    """, (username_or_email, username_or_email.lower()))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(password, user["password_hash"]):
        record_login_attempt(ip, username_or_email, success=False)
        return jsonify({"error": "Unauthorized", "message": "Invalid username or password"}), 401

    if user["is_active"] != 1:
        return jsonify({"error": "Forbidden", "message": "Account has been deactivated"}), 403

    record_login_attempt(ip, username_or_email, success=True)
    token = create_user_session(user["id"])

    response = make_response(jsonify({
        "success": True,
        "message": "Logged in successfully",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "display_name": user["display_name"],
            "avatar_url": user["avatar_url"],
            "bio": user["bio"],
            "is_admin": user["is_admin"]
        },
        "token": token
    }))

    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=14 * 86400,
        httponly=True,
        samesite="Lax",
        secure=is_request_secure()
    )
    return response

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    user = get_authenticated_user()
    if user and "token" in user:
        delete_user_session(user["token"])

    response = make_response(jsonify({"success": True, "message": "Logged out"}))
    response.set_cookie(SESSION_COOKIE_NAME, "", expires=0, httponly=True, samesite="Lax", secure=is_request_secure())
    return response

@app.route("/api/auth/me", methods=["GET"])
def get_me():
    user = get_authenticated_user()
    if not user:
        return jsonify({"user": None}), 200
    return jsonify({"user": user}), 200

@app.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()

    if not email or "@" not in email:
        return jsonify({"error": "Validation Error", "message": "A valid email address is required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email FROM users WHERE email = ? AND is_active = 1;", (email,))
    user = cursor.fetchone()

    if user:
        # Generate 256-bit cryptographically secure token
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

        # Invalidate old unused tokens for this user
        cursor.execute("UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0;", (user["id"],))

        cursor.execute("""
            INSERT INTO password_resets (user_id, token, expires_at, used)
            VALUES (?, ?, ?, 0);
        """, (user["id"], token, expires_at))
        conn.commit()

        # Dispatch reset email asynchronously
        try:
            base_url = get_request_base_url()
            send_password_reset_email(user["email"], user["username"], token, base_url=base_url)
        except Exception as e:
            app.logger.warning(f"Error dispatching reset email: {e}")

    conn.close()

    # Anti-enumeration response: always return generic success message
    return jsonify({
        "success": True,
        "message": "If an account exists with that email address, a password reset link has been sent. Please check your inbox and spam folder."
    }), 200

@app.route("/api/auth/verify-reset-token", methods=["POST"])
def verify_reset_token():
    data = request.get_json() or {}
    token = (data.get("token") or "").strip()

    if not token:
        return jsonify({"valid": False, "message": "Token is required."}), 400

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pr.id, pr.user_id, u.username
        FROM password_resets pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.token = ? AND pr.expires_at > ? AND pr.used = 0 AND u.is_active = 1;
    """, (token, now_str))
    entry = cursor.fetchone()
    conn.close()

    if not entry:
        return jsonify({"valid": False, "message": "Password reset link is invalid or has expired."}), 400

    return jsonify({
        "valid": True,
        "username": entry["username"],
        "message": "Token is valid."
    }), 200

@app.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json() or {}
    token = (data.get("token") or "").strip()
    new_password = data.get("new_password") or ""

    if not token:
        return jsonify({"error": "Validation Error", "message": "Reset token is required."}), 400

    is_valid_pw, pw_err = validate_password_strength(new_password)
    if not is_valid_pw:
        return jsonify({"error": "Validation Error", "message": pw_err}), 400

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pr.id, pr.user_id, u.username, u.email
        FROM password_resets pr
        JOIN users u ON pr.user_id = u.id
        WHERE pr.token = ? AND pr.expires_at > ? AND pr.used = 0 AND u.is_active = 1;
    """, (token, now_str))
    reset_entry = cursor.fetchone()

    if not reset_entry:
        conn.close()
        return jsonify({"error": "Invalid Token", "message": "Password reset link is invalid or has expired. Please request a new one."}), 400

    user_id = reset_entry["user_id"]
    pw_hash = hash_password(new_password)

    # 1. Update password hash
    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?;", (pw_hash, user_id))

    # 2. Mark token as used
    cursor.execute("UPDATE password_resets SET used = 1 WHERE id = ?;", (reset_entry["id"],))

    # 3. Security: Invalidate all existing active sessions
    cursor.execute("DELETE FROM sessions WHERE user_id = ?;", (user_id,))
    conn.commit()
    invalidate_user_sessions(user_id=user_id)

    # 4. Dispatch security alert email
    try:
        base_url = get_request_base_url()
        send_password_changed_email(reset_entry["email"], reset_entry["username"], base_url=base_url)
    except Exception as e:
        app.logger.warning(f"Failed to dispatch password changed alert: {e}")

    conn.close()

    return jsonify({
        "success": True,
        "message": "Password reset successfully! You can now log in with your new password."
    }), 200


# ==============================================================================
# USER PROFILES & SOCIAL GRAPH
# ==============================================================================

@app.route("/api/users/<username>", methods=["GET"])
def get_user_profile(username):
    current_user = get_authenticated_user()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, username, display_name, avatar_url, bio, is_admin, is_verified, dietary_json, created_at
        FROM users
        WHERE username = ? AND is_active = 1;
    """, (username,))
    profile_user = cursor.fetchone()

    if not profile_user:
        conn.close()
        return jsonify({"error": "Not Found", "message": "User not found"}), 404

    target_id = profile_user["id"]

    # Calculate statistics
    cursor.execute("SELECT COUNT(*) AS count FROM recipes WHERE user_id = ? AND is_public = 1;", (target_id,))
    recipes_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM friendships WHERE friend_id = ?;", (target_id,))
    followers_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM friendships WHERE user_id = ?;", (target_id,))
    following_count = cursor.fetchone()["count"]

    is_following = False
    is_blocked_by_me = False
    is_blocking_me = False
    is_friend = False

    if current_user:
        cursor.execute("SELECT id FROM friendships WHERE user_id = ? AND friend_id = ?;", (current_user["id"], target_id))
        is_following = bool(cursor.fetchone())

        cursor.execute("SELECT id FROM user_blocks WHERE user_id = ? AND blocked_user_id = ?;", (current_user["id"], target_id))
        is_blocked_by_me = bool(cursor.fetchone())

        cursor.execute("SELECT id FROM user_blocks WHERE user_id = ? AND blocked_user_id = ?;", (target_id, current_user["id"]))
        is_blocking_me = bool(cursor.fetchone())

        is_friend = are_users_friends(current_user["id"], target_id, conn=conn)

    # Get recent public recipes
    cursor.execute("""
        SELECT id, title, description, prep_time_min, cook_time_min, servings, difficulty, cuisine, tags_json, image_url, created_at
        FROM recipes
        WHERE user_id = ? AND is_public = 1
        ORDER BY created_at DESC LIMIT 12;
    """, (target_id,))
    recent_recipes = [dict(r) for r in cursor.fetchall()]

    badges = compute_user_badges(target_id, conn=conn)

    dietary_prefs = []
    try:
        dietary_prefs = json.loads(profile_user["dietary_json"] or "[]")
    except Exception:
        dietary_prefs = []

    user_dict = dict(profile_user)
    user_dict["dietary_preferences"] = dietary_prefs
    user_dict["badges"] = badges

    conn.close()

    return jsonify({
        "user": user_dict,
        "badges": badges,
        "stats": {
            "recipes_count": recipes_count,
            "followers_count": followers_count,
            "following_count": following_count,
            "is_following": is_following,
            "is_friend": is_friend,
            "is_blocked_by_me": is_blocked_by_me,
            "is_blocking_me": is_blocking_me
        },
        "recipes": recent_recipes
    })

@app.route("/api/users/profile", methods=["PUT"])
@require_auth
def update_profile():
    data = request.get_json() or {}
    display_name = (data.get("display_name") or "").strip()
    avatar_url = (data.get("avatar_url") or "").strip()
    bio = (data.get("bio") or "").strip()
    dietary_prefs = data.get("dietary_preferences")

    if not display_name:
        return jsonify({"error": "Validation Error", "message": "Display name cannot be empty"}), 400

    is_clean, err_msg = validate_clean_content(display_name, "Display Name")
    if not is_clean:
        return jsonify({"error": "Validation Error", "message": err_msg}), 400

    if bio:
        is_clean, err_msg = validate_clean_content(bio, "Culinary Bio")
        if not is_clean:
            return jsonify({"error": "Validation Error", "message": err_msg}), 400

    dietary_json = None
    if dietary_prefs is not None and isinstance(dietary_prefs, list):
        dietary_json = json.dumps([str(p).strip() for p in dietary_prefs if str(p).strip()])

    conn = get_db_connection()
    cursor = conn.cursor()

    if dietary_json is not None:
        cursor.execute("""
            UPDATE users
            SET display_name = ?, avatar_url = ?, bio = ?, dietary_json = ?
            WHERE id = ?;
        """, (display_name, avatar_url, bio, dietary_json, g.current_user["id"]))
    else:
        cursor.execute("""
            UPDATE users
            SET display_name = ?, avatar_url = ?, bio = ?
            WHERE id = ?;
        """, (display_name, avatar_url, bio, g.current_user["id"]))

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Profile updated successfully"})

@app.route("/api/users/<int:target_user_id>/follow", methods=["POST", "DELETE"])
@require_auth
def toggle_follow(target_user_id):
    if target_user_id == g.current_user["id"]:
        return jsonify({"error": "Bad Request", "message": "You cannot follow yourself"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        # Check if target user has blocked current user or vice versa
        if is_user_blocked(g.current_user["id"], target_user_id, conn=conn):
            conn.close()
            return jsonify({"error": "Forbidden", "message": "Unable to follow this user."}), 403

        cursor.execute("""
            INSERT OR IGNORE INTO friendships (user_id, friend_id)
            VALUES (?, ?);
        """, (g.current_user["id"], target_user_id))
        is_following = True
        create_notification(
            user_id=target_user_id,
            actor_id=g.current_user["id"],
            notif_type="follow",
            entity_type="user",
            entity_id=g.current_user["id"],
            message=f"@{g.current_user['username']} started following you.",
            conn=conn
        )
    else:
        cursor.execute("""
            DELETE FROM friendships
            WHERE user_id = ? AND friend_id = ?;
        """, (g.current_user["id"], target_user_id))
        is_following = False

    conn.commit()
    conn.close()
    return jsonify({"success": True, "is_following": is_following})

# ==============================================================================
# USER BLOCKING & SAFETY ENDPOINTS
# ==============================================================================

@app.route("/api/users/<int:target_user_id>/block", methods=["POST", "DELETE"])
@require_auth
def toggle_block_user(target_user_id):
    if target_user_id == g.current_user["id"]:
        return jsonify({"error": "Bad Request", "message": "You cannot block yourself"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("""
            INSERT OR IGNORE INTO user_blocks (user_id, blocked_user_id)
            VALUES (?, ?);
        """, (g.current_user["id"], target_user_id))
        # Also remove mutual friendship/follow
        cursor.execute("DELETE FROM friendships WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?);",
                       (g.current_user["id"], target_user_id, target_user_id, g.current_user["id"]))
        is_blocked = True
        msg = "User blocked. You will no longer see each other's posts, comments, or messages."
    else:
        cursor.execute("""
            DELETE FROM user_blocks
            WHERE user_id = ? AND blocked_user_id = ?;
        """, (g.current_user["id"], target_user_id))
        is_blocked = False
        msg = "User unblocked."

    conn.commit()
    conn.close()
    return jsonify({"success": True, "is_blocked": is_blocked, "message": msg})

@app.route("/api/users/blocked", methods=["GET"])
@require_auth
def get_blocked_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.display_name, u.avatar_url, b.created_at AS blocked_at
        FROM user_blocks b
        JOIN users u ON b.blocked_user_id = u.id
        WHERE b.user_id = ?
        ORDER BY b.created_at DESC;
    """, (g.current_user["id"],))
    blocked = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "blocked_users": blocked})

@app.route("/api/users/featured", methods=["GET"])
def get_featured_chefs():
    current_user = get_authenticated_user()
    if not current_user:
        cached = _FEED_CACHE.get("featured_chefs_public")
        if cached is not None:
            return jsonify(cached)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.id, u.username, u.display_name, u.avatar_url, u.bio, u.is_verified,
               (SELECT COUNT(*) FROM recipes r WHERE r.user_id = u.id AND r.is_public = 1) AS recipe_count,
               (SELECT COUNT(*) FROM friendships f WHERE f.friend_id = u.id) AS follower_count
        FROM users u
        WHERE u.is_active = 1
        ORDER BY recipe_count DESC, follower_count DESC
        LIMIT 6;
    """)
    chefs = [dict(r) for r in cursor.fetchall()]

    following_ids = set()
    if current_user and chefs:
        c_ids = [c["id"] for c in chefs]
        c_placeholders = ",".join(["?"] * len(c_ids))
        cursor.execute(f"SELECT friend_id FROM friendships WHERE user_id = ? AND friend_id IN ({c_placeholders});", [current_user["id"]] + c_ids)
        following_ids = {r["friend_id"] for r in cursor.fetchall()}

    for chef in chefs:
        chef["badges"] = compute_user_badges(chef["id"], conn=conn)
        chef["is_following"] = (chef["id"] in following_ids)

    conn.close()
    result = {"chefs": chefs}
    if not current_user:
        _FEED_CACHE.set("featured_chefs_public", result)
    return jsonify(result)


@app.route("/api/users", methods=["GET"])
def get_users_list():
    query = (request.args.get("q") or "").strip()
    clean_query = query.lstrip("@").strip()
    current_user = get_authenticated_user()
    conn = get_db_connection()
    cursor = conn.cursor()

    if clean_query:
        search_param = f"%{clean_query}%"
        cursor.execute("""
            SELECT u.id, u.username, u.display_name, u.avatar_url, u.bio,
                   (SELECT COUNT(*) FROM recipes r WHERE r.user_id = u.id AND r.is_public = 1) AS recipe_count,
                   (SELECT COUNT(*) FROM friendships f WHERE f.friend_id = u.id) AS follower_count
            FROM users u
            WHERE u.is_active = 1
              AND (u.username LIKE ? OR u.display_name LIKE ? OR u.bio LIKE ?)
            ORDER BY follower_count DESC, recipe_count DESC
            LIMIT 30;
        """, (search_param, search_param, search_param))
    else:
        cursor.execute("""
            SELECT u.id, u.username, u.display_name, u.avatar_url, u.bio,
                   (SELECT COUNT(*) FROM recipes r WHERE r.user_id = u.id AND r.is_public = 1) AS recipe_count,
                   (SELECT COUNT(*) FROM friendships f WHERE f.friend_id = u.id) AS follower_count
            FROM users u
            WHERE u.is_active = 1
            ORDER BY follower_count DESC, recipe_count DESC
            LIMIT 30;
        """)

    users = [dict(r) for r in cursor.fetchall()]
    if current_user:
        for u in users:
            cursor.execute("SELECT id FROM friendships WHERE user_id = ? AND friend_id = ?;", (current_user["id"], u["id"]))
            u["is_following"] = bool(cursor.fetchone())

    conn.close()
    return jsonify({"users": users})


# ==============================================================================
# GLOBAL UNIFIED SEARCH ENDPOINT
# ==============================================================================

@app.route("/api/search", methods=["GET"])
def global_search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"query": "", "recipes": [], "chefs": [], "stations": [], "posts": []})

    current_user = get_authenticated_user()
    conn = get_db_connection()
    cursor = conn.cursor()
    search_param = f"%{query}%"
    clean_user_query = query.lstrip("@").strip()
    user_search_param = f"%{clean_user_query}%"
    fts_q = sanitize_fts_query(query)

    # 1. Search Recipes with FTS5 BM25 ranking (fallback to LIKE)
    recipes = []
    if fts_q:
        try:
            cursor.execute("""
                SELECT r.id, r.title, r.description, r.image_url, r.cuisine, r.difficulty, r.prep_time_min, r.cook_time_min,
                       u.username, u.display_name
                FROM recipes_fts f
                JOIN recipes r ON f.rowid = r.id
                JOIN users u ON r.user_id = u.id
                WHERE (r.is_public = 1 OR (r.user_id = ?))
                  AND recipes_fts MATCH ?
                ORDER BY f.rank
                LIMIT 5;
            """, (current_user["id"] if current_user else -1, fts_q))
            recipes = [dict(row) for row in cursor.fetchall()]
        except Exception:
            recipes = []

    if not recipes:
        cursor.execute("""
            SELECT r.id, r.title, r.description, r.image_url, r.cuisine, r.difficulty, r.prep_time_min, r.cook_time_min,
                   u.username, u.display_name
            FROM recipes r
            JOIN users u ON r.user_id = u.id
            WHERE (r.is_public = 1 OR (r.user_id = ?))
              AND (r.title LIKE ? OR r.description LIKE ? OR r.cuisine LIKE ? OR r.ingredients_json LIKE ?)
            ORDER BY r.id DESC
            LIMIT 5;
        """, (current_user["id"] if current_user else -1, search_param, search_param, search_param, search_param))
        recipes = [dict(row) for row in cursor.fetchall()]

    # 2. Search Chefs / Users (Handles @username, display name, and bio)
    cursor.execute("""
        SELECT u.id, u.username, u.display_name, u.avatar_url, u.bio,
               (SELECT COUNT(*) FROM recipes r WHERE r.user_id = u.id AND r.is_public = 1) AS recipe_count,
               (SELECT COUNT(*) FROM friendships f WHERE f.friend_id = u.id) AS follower_count
        FROM users u
        WHERE u.is_active = 1
          AND (u.username LIKE ? OR u.display_name LIKE ? OR u.bio LIKE ?)
        ORDER BY follower_count DESC, recipe_count DESC
        LIMIT 6;
    """, (user_search_param, user_search_param, user_search_param))
    chefs = [dict(row) for row in cursor.fetchall()]

    if current_user and chefs:
        chef_ids = [c["id"] for c in chefs]
        c_placeholders = ",".join(["?"] * len(chef_ids))
        cursor.execute(f"SELECT friend_id FROM friendships WHERE user_id = ? AND friend_id IN ({c_placeholders});", [current_user["id"]] + chef_ids)
        following_ids = {row["friend_id"] for row in cursor.fetchall()}
        for chef in chefs:
            chef["is_following"] = (chef["id"] in following_ids)
    else:
        for chef in chefs:
            chef["is_following"] = False

    # 3. Search Stations
    cursor.execute("""
        SELECT s.id, s.name, s.slug, s.description, s.icon, s.banner_url, s.member_count
        FROM stations s
        WHERE s.name LIKE ? OR s.description LIKE ? OR s.slug LIKE ?
        ORDER BY s.member_count DESC
        LIMIT 4;
    """, (search_param, search_param, search_param))
    stations = [dict(row) for row in cursor.fetchall()]

    # 4. Search Community Posts with FTS5 BM25 ranking (fallback to LIKE)
    posts = []
    if fts_q:
        try:
            cursor.execute("""
                SELECT cp.id, cp.content, cp.image_url, cp.post_type, cp.created_at,
                       u.username, u.display_name, u.avatar_url,
                       s.name AS station_name, s.slug AS station_slug, s.icon AS station_icon,
                       r.title AS recipe_title
                FROM posts_fts f
                JOIN community_posts cp ON f.rowid = cp.id
                JOIN users u ON cp.user_id = u.id
                LEFT JOIN stations s ON cp.station_id = s.id
                LEFT JOIN recipes r ON cp.recipe_id = r.id
                WHERE cp.is_hidden = 0
                  AND posts_fts MATCH ?
                ORDER BY f.rank
                LIMIT 4;
            """, (fts_q,))
            posts = [dict(row) for row in cursor.fetchall()]
        except Exception:
            posts = []

    if not posts:
        cursor.execute("""
            SELECT cp.id, cp.content, cp.image_url, cp.post_type, cp.created_at,
                   u.username, u.display_name, u.avatar_url,
                   s.name AS station_name, s.slug AS station_slug, s.icon AS station_icon,
                   r.title AS recipe_title
            FROM community_posts cp
            JOIN users u ON cp.user_id = u.id
            LEFT JOIN stations s ON cp.station_id = s.id
            LEFT JOIN recipes r ON cp.recipe_id = r.id
            WHERE cp.is_hidden = 0
              AND (cp.content LIKE ? OR r.title LIKE ?)
            ORDER BY cp.id DESC
            LIMIT 4;
        """, (search_param, search_param))
        posts = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify({
        "query": query,
        "recipes": recipes,
        "chefs": chefs,
        "stations": stations,
        "posts": posts
    })


# ==============================================================================
# RECIPES & RECIPE BOX
# ==============================================================================

@app.route("/api/recipes", methods=["GET"])
def get_recipes():
    current_user = get_authenticated_user()
    scope = request.args.get("scope", "all")  # all, mine, saved, public
    query = (request.args.get("q") or "").strip()
    cuisine = (request.args.get("cuisine") or "").strip()
    tag = (request.args.get("tag") or "").strip()
    difficulty = (request.args.get("difficulty") or "").strip()
    author_id = request.args.get("user_id")
    limit = min(int(request.args.get("limit", 60)), 100)
    before_id = request.args.get("before_id") or request.args.get("cursor")

    # If unauthenticated public all recipes listing (first page)
    is_public_all = not current_user and scope == "all" and not query and not cuisine and not tag and not difficulty and not author_id and not before_id and limit == 60
    if is_public_all:
        cached = _FEED_CACHE.get("recipes_public_all")
        if cached is not None:
            return jsonify(cached)

    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = []
    params = []

    if scope == "mine":
        if not current_user:
            conn.close()
            return jsonify({"recipes": []})
        conditions.append("r.user_id = ?")
        params.append(current_user["id"])
    elif scope == "saved":
        if not current_user:
            conn.close()
            return jsonify({"recipes": []})
        conditions.append("r.id IN (SELECT recipe_id FROM saved_recipes WHERE user_id = ?)")
        params.append(current_user["id"])
    elif author_id:
        conditions.append("r.user_id = ?")
        params.append(author_id)
        if not current_user or current_user["id"] != int(author_id):
            conditions.append("r.is_public = 1")
    else:
        # Public recipes + own private recipes
        if current_user:
            conditions.append("(r.is_public = 1 OR r.user_id = ?)")
            params.append(current_user["id"])
        else:
            conditions.append("r.is_public = 1")

    if before_id:
        try:
            conditions.append("r.id < ?")
            params.append(int(before_id))
        except (ValueError, TypeError):
            pass

    if query:
        fts_q = sanitize_fts_query(query)
        if fts_q:
            conditions.append("r.id IN (SELECT rowid FROM recipes_fts WHERE recipes_fts MATCH ?)")
            params.append(fts_q)
        else:
            conditions.append("(r.title LIKE ? OR r.description LIKE ? OR r.tags_json LIKE ?)")
            wild = f"%{query}%"
            params.extend([wild, wild, wild])

    if cuisine and cuisine != "All":
        conditions.append("r.cuisine = ?")
        params.append(cuisine)

    if difficulty and difficulty != "All":
        conditions.append("r.difficulty = ?")
        params.append(difficulty)

    if tag:
        conditions.append("r.tags_json LIKE ?")
        params.append(f"%{tag}%")

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    sql = f"""
        SELECT r.id, r.user_id, r.original_author_id, r.title, r.description,
               r.prep_time_min, r.cook_time_min, r.servings, r.difficulty, r.cuisine,
               r.tags_json, r.image_url, r.source_url, r.is_public, r.created_at,
               u.username AS author_username, u.display_name AS author_display_name, u.avatar_url AS author_avatar,
               ROUND((SELECT AVG(rating) FROM recipe_reviews rr WHERE rr.recipe_id = r.id), 1) AS avg_rating,
               (SELECT COUNT(*) FROM recipe_reviews rr WHERE rr.recipe_id = r.id) AS reviews_count
        FROM recipes r
        JOIN users u ON r.user_id = u.id
        {where_clause}
        ORDER BY r.id DESC
        LIMIT {limit};
    """
    cursor.execute(sql, params)
    recipes = [dict(row) for row in cursor.fetchall()]
    saved_ids = set()
    if current_user and recipes:
        r_ids = [r["id"] for r in recipes]
        r_placeholders = ",".join(["?"] * len(r_ids))
        cursor.execute(f"SELECT recipe_id FROM saved_recipes WHERE user_id = ? AND recipe_id IN ({r_placeholders});", [current_user["id"]] + r_ids)
        saved_ids = {row["recipe_id"] for row in cursor.fetchall()}

    # Parse tags & check bookmark state
    for r in recipes:
        try:
            r["tags"] = json.loads(r["tags_json"])
        except Exception:
            r["tags"] = []
        r["is_saved"] = (r["id"] in saved_ids)

    conn.close()
    next_cursor = recipes[-1]["id"] if recipes and len(recipes) == limit else None
    result = {"recipes": recipes, "next_cursor": next_cursor}
    if is_public_all:
        _FEED_CACHE.set("recipes_public_all", result)
    return jsonify(result)

@app.route("/api/recipes/<int:recipe_id>", methods=["GET"])
def get_recipe_detail(recipe_id):
    current_user = get_authenticated_user()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.*,
               u.username AS author_username, u.display_name AS author_display_name, u.avatar_url AS author_avatar,
               orig.username AS orig_author_username, orig.display_name AS orig_author_display_name,
               ROUND((SELECT AVG(rating) FROM recipe_reviews rr WHERE rr.recipe_id = r.id), 1) AS avg_rating,
               (SELECT COUNT(*) FROM recipe_reviews rr WHERE rr.recipe_id = r.id) AS reviews_count
        FROM recipes r
        JOIN users u ON r.user_id = u.id
        LEFT JOIN users orig ON r.original_author_id = orig.id
        WHERE r.id = ?;
    """, (recipe_id,))
    recipe = cursor.fetchone()

    if not recipe:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Recipe not found"}), 404

    # Security check: Private recipe access
    if recipe["is_public"] != 1 and (not current_user or (current_user["id"] != recipe["user_id"] and current_user["is_admin"] != 1)):
        conn.close()
        return jsonify({"error": "Forbidden", "message": "This recipe is private"}), 403

    recipe_dict = dict(recipe)
    try:
        recipe_dict["tags"] = json.loads(recipe_dict["tags_json"])
        recipe_dict["ingredients"] = json.loads(recipe_dict["ingredients_json"])
        recipe_dict["steps"] = json.loads(recipe_dict["steps_json"])
    except Exception:
        recipe_dict["tags"] = []
        recipe_dict["ingredients"] = []
        recipe_dict["steps"] = []

    # Fetch Parent Recipe Lineage if this recipe is a fork
    recipe_dict["parent_recipe"] = None
    if recipe_dict.get("parent_recipe_id"):
        cursor.execute("""
            SELECT pr.id, pr.title, pr.user_id, pr.fork_notes,
                   u.username AS author_username, u.display_name AS author_display_name, u.avatar_url AS author_avatar
            FROM recipes pr
            JOIN users u ON pr.user_id = u.id
            WHERE pr.id = ?;
        """, (recipe_dict["parent_recipe_id"],))
        p_row = cursor.fetchone()
        if p_row:
            recipe_dict["parent_recipe"] = dict(p_row)

    # Community forks count
    cursor.execute("SELECT COUNT(*) AS cnt FROM recipes WHERE parent_recipe_id = ? AND is_public = 1;", (recipe_id,))
    recipe_dict["forks_count"] = cursor.fetchone()["cnt"]

    if current_user:
        cursor.execute("SELECT id, folder_name, notes FROM saved_recipes WHERE user_id = ? AND recipe_id = ?;", (current_user["id"], recipe_id))
        saved = cursor.fetchone()
        recipe_dict["is_saved"] = bool(saved)
        recipe_dict["saved_folder"] = saved["folder_name"] if saved else ""

        cursor.execute("SELECT id, rating, review, image_url, created_at FROM recipe_reviews WHERE user_id = ? AND recipe_id = ?;", (current_user["id"], recipe_id))
        user_rev = cursor.fetchone()
        recipe_dict["user_review"] = dict(user_rev) if user_rev else None
    else:
        recipe_dict["is_saved"] = False
        recipe_dict["saved_folder"] = ""
        recipe_dict["user_review"] = None

    recipe_dict["author_badges"] = compute_user_badges(recipe["user_id"], conn=conn)

    conn.close()
    return jsonify({"recipe": recipe_dict})

@app.route("/api/recipes", methods=["POST"])
@require_auth
def create_recipe():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Validation Error", "message": "Recipe title is required"}), 400

    description = (data.get("description") or "").strip()

    is_clean, err_msg = validate_clean_content(title, "Recipe Title")
    if not is_clean:
        return jsonify({"error": "Validation Error", "message": err_msg}), 400

    if description:
        is_clean, err_msg = validate_clean_content(description, "Recipe Description")
        if not is_clean:
            return jsonify({"error": "Validation Error", "message": err_msg}), 400

    prep_time = int(data.get("prep_time_min") or 0)
    cook_time = int(data.get("cook_time_min") or 0)
    servings = max(1, int(data.get("servings") or 4))
    difficulty = data.get("difficulty") or "Medium"
    cuisine = data.get("cuisine") or "Global"
    tags = data.get("tags") or []
    ingredients = data.get("ingredients") or []
    steps = data.get("steps") or []
    image_url = (data.get("image_url") or "").strip()
    source_url = (data.get("source_url") or "").strip()
    is_public = 1 if data.get("is_public", True) else 0
    parent_recipe_id = data.get("parent_recipe_id")
    fork_notes = (data.get("fork_notes") or "").strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    original_author_id = None
    if parent_recipe_id:
        cursor.execute("SELECT id, user_id, original_author_id FROM recipes WHERE id = ?;", (parent_recipe_id,))
        p_row = cursor.fetchone()
        if p_row:
            original_author_id = p_row["original_author_id"] or p_row["user_id"]
            cursor.execute("UPDATE recipes SET fork_count = COALESCE(fork_count, 0) + 1 WHERE id = ?;", (parent_recipe_id,))

    cursor.execute("""
        INSERT INTO recipes (
            user_id, original_author_id, parent_recipe_id, fork_notes, title, description, prep_time_min, cook_time_min, servings,
            difficulty, cuisine, tags_json, ingredients_json, steps_json,
            image_url, source_url, is_public
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        g.current_user["id"], original_author_id, parent_recipe_id, fork_notes, title, description, prep_time, cook_time, servings,
        difficulty, cuisine, json.dumps(tags), json.dumps(ingredients), json.dumps(steps),
        image_url, source_url, is_public
    ))
    recipe_id = cursor.lastrowid

    # Auto-index hashtags from title, description, and tags
    extracted_tags = extract_hashtags(f"{title} {description} {fork_notes}")
    if isinstance(tags, list):
        for t in tags:
            extracted_tags.extend(extract_hashtags(str(t)))
            if isinstance(t, str) and t.strip():
                extracted_tags.append(t.strip().lower())
    sync_entity_hashtags(cursor, "recipe", recipe_id, extracted_tags)

    if parent_recipe_id and original_author_id and original_author_id != g.current_user["id"]:
        create_notification(
            user_id=original_author_id,
            actor_id=g.current_user["id"],
            notif_type="fork",
            entity_type="recipe",
            entity_id=recipe_id,
            message=f"@{g.current_user['username']} created a twist on your recipe: '{title}'.",
            conn=conn
        )

    conn.commit()
    conn.close()
    _FEED_CACHE.invalidate()

    return jsonify({"success": True, "message": "Recipe created", "recipe_id": recipe_id}), 201

@app.route("/api/recipes/<int:recipe_id>", methods=["PUT"])
@require_auth
def update_recipe(recipe_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Security Mitigation: IDOR Protection
    cursor.execute("SELECT id, user_id FROM recipes WHERE id = ?;", (recipe_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Recipe not found"}), 404

    if existing["user_id"] != g.current_user["id"] and g.current_user["is_admin"] != 1:
        conn.close()
        return jsonify({"error": "Forbidden", "message": "You can only edit your own recipes"}), 403

    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        conn.close()
        return jsonify({"error": "Validation Error", "message": "Recipe title is required"}), 400

    description = (data.get("description") or "").strip()

    is_clean, err_msg = validate_clean_content(title, "Recipe Title")
    if not is_clean:
        conn.close()
        return jsonify({"error": "Validation Error", "message": err_msg}), 400

    if description:
        is_clean, err_msg = validate_clean_content(description, "Recipe Description")
        if not is_clean:
            conn.close()
            return jsonify({"error": "Validation Error", "message": err_msg}), 400
    prep_time = int(data.get("prep_time_min") or 0)
    cook_time = int(data.get("cook_time_min") or 0)
    servings = max(1, int(data.get("servings") or 4))
    difficulty = data.get("difficulty") or "Medium"
    cuisine = data.get("cuisine") or "Global"
    tags = data.get("tags") or []
    ingredients = data.get("ingredients") or []
    steps = data.get("steps") or []
    image_url = (data.get("image_url") or "").strip()
    source_url = (data.get("source_url") or "").strip()
    is_public = 1 if data.get("is_public", True) else 0
    fork_notes = (data.get("fork_notes") or "").strip()

    cursor.execute("""
        UPDATE recipes SET
            title = ?, description = ?, fork_notes = ?, prep_time_min = ?, cook_time_min = ?, servings = ?,
            difficulty = ?, cuisine = ?, tags_json = ?, ingredients_json = ?, steps_json = ?,
            image_url = ?, source_url = ?, is_public = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
    """, (
        title, description, fork_notes, prep_time, cook_time, servings,
        difficulty, cuisine, json.dumps(tags), json.dumps(ingredients), json.dumps(steps),
        image_url, source_url, is_public, recipe_id
    ))

    # Sync hashtags
    extracted_tags = extract_hashtags(f"{title} {description} {fork_notes}")
    if isinstance(tags, list):
        for t in tags:
            extracted_tags.extend(extract_hashtags(str(t)))
            if isinstance(t, str) and t.strip():
                extracted_tags.append(t.strip().lower())
    sync_entity_hashtags(cursor, "recipe", recipe_id, extracted_tags)

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Recipe updated successfully"})

@app.route("/api/recipes/<int:recipe_id>", methods=["DELETE"])
@require_auth
def delete_recipe(recipe_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Security Mitigation: IDOR Protection
    cursor.execute("SELECT id, user_id FROM recipes WHERE id = ?;", (recipe_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Recipe not found"}), 404

    if existing["user_id"] != g.current_user["id"] and g.current_user["is_admin"] != 1:
        conn.close()
        return jsonify({"error": "Forbidden", "message": "You can only delete your own recipes"}), 403

    cursor.execute("DELETE FROM recipes WHERE id = ?;", (recipe_id,))
    cursor.execute("DELETE FROM hashtag_references WHERE entity_type = 'recipe' AND entity_id = ?;", (recipe_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Recipe deleted"})

@app.route("/api/recipes/<int:recipe_id>/save", methods=["POST", "DELETE"])
@require_auth
def toggle_save_recipe(recipe_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        folder = data.get("folder_name") or "Favorites"
        notes = data.get("notes") or ""
        cursor.execute("""
            INSERT OR REPLACE INTO saved_recipes (user_id, recipe_id, folder_name, notes)
            VALUES (?, ?, ?, ?);
        """, (g.current_user["id"], recipe_id, folder, notes))
        saved = True
    else:
        cursor.execute("""
            DELETE FROM saved_recipes
            WHERE user_id = ? AND recipe_id = ?;
        """, (g.current_user["id"], recipe_id))
        saved = False

    conn.commit()
    conn.close()
    return jsonify({"success": True, "is_saved": saved})

@app.route("/api/recipes/<int:recipe_id>/fork", methods=["POST"])
@require_auth
def fork_recipe(recipe_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM recipes WHERE id = ?;", (recipe_id,))
    orig = cursor.fetchone()
    if not orig:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Recipe not found"}), 404

    data = request.get_json(silent=True) or {}
    new_title = (data.get("title") or f"{orig['title']} (My Fork)").strip()
    description = (data.get("description") or orig["description"]).strip()
    fork_notes = (data.get("fork_notes") or "").strip()
    prep_time = int(data.get("prep_time_min") if data.get("prep_time_min") is not None else orig["prep_time_min"] or 0)
    cook_time = int(data.get("cook_time_min") if data.get("cook_time_min") is not None else orig["cook_time_min"] or 0)
    servings = int(data.get("servings") if data.get("servings") is not None else orig["servings"] or 4)
    difficulty = data.get("difficulty") or orig["difficulty"] or "Medium"
    cuisine = data.get("cuisine") or orig["cuisine"] or "Global"
    tags_json = json.dumps(data.get("tags")) if "tags" in data else orig["tags_json"]
    ingredients_json = json.dumps(data.get("ingredients")) if "ingredients" in data else orig["ingredients_json"]
    steps_json = json.dumps(data.get("steps")) if "steps" in data else orig["steps_json"]
    image_url = (data.get("image_url") if "image_url" in data else orig["image_url"]) or ""
    source_url = (data.get("source_url") if "source_url" in data else orig["source_url"]) or ""

    original_author_id = orig["original_author_id"] or orig["user_id"]

    cursor.execute("""
        INSERT INTO recipes (
            user_id, original_author_id, parent_recipe_id, fork_notes, title, description, prep_time_min, cook_time_min,
            servings, difficulty, cuisine, tags_json, ingredients_json, steps_json,
            image_url, source_url, is_public
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
    """, (
        g.current_user["id"], original_author_id, orig["id"], fork_notes, new_title, description,
        prep_time, cook_time, servings, difficulty, cuisine, tags_json, ingredients_json,
        steps_json, image_url, source_url
    ))
    new_id = cursor.lastrowid

    # Increment parent recipe fork counter
    cursor.execute("UPDATE recipes SET fork_count = COALESCE(fork_count, 0) + 1 WHERE id = ?;", (orig["id"],))

    # Sync hashtags
    extracted_tags = extract_hashtags(f"{new_title} {description} {fork_notes}")
    try:
        parsed_tags = json.loads(tags_json)
        if isinstance(parsed_tags, list):
            for t in parsed_tags:
                extracted_tags.extend(extract_hashtags(str(t)))
                if isinstance(t, str) and t.strip():
                    extracted_tags.append(t.strip().lower())
    except Exception:
        pass
    sync_entity_hashtags(cursor, "recipe", new_id, extracted_tags)

    if orig["user_id"] != g.current_user["id"]:
        create_notification(
            user_id=orig["user_id"],
            actor_id=g.current_user["id"],
            notif_type="fork",
            entity_type="recipe",
            entity_id=new_id,
            message=f"@{g.current_user['username']} created a twist on your recipe '{orig['title']}'.",
            conn=conn
        )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Recipe forked to your Recipe Box!",
        "recipe_id": new_id,
        "forked_from": {"id": orig["id"], "title": orig["title"]}
    }), 201

@app.route("/api/recipes/<int:recipe_id>/forks", methods=["GET"])
def get_recipe_forks(recipe_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, user_id, parent_recipe_id, fork_count FROM recipes WHERE id = ?;", (recipe_id,))
    orig = cursor.fetchone()
    if not orig:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Recipe not found"}), 404

    parent_recipe = None
    if orig["parent_recipe_id"]:
        cursor.execute("""
            SELECT pr.id, pr.title, pr.user_id, pr.fork_notes,
                   u.username AS author_username, u.display_name AS author_display_name, u.avatar_url AS author_avatar
            FROM recipes pr
            JOIN users u ON pr.user_id = u.id
            WHERE pr.id = ?;
        """, (orig["parent_recipe_id"],))
        p_row = cursor.fetchone()
        parent_recipe = dict(p_row) if p_row else None

    cursor.execute("""
        SELECT r.id, r.title, r.description, r.fork_notes, r.image_url, r.created_at,
               r.prep_time_min, r.cook_time_min, r.difficulty, r.cuisine,
               u.id AS author_id, u.username AS author_username, u.display_name AS author_display_name, u.avatar_url AS author_avatar,
               ROUND((SELECT AVG(rating) FROM recipe_reviews rr WHERE rr.recipe_id = r.id), 1) AS avg_rating,
               (SELECT COUNT(*) FROM recipe_reviews rr WHERE rr.recipe_id = r.id) AS reviews_count
        FROM recipes r
        JOIN users u ON r.user_id = u.id
        WHERE r.parent_recipe_id = ? AND r.is_public = 1
        ORDER BY r.created_at DESC;
    """, (recipe_id,))
    forks = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        "success": True,
        "recipe_id": recipe_id,
        "recipe_title": orig["title"],
        "parent_recipe": parent_recipe,
        "forks_count": len(forks),
        "total_forks": len(forks),
        "forks": forks
    })

@app.route("/api/recipes/scrape", methods=["POST"])
@require_auth
def scrape_recipe():
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Validation Error", "message": "Recipe URL is required"}), 400

    try:
        scraped_data = scrape_recipe_from_url(url)
        return jsonify({"success": True, "recipe": scraped_data})
    except Exception as e:
        return jsonify({"error": "Scrape Error", "message": f"Could not scrape recipe: {str(e)}"}), 422


# ==============================================================================
# RECIPE REVIEWS & DISH REMAKES ("I MADE THIS!")
# ==============================================================================

@app.route("/api/recipes/<int:recipe_id>/reviews", methods=["GET"])
def get_recipe_reviews(recipe_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.id, r.recipe_id, r.user_id, r.rating, r.review, r.image_url, r.created_at,
               u.username, u.display_name, u.avatar_url
        FROM recipe_reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.recipe_id = ?
        ORDER BY r.created_at DESC;
    """, (recipe_id,))
    reviews = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT ROUND(AVG(rating), 1) AS avg_rating, COUNT(*) AS count
        FROM recipe_reviews
        WHERE recipe_id = ?;
    """, (recipe_id,))
    stats = cursor.fetchone()
    avg_rating = stats["avg_rating"] if stats and stats["avg_rating"] is not None else 0.0
    count = stats["count"] if stats else 0

    conn.close()
    return jsonify({
        "success": True,
        "reviews": reviews,
        "avg_rating": avg_rating,
        "count": count
    })

@app.route("/api/recipes/<int:recipe_id>/reviews", methods=["POST"])
@require_auth
def create_or_update_recipe_review(recipe_id):
    data = request.get_json() or {}
    try:
        rating = int(data.get("rating") or 5)
    except (ValueError, TypeError):
        rating = 5
    rating = max(1, min(5, rating))

    review_text = (data.get("review") or "").strip()
    image_url = (data.get("image_url") or "").strip()
    share_to_feed = bool(data.get("share_to_feed", False))

    if review_text:
        is_clean, err_msg = validate_clean_content(review_text, "Review")
        if not is_clean:
            return jsonify({"error": "Validation Error", "message": err_msg}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id, title, is_public FROM recipes WHERE id = ?;", (recipe_id,))
    recipe = cursor.fetchone()
    if not recipe:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Recipe not found"}), 404

    cursor.execute("""
        INSERT INTO recipe_reviews (recipe_id, user_id, rating, review, image_url)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(recipe_id, user_id) DO UPDATE SET
            rating = excluded.rating,
            review = excluded.review,
            image_url = excluded.image_url,
            created_at = CURRENT_TIMESTAMP;
    """, (recipe_id, g.current_user["id"], rating, review_text, image_url))
    conn.commit()

    # In-app notification to original author
    if recipe["user_id"] != g.current_user["id"]:
        stars_str = "★" * rating
        create_notification(
            user_id=recipe["user_id"],
            actor_id=g.current_user["id"],
            notif_type="review",
            entity_type="recipe",
            entity_id=recipe_id,
            message=f"@{g.current_user['username']} made your recipe '{recipe['title']}' and left a {rating}★ rating ({stars_str})!",
            conn=conn
        )

    # If user selected to share remake to the community feed
    if share_to_feed:
        feed_content = f"🍳 I Made This: {recipe['title']}!\nRating: {'★' * rating} ({rating}/5)\n\n{review_text}".strip()
        cursor.execute("""
            INSERT INTO community_posts (user_id, recipe_id, content, image_url)
            VALUES (?, ?, ?, ?);
        """, (g.current_user["id"], recipe_id, feed_content, image_url))
        conn.commit()

    conn.close()
    return jsonify({"success": True, "message": "Your review and remake have been shared!"})

@app.route("/api/recipes/<int:recipe_id>/reviews/<int:review_id>", methods=["DELETE"])
@require_auth
def delete_recipe_review(recipe_id, review_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id FROM recipe_reviews WHERE id = ? AND recipe_id = ?;", (review_id, recipe_id))
    review = cursor.fetchone()
    if not review:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Review not found"}), 404

    if review["user_id"] != g.current_user["id"] and g.current_user.get("is_admin") != 1:
        conn.close()
        return jsonify({"error": "Forbidden", "message": "You can only delete your own reviews"}), 403

    cursor.execute("DELETE FROM recipe_reviews WHERE id = ?;", (review_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Review removed"})


# ==============================================================================
# KITCHEN STATIONS (Sub-Communities)
# ==============================================================================

@app.route("/api/stations", methods=["GET"])
def get_stations():
    current_user = get_authenticated_user()
    query = (request.args.get("q") or "").strip()

    if not current_user and not query:
        cached = _FEED_CACHE.get("stations_directory_public")
        if cached is not None:
            return jsonify(cached)

    conn = get_db_connection()
    cursor = conn.cursor()

    if query:
        cursor.execute("""
            SELECT s.id, s.name, s.slug, s.description, s.icon, s.banner_url, s.rules_text, s.member_count, s.created_at,
                   (SELECT COUNT(*) FROM community_posts cp WHERE cp.station_id = s.id AND cp.is_hidden = 0) AS post_count
            FROM stations s
            WHERE s.name LIKE ? OR s.description LIKE ?
            ORDER BY s.member_count DESC, s.id ASC;
        """, (f"%{query}%", f"%{query}%"))
    else:
        cursor.execute("""
            SELECT s.id, s.name, s.slug, s.description, s.icon, s.banner_url, s.rules_text, s.member_count, s.created_at,
                   (SELECT COUNT(*) FROM community_posts cp WHERE cp.station_id = s.id AND cp.is_hidden = 0) AS post_count
            FROM stations s
            ORDER BY s.member_count DESC, s.id ASC;
        """)

    stations = [dict(row) for row in cursor.fetchall()]

    if current_user:
        cursor.execute("SELECT station_id, role FROM station_members WHERE user_id = ?;", (current_user["id"],))
        memberships = {r["station_id"]: r["role"] for r in cursor.fetchall()}
        for s in stations:
            s["is_member"] = s["id"] in memberships
            s["user_role"] = memberships.get(s["id"])
    else:
        for s in stations:
            s["is_member"] = False
            s["user_role"] = None

    conn.close()
    result = {"success": True, "stations": stations}
    if not current_user and not query:
        _FEED_CACHE.set("stations_directory_public", result)
    return jsonify(result)

@app.route("/api/stations/<slug>", methods=["GET"])
def get_station_detail(slug):
    current_user = get_authenticated_user()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id, s.name, s.slug, s.description, s.icon, s.banner_url, s.rules_text, s.member_count, s.created_at,
               (SELECT COUNT(*) FROM community_posts cp WHERE cp.station_id = s.id AND cp.is_hidden = 0) AS post_count
        FROM stations s
        WHERE s.slug = ?;
    """, (slug,))
    station = cursor.fetchone()
    if not station:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Kitchen station not found"}), 404

    station_dict = dict(station)

    # Lead cooks & member sample
    cursor.execute("""
        SELECT u.id, u.username, u.display_name, u.avatar_url, sm.role
        FROM station_members sm
        JOIN users u ON sm.user_id = u.id
        WHERE sm.station_id = ?
        ORDER BY (CASE WHEN sm.role = 'lead_cook' THEN 1 ELSE 2 END), sm.created_at ASC
        LIMIT 12;
    """, (station_dict["id"],))
    members = [dict(m) for m in cursor.fetchall()]
    station_dict["lead_cooks"] = [m for m in members if m["role"] == "lead_cook"]
    station_dict["members_sample"] = members

    if current_user:
        cursor.execute("SELECT role FROM station_members WHERE station_id = ? AND user_id = ?;", (station_dict["id"], current_user["id"]))
        mem = cursor.fetchone()
        station_dict["is_member"] = bool(mem)
        station_dict["user_role"] = mem["role"] if mem else None
    else:
        station_dict["is_member"] = False
        station_dict["user_role"] = None

    conn.close()
    return jsonify({"success": True, "station": station_dict})

@app.route("/api/stations/<slug>/join", methods=["POST"])
@require_auth
def toggle_station_membership(slug):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name FROM stations WHERE slug = ?;", (slug,))
    station = cursor.fetchone()
    if not station:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Kitchen station not found"}), 404

    station_id = station["id"]
    cursor.execute("SELECT id FROM station_members WHERE station_id = ? AND user_id = ?;", (station_id, g.current_user["id"]))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("DELETE FROM station_members WHERE station_id = ? AND user_id = ?;", (station_id, g.current_user["id"]))
        is_member = False
        message = f"Clocked out from {station['name']}"
    else:
        cursor.execute("INSERT INTO station_members (station_id, user_id, role) VALUES (?, ?, 'chef');", (station_id, g.current_user["id"]))
        is_member = True
        message = f"Clocked into {station['name']}!"

    cursor.execute("SELECT COUNT(*) AS cnt FROM station_members WHERE station_id = ?;", (station_id,))
    new_count = cursor.fetchone()["cnt"]
    cursor.execute("UPDATE stations SET member_count = ? WHERE id = ?;", (new_count, station_id))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "is_member": is_member,
        "member_count": new_count,
        "message": message
    })

@app.route("/api/stations", methods=["POST"])
@require_auth
def create_station():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Validation Error", "message": "Station name is required"}), 400

    if len(name) > 60:
        return jsonify({"error": "Validation Error", "message": "Station name must be 60 characters or fewer"}), 400

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        slug = f"station-{secrets.token_hex(4)}"

    description = (data.get("description") or "").strip()
    if not description:
        return jsonify({"error": "Validation Error", "message": "Station description is required"}), 400

    icon = (data.get("icon") or "🍳").strip()[:8]
    banner_url = (data.get("banner_url") or "").strip()
    rules_text = (data.get("rules_text") or "").strip()

    is_clean, err_msg = validate_clean_content(name, "Station Name")
    if not is_clean:
        return jsonify({"error": "Validation Error", "message": err_msg}), 400

    is_clean, err_msg = validate_clean_content(description, "Station Description")
    if not is_clean:
        return jsonify({"error": "Validation Error", "message": err_msg}), 400

    if rules_text:
        is_clean, err_msg = validate_clean_content(rules_text, "Station Rules")
        if not is_clean:
            return jsonify({"error": "Validation Error", "message": err_msg}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM stations WHERE slug = ? OR name = ?;", (slug, name))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "Conflict", "message": "A Kitchen Station with this name or slug already exists"}), 409

    cursor.execute("""
        INSERT INTO stations (name, slug, description, icon, banner_url, rules_text, member_count, created_by)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?);
    """, (name, slug, description, icon, banner_url, rules_text, g.current_user["id"]))
    station_id = cursor.lastrowid

    # Automatically clock in creator as lead_cook
    cursor.execute("""
        INSERT INTO station_members (station_id, user_id, role)
        VALUES (?, ?, 'lead_cook');
    """, (station_id, g.current_user["id"]))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": f"Station '{name}' opened successfully!",
        "station": {
            "id": station_id,
            "name": name,
            "slug": slug,
            "description": description,
            "icon": icon,
            "banner_url": banner_url,
            "rules_text": rules_text,
            "member_count": 1,
            "is_member": True,
            "user_role": "lead_cook"
        }
    }), 201

@app.route("/api/stations/<slug>/leaderboard", methods=["GET"])
def get_station_leaderboard(slug):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, slug, icon FROM stations WHERE slug = ?;", (slug,))
    station = cursor.fetchone()
    if not station:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Kitchen station not found"}), 404

    station_id = station["id"]

    # Top contributors / lead cooks in station
    cursor.execute("""
        SELECT u.id, u.username, u.display_name, u.avatar_url,
               COUNT(DISTINCT cp.id) AS post_count,
               COUNT(pl.id) AS likes_received
        FROM users u
        JOIN community_posts cp ON cp.user_id = u.id AND cp.station_id = ? AND cp.is_hidden = 0
        LEFT JOIN post_likes pl ON pl.post_id = cp.id
        GROUP BY u.id
        ORDER BY likes_received DESC, post_count DESC
        LIMIT 10;
    """, (station_id,))
    top_chefs = [dict(row) for row in cursor.fetchall()]

    # Trending station dishes & discussions
    cursor.execute("""
        SELECT cp.id, cp.content, cp.image_url, cp.recipe_id, cp.created_at,
               u.username, u.display_name, u.avatar_url,
               (SELECT COUNT(*) FROM post_likes pl WHERE pl.post_id = cp.id) AS like_count,
               (SELECT COUNT(*) FROM post_comments pc WHERE pc.post_id = cp.id AND pc.is_hidden = 0) AS comment_count,
               r.title AS recipe_title
        FROM community_posts cp
        JOIN users u ON cp.user_id = u.id
        LEFT JOIN recipes r ON cp.recipe_id = r.id
        WHERE cp.station_id = ? AND cp.is_hidden = 0
        ORDER BY like_count DESC, cp.created_at DESC
        LIMIT 6;
    """, (station_id,))
    trending_dishes = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify({
        "success": True,
        "station": dict(station),
        "lead_cooks": top_chefs,
        "trending_dishes": trending_dishes
    })


# ==============================================================================
# COMMUNITY POSTS, LIKES, COMMENTS & MODERATION
# ==============================================================================

# ==============================================================================
# COMMUNITY POSTS, MULTI-REACTIONS, POLLS & MENTIONS
# ==============================================================================

@app.route("/api/posts", methods=["GET"])
def get_posts():
    current_user = get_authenticated_user()
    post_type = request.args.get("type", "all")  # all, for_you, following, trending, question, showcase, post
    station_slug = (request.args.get("station") or "").strip()
    query = (request.args.get("q") or "").strip()
    dietary_filter = (request.args.get("dietary") or "").strip().lower()
    limit = min(int(request.args.get("limit", 50)), 100)
    before_id = request.args.get("before_id") or request.args.get("cursor")

    # If unauthenticated public feed request (first page)
    is_public_feed = (not current_user and not query and not dietary_filter and not station_slug and not before_id and limit == 50 and post_type in ["all", "trending", "showcase", "question", "post"])
    if is_public_feed:
        cached = _FEED_CACHE.get(f"posts_feed_{post_type}")
        if cached is not None:
            return jsonify(cached)

    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = ["p.is_hidden = 0"]
    params = []

    # Block filter: exclude posts by users who blocked current user or whom current user blocked
    if current_user:
        conditions.append("""
            p.user_id NOT IN (
                SELECT blocked_user_id FROM user_blocks WHERE user_id = ?
                UNION
                SELECT user_id FROM user_blocks WHERE blocked_user_id = ?
            )
        """)
        params.extend([current_user["id"], current_user["id"]])

    # Feed algorithms & type filtering
    if post_type in ["question", "showcase", "post"]:
        conditions.append("p.post_type = ?")
        params.append(post_type)
    elif post_type == "following":
        if not current_user:
            conn.close()
            return jsonify({"posts": []})
        conditions.append("p.user_id IN (SELECT friend_id FROM friendships WHERE user_id = ?)")
        params.append(current_user["id"])
    elif post_type == "for_you" and current_user:
        # Prioritize posts from user's joined stations, followed chefs, and trending posts
        pass  # We apply custom sorting below

    if station_slug:
        conditions.append("st.slug = ?")
        params.append(station_slug)

    if before_id:
        try:
            conditions.append("p.id < ?")
            params.append(int(before_id))
        except (ValueError, TypeError):
            pass

    if query:
        fts_q = sanitize_fts_query(query)
        if fts_q:
            conditions.append("(p.id IN (SELECT rowid FROM posts_fts WHERE posts_fts MATCH ?) OR r.id IN (SELECT rowid FROM recipes_fts WHERE recipes_fts MATCH ?))")
            params.extend([fts_q, fts_q])
        else:
            conditions.append("(p.content LIKE ? OR r.title LIKE ? OR st.name LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])

    if dietary_filter:
        tag_match = f"%{dietary_filter}%"
        conditions.append("(r.tags_json LIKE ? OR p.content LIKE ?)")
        params.extend([tag_match, tag_match])

    where_clause = "WHERE " + " AND ".join(conditions)

    order_clause = "ORDER BY p.id DESC"
    if post_type == "trending":
        # Rank by engagement on recent posts
        conditions.append("p.created_at >= datetime('now', '-14 days')")
        order_clause = """
            ORDER BY (
                (SELECT COUNT(*) FROM post_likes l WHERE l.post_id = p.id) * 2 +
                (SELECT COUNT(*) FROM post_reactions pr WHERE pr.post_id = p.id) * 3 +
                (SELECT COUNT(*) FROM post_comments c WHERE c.post_id = p.id AND c.is_hidden = 0) * 4
            ) DESC, p.id DESC
        """
    elif post_type == "for_you" and current_user:
        order_clause = f"""
            ORDER BY (
                CASE WHEN p.station_id IN (SELECT station_id FROM station_members WHERE user_id = {current_user['id']}) THEN 5 ELSE 0 END +
                CASE WHEN p.user_id IN (SELECT friend_id FROM friendships WHERE user_id = {current_user['id']}) THEN 4 ELSE 0 END +
                (SELECT COUNT(*) FROM post_likes l WHERE l.post_id = p.id)
            ) DESC, p.id DESC
        """

    sql = f"""
        SELECT p.id, p.user_id, p.content, p.image_url, p.recipe_id, p.station_id, p.post_type, p.created_at,
               u.username, u.display_name, u.avatar_url, u.is_verified,
               r.title AS recipe_title, r.image_url AS recipe_image, r.difficulty AS recipe_difficulty, r.prep_time_min + r.cook_time_min AS recipe_total_time,
               st.name AS station_name, st.slug AS station_slug, st.icon AS station_icon,
               (SELECT COUNT(*) FROM post_likes l WHERE l.post_id = p.id) AS like_count,
               (SELECT COUNT(*) FROM post_comments c WHERE c.post_id = p.id AND c.is_hidden = 0) AS comment_count
        FROM community_posts p
        JOIN users u ON p.user_id = u.id
        LEFT JOIN recipes r ON p.recipe_id = r.id
        LEFT JOIN stations st ON p.station_id = st.id
        {where_clause}
        {order_clause}
        LIMIT {limit};
    """
    cursor.execute(sql, params)
    posts = [dict(row) for row in cursor.fetchall()]
    posts = enrich_posts_batch(posts, current_user, conn)
    conn.close()
    next_cursor = posts[-1]["id"] if posts and len(posts) == limit else None
    result = {"posts": posts, "next_cursor": next_cursor}
    if is_public_feed:
        _FEED_CACHE.set(f"posts_feed_{post_type}", result)
    return jsonify(result)

@app.route("/api/posts", methods=["POST"])
@require_auth
def create_post():
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "Validation Error", "message": "Post content cannot be empty"}), 400

    is_clean, err_msg = validate_clean_content(content, "Post Content")
    if not is_clean:
        return jsonify({"error": "Validation Error", "message": err_msg}), 400

    image_url = (data.get("image_url") or "").strip()
    recipe_id = data.get("recipe_id")
    post_type = data.get("post_type") or "post"
    station_id = data.get("station_id")
    station_slug = (data.get("station_slug") or "").strip()
    poll_data = data.get("poll")

    conn = get_db_connection()
    cursor = conn.cursor()

    if not station_id and station_slug:
        cursor.execute("SELECT id FROM stations WHERE slug = ?;", (station_slug,))
        st_row = cursor.fetchone()
        if st_row:
            station_id = st_row["id"]

    cursor.execute("""
        INSERT INTO community_posts (user_id, content, image_url, recipe_id, station_id, post_type)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (g.current_user["id"], content, image_url, recipe_id, station_id, post_type))
    post_id = cursor.lastrowid

    # Create attached poll if provided
    if poll_data and isinstance(poll_data, dict):
        q = (poll_data.get("question") or "").strip()
        opts = [str(o).strip() for o in poll_data.get("options", []) if str(o).strip()]
        if q and len(opts) >= 2:
            is_q_clean, q_err = validate_clean_content(q, "Poll Question")
            if is_q_clean:
                cursor.execute("""
                    INSERT INTO post_polls (post_id, question, options_json)
                    VALUES (?, ?, ?);
                """, (post_id, q, json.dumps(opts[:5])))

    # Hashtag extraction & indexing
    extracted_tags = extract_hashtags(content)
    sync_entity_hashtags(cursor, "post", post_id, extracted_tags)

    # Mention extraction & notifications
    snippet = content[:40]
    parse_and_notify_mentions(
        text=content,
        actor_id=g.current_user["id"],
        entity_type="post",
        entity_id=post_id,
        message_template=f"@{g.current_user['username']} mentioned you in a culinary post: \"{snippet}\"",
        conn=conn
    )

    conn.commit()
    conn.close()
    _FEED_CACHE.invalidate()
    return jsonify({"success": True, "message": "Post published", "post_id": post_id}), 201

@app.route("/api/posts/<int:post_id>", methods=["DELETE"])
@require_auth
def delete_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id FROM community_posts WHERE id = ?;", (post_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Post not found"}), 404

    if existing["user_id"] != g.current_user["id"] and g.current_user["is_admin"] != 1:
        conn.close()
        return jsonify({"error": "Forbidden", "message": "You can only delete your own posts"}), 403

    sync_entity_hashtags(cursor, "post", post_id, [])
    cursor.execute("DELETE FROM community_posts WHERE id = ?;", (post_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Post deleted"})

# ==============================================================================
# HASHTAG DISCOVERY & TRENDING TOPICS
# ==============================================================================

@app.route("/api/hashtags/trending", methods=["GET"])
def get_trending_hashtags():
    limit = min(int(request.args.get("limit", 10)), 30)
    cache_key = f"trending_hashtags_{limit}"
    cached = _FEED_CACHE.get(cache_key)
    if cached is not None:
        return jsonify(cached)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT h.id, h.tag, h.usage_count,
               (SELECT COUNT(*) FROM hashtag_references hr WHERE hr.hashtag_id = h.id AND hr.created_at >= datetime('now', '-7 days')) AS recent_count
        FROM hashtags h
        WHERE h.usage_count > 0
        ORDER BY recent_count DESC, h.usage_count DESC
        LIMIT ?;
    """, (limit,))
    rows = cursor.fetchall()
    tags = [{"id": r["id"], "tag": r["tag"], "count": r["usage_count"], "recent_count": r["recent_count"]} for r in rows]
    conn.close()
    result = {"success": True, "trending_hashtags": tags, "trending": tags}
    _FEED_CACHE.set(cache_key, result)
    return jsonify(result)

@app.route("/api/hashtags/<string:tag_name>", methods=["GET"])
def get_hashtag_feed(tag_name):
    cleaned_tag = tag_name.strip().lower().lstrip("#")
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, tag, usage_count FROM hashtags WHERE tag = ?;", (cleaned_tag,))
    tag_info = cursor.fetchone()
    if not tag_info:
        conn.close()
        return jsonify({"success": True, "tag": cleaned_tag, "usage_count": 0, "recipes": [], "posts": []})

    # Fetch matching recipes
    cursor.execute("""
        SELECT r.*,
               u.username AS author_username, u.display_name AS author_display_name, u.avatar_url AS author_avatar,
               ROUND((SELECT AVG(rating) FROM recipe_reviews rr WHERE rr.recipe_id = r.id), 1) AS avg_rating,
               (SELECT COUNT(*) FROM recipe_reviews rr WHERE rr.recipe_id = r.id) AS reviews_count
        FROM recipes r
        JOIN hashtag_references hr ON hr.entity_type = 'recipe' AND hr.entity_id = r.id
        JOIN users u ON r.user_id = u.id
        WHERE hr.hashtag_id = ? AND r.is_public = 1
        ORDER BY r.created_at DESC
        LIMIT 30;
    """, (tag_info["id"],))
    recipe_rows = cursor.fetchall()
    recipes = []
    for r in recipe_rows:
        rd = dict(r)
        try:
            rd["tags"] = json.loads(rd["tags_json"])
            rd["ingredients"] = json.loads(rd["ingredients_json"])
            rd["steps"] = json.loads(rd["steps_json"])
        except Exception:
            rd["tags"] = []
            rd["ingredients"] = []
            rd["steps"] = []
        recipes.append(rd)

    # Fetch matching posts
    cursor.execute("""
        SELECT p.id, p.user_id, p.content, p.image_url, p.recipe_id, p.station_id, p.post_type, p.created_at,
               u.username, u.display_name, u.avatar_url, u.is_verified,
               r.title AS recipe_title, r.image_url AS recipe_image,
               st.name AS station_name, st.slug AS station_slug, st.icon AS station_icon,
               (SELECT COUNT(*) FROM post_likes l WHERE l.post_id = p.id) AS like_count,
               (SELECT COUNT(*) FROM post_comments c WHERE c.post_id = p.id AND c.is_hidden = 0) AS comment_count
        FROM community_posts p
        JOIN hashtag_references hr ON hr.entity_type = 'post' AND hr.entity_id = p.id
        JOIN users u ON p.user_id = u.id
        LEFT JOIN recipes r ON p.recipe_id = r.id
        LEFT JOIN stations st ON p.station_id = st.id
        WHERE hr.hashtag_id = ? AND p.is_hidden = 0
        ORDER BY p.created_at DESC
        LIMIT 30;
    """, (tag_info["id"],))
    posts = [dict(p) for p in cursor.fetchall()]
    current_user = get_authenticated_user()
    posts = enrich_posts_batch(posts, current_user, conn)
    conn.close()
    return jsonify({
        "success": True,
        "tag": tag_info["tag"],
        "usage_count": tag_info["usage_count"],
        "recipes": recipes,
        "posts": posts
    })

@app.route("/api/posts/<int:post_id>/like", methods=["POST", "DELETE"])
@require_auth
def toggle_post_like(post_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("""
            INSERT OR IGNORE INTO post_likes (post_id, user_id)
            VALUES (?, ?);
        """, (post_id, g.current_user["id"]))
        is_liked = True

        cursor.execute("SELECT user_id, content FROM community_posts WHERE id = ?;", (post_id,))
        p_row = cursor.fetchone()
        if p_row and p_row["user_id"] != g.current_user["id"]:
            snippet = (p_row["content"] or "your post")[:40]
            create_notification(
                user_id=p_row["user_id"],
                actor_id=g.current_user["id"],
                notif_type="like",
                entity_type="post",
                entity_id=post_id,
                message=f"@{g.current_user['username']} liked your post: \"{snippet}\"",
                conn=conn
            )
    else:
        cursor.execute("""
            DELETE FROM post_likes
            WHERE post_id = ? AND user_id = ?;
        """, (post_id, g.current_user["id"]))
        is_liked = False

    cursor.execute("SELECT COUNT(*) AS count FROM post_likes WHERE post_id = ?;", (post_id,))
    count = cursor.fetchone()["count"]
    conn.commit()
    conn.close()

    return jsonify({"success": True, "is_liked": is_liked, "like_count": count})

# ==============================================================================
# CULINARY MULTI-REACTIONS (heart, chef_kiss, fire, drool, genius)
# ==============================================================================

VALID_REACTIONS = {"heart", "chef_kiss", "fire", "drool", "genius"}
REACTION_EMOJIS = {"heart": "❤️", "chef_kiss": "👨‍🍳", "fire": "🔥", "drool": "🤤", "genius": "💡"}

@app.route("/api/posts/<int:post_id>/react", methods=["POST"])
@require_auth
def react_to_post(post_id):
    data = request.get_json() or {}
    reaction = (data.get("reaction") or "fire").strip().lower()

    if reaction not in VALID_REACTIONS:
        return jsonify({"error": "Validation Error", "message": f"Invalid reaction. Allowed: {list(VALID_REACTIONS)}"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id, content FROM community_posts WHERE id = ?;", (post_id,))
    p_row = cursor.fetchone()
    if not p_row:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Post not found"}), 404

    # Check existing reaction
    cursor.execute("SELECT reaction FROM post_reactions WHERE post_id = ? AND user_id = ?;", (post_id, g.current_user["id"]))
    existing = cursor.fetchone()

    user_reaction = None
    if existing and existing["reaction"] == reaction:
        # Toggle off
        cursor.execute("DELETE FROM post_reactions WHERE post_id = ? AND user_id = ?;", (post_id, g.current_user["id"]))
        user_reaction = None
    else:
        # Insert or update
        cursor.execute("""
            INSERT OR REPLACE INTO post_reactions (post_id, user_id, reaction)
            VALUES (?, ?, ?);
        """, (post_id, g.current_user["id"], reaction))
        user_reaction = reaction

        # Send notification to author
        if p_row["user_id"] != g.current_user["id"]:
            emoji = REACTION_EMOJIS.get(reaction, "✨")
            create_notification(
                user_id=p_row["user_id"],
                actor_id=g.current_user["id"],
                notif_type="reaction",
                entity_type="post",
                entity_id=post_id,
                message=f"@{g.current_user['username']} reacted {emoji} to your post: \"{p_row['content'][:35]}\"",
                conn=conn
            )

    conn.commit()

    # Aggregate counts
    cursor.execute("SELECT reaction, COUNT(*) AS count FROM post_reactions WHERE post_id = ? GROUP BY reaction;", (post_id,))
    counts = {r: 0 for r in VALID_REACTIONS}
    for row in cursor.fetchall():
        if row["reaction"] in counts:
            counts[row["reaction"]] = row["count"]

    conn.close()
    return jsonify({
        "success": True,
        "user_reaction": user_reaction,
        "reactions": {
            "counts": counts,
            "total": sum(counts.values()),
            "user_reaction": user_reaction
        }
    })

# ==============================================================================
# COMMUNITY POLLS & VOTING
# ==============================================================================

@app.route("/api/polls/<int:poll_id>/vote", methods=["POST"])
@require_auth
def vote_poll(poll_id):
    data = request.get_json() or {}
    option_index = data.get("option_index")
    if option_index is None or not isinstance(option_index, int) or option_index < 0:
        return jsonify({"error": "Validation Error", "message": "Valid option_index required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, post_id, question, options_json FROM post_polls WHERE id = ?;", (poll_id,))
    poll = cursor.fetchone()
    if not poll:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Poll not found"}), 404

    try:
        options = json.loads(poll["options_json"] or "[]")
    except Exception:
        options = []

    if option_index >= len(options):
        conn.close()
        return jsonify({"error": "Validation Error", "message": "Invalid option selection"}), 400

    # Cast or update vote
    cursor.execute("""
        INSERT OR REPLACE INTO poll_votes (poll_id, user_id, option_index)
        VALUES (?, ?, ?);
    """, (poll_id, g.current_user["id"], option_index))
    conn.commit()

    # Calculate updated poll stats
    cursor.execute("SELECT option_index, COUNT(*) AS count FROM poll_votes WHERE poll_id = ? GROUP BY option_index;", (poll_id,))
    vote_rows = {r["option_index"]: r["count"] for r in cursor.fetchall()}
    total_votes = sum(vote_rows.values())

    options_data = []
    for idx, opt_text in enumerate(options):
        votes = vote_rows.get(idx, 0)
        pct = round((votes / total_votes * 100)) if total_votes > 0 else 0
        options_data.append({
            "index": idx,
            "text": opt_text,
            "votes": votes,
            "percent": pct
        })

    conn.close()
    return jsonify({
        "success": True,
        "poll": {
            "id": poll["id"],
            "question": poll["question"],
            "options": options_data,
            "total_votes": total_votes,
            "user_voted_index": option_index
        }
    })

# ==============================================================================
# STATION WEEKLY CHALLENGES
# ==============================================================================

@app.route("/api/stations/<slug>/challenges", methods=["GET"])
def get_station_challenges(slug):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM stations WHERE slug = ?;", (slug,))
    st = cursor.fetchone()
    if not st:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Station not found"}), 404

    cursor.execute("""
        SELECT id, station_id, title, description, tag, icon, start_date, end_date, is_active, created_at
        FROM station_challenges
        WHERE station_id = ? AND is_active = 1
        ORDER BY created_at DESC;
    """, (st["id"],))
    challenges = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({"success": True, "challenges": challenges})

# ==============================================================================
# POST COMMENTS & NESTED REPLIES
# ==============================================================================

@app.route("/api/posts/<int:post_id>/comments", methods=["GET"])
def get_post_comments(post_id):
    current_user = get_authenticated_user()
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = ["c.post_id = ?", "c.is_hidden = 0"]
    params = [post_id]

    if current_user:
        conditions.append("""
            c.user_id NOT IN (
                SELECT blocked_user_id FROM user_blocks WHERE user_id = ?
                UNION
                SELECT user_id FROM user_blocks WHERE blocked_user_id = ?
            )
        """)
        params.extend([current_user["id"], current_user["id"]])

    where_clause = "WHERE " + " AND ".join(conditions)

    cursor.execute(f"""
        SELECT c.id, c.post_id, c.user_id, c.comment, c.parent_id, c.reply_to_username, c.created_at,
               u.username, u.display_name, u.avatar_url, u.is_verified
        FROM post_comments c
        JOIN users u ON c.user_id = u.id
        {where_clause}
        ORDER BY c.created_at ASC;
    """, params)
    comments = [dict(row) for row in cursor.fetchall()]

    for c in comments:
        c["author_badges"] = compute_user_badges(c["user_id"], conn=conn)

    conn.close()
    return jsonify({"comments": comments})

@app.route("/api/posts/<int:post_id>/comments", methods=["POST"])
@require_auth
def create_comment(post_id):
    data = request.get_json() or {}
    comment_text = (data.get("comment") or "").strip()
    if not comment_text:
        return jsonify({"error": "Validation Error", "message": "Comment cannot be empty"}), 400

    is_clean, err_msg = validate_clean_content(comment_text, "Comment")
    if not is_clean:
        return jsonify({"error": "Validation Error", "message": err_msg}), 400

    parent_id = data.get("parent_id")
    reply_to_username = (data.get("reply_to_username") or "").strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, content FROM community_posts WHERE id = ?;", (post_id,))
    p_row = cursor.fetchone()
    if not p_row:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Post not found"}), 404

    # Ensure no blocking relationship exists with post owner
    if is_user_blocked(g.current_user["id"], p_row["user_id"], conn=conn):
        conn.close()
        return jsonify({"error": "Forbidden", "message": "Unable to comment on this post."}), 403

    cursor.execute("""
        INSERT INTO post_comments (post_id, user_id, comment, parent_id, reply_to_username)
        VALUES (?, ?, ?, ?, ?);
    """, (post_id, g.current_user["id"], comment_text, parent_id, reply_to_username))
    comment_id = cursor.lastrowid
    conn.commit()

    if p_row["user_id"] != g.current_user["id"]:
        create_notification(
            user_id=p_row["user_id"],
            actor_id=g.current_user["id"],
            notif_type="comment",
            entity_type="post",
            entity_id=post_id,
            message=f"@{g.current_user['username']} commented: \"{comment_text[:40]}\"",
            conn=conn
        )
        conn.commit()

    # Mention notifications in comments
    parse_and_notify_mentions(
        text=comment_text,
        actor_id=g.current_user["id"],
        entity_type="post",
        entity_id=post_id,
        message_template=f"@{g.current_user['username']} mentioned you in a comment: \"{comment_text[:40]}\"",
        conn=conn
    )

    badges = compute_user_badges(g.current_user["id"], conn=conn)
    conn.close()

    return jsonify({
        "success": True,
        "message": "Comment added",
        "comment": {
            "id": comment_id,
            "post_id": post_id,
            "user_id": g.current_user["id"],
            "comment": comment_text,
            "parent_id": parent_id,
            "reply_to_username": reply_to_username,
            "username": g.current_user["username"],
            "display_name": g.current_user["display_name"],
            "avatar_url": g.current_user["avatar_url"],
            "author_badges": badges,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }
    }), 201

@app.route("/api/comments/<int:comment_id>", methods=["DELETE"])
@require_auth
def delete_comment(comment_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id FROM post_comments WHERE id = ?;", (comment_id,))
    comment = cursor.fetchone()
    if not comment:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Comment not found"}), 404

    if comment["user_id"] != g.current_user["id"] and g.current_user["is_admin"] != 1:
        conn.close()
        return jsonify({"error": "Forbidden", "message": "You can only delete your own comments"}), 403

    cursor.execute("DELETE FROM post_comments WHERE id = ?;", (comment_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Comment deleted"})

@app.route("/api/reports", methods=["POST"])
@require_auth
def submit_report():
    data = request.get_json() or {}
    post_id = data.get("post_id")
    comment_id = data.get("comment_id")
    reason = (data.get("reason") or "Spam / Inappropriate").strip()

    if not post_id and not comment_id:
        return jsonify({"error": "Validation Error", "message": "Must report a post or comment"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO post_reports (post_id, comment_id, reported_by, reason)
        VALUES (?, ?, ?, ?);
    """, (post_id, comment_id, g.current_user["id"], reason))

    if post_id:
        cursor.execute("UPDATE community_posts SET report_count = report_count + 1 WHERE id = ?;", (post_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Report submitted for moderation review"})

# ==============================================================================
# DIRECT MESSAGES & KITCHEN WHISPERS (1-on-1 DM & REQUESTS ENGINE)
# ==============================================================================

@app.route("/api/messages/unread-count", methods=["GET"])
@require_auth
def get_unread_messages_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) AS count
        FROM direct_messages
        WHERE recipient_id = ? AND is_read = 0;
    """, (g.current_user["id"],))
    count = cursor.fetchone()["count"]

    # Count incoming pending message requests
    cursor.execute("""
        SELECT COUNT(*) AS count
        FROM message_requests
        WHERE recipient_id = ? AND status = 'pending';
    """, (g.current_user["id"],))
    requests_count = cursor.fetchone()["count"]

    conn.close()
    return jsonify({
        "success": True,
        "unread_count": count,
        "unread_requests_count": requests_count
    })

@app.route("/api/messages/conversations", methods=["GET"])
@require_auth
def get_conversations():
    my_id = g.current_user["id"]
    tab = request.args.get("tab", "all").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get distinct conversational partner IDs (excluding blocked users)
    cursor.execute("""
        SELECT DISTINCT
            CASE WHEN sender_id = ? THEN recipient_id ELSE sender_id END AS partner_id
        FROM direct_messages
        WHERE (sender_id = ? OR recipient_id = ?)
          AND partner_id NOT IN (
              SELECT blocked_user_id FROM user_blocks WHERE user_id = ?
              UNION
              SELECT user_id FROM user_blocks WHERE blocked_user_id = ?
          );
    """, (my_id, my_id, my_id, my_id, my_id))
    partner_rows = cursor.fetchall()

    primary_convos = []
    request_convos = []

    for pr in partner_rows:
        partner_id = pr["partner_id"]
        cursor.execute("SELECT id, username, display_name, avatar_url, is_verified FROM users WHERE id = ?;", (partner_id,))
        partner = cursor.fetchone()
        if not partner:
            continue

        is_friend = are_users_friends(my_id, partner_id, conn=conn)
        req_info = get_message_request_info(my_id, partner_id, conn=conn)

        # Get latest message in thread
        cursor.execute("""
            SELECT id, sender_id, recipient_id, message, recipe_id, post_id, is_read, created_at
            FROM direct_messages
            WHERE (sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?)
            ORDER BY created_at DESC, id DESC
            LIMIT 1;
        """, (my_id, partner_id, partner_id, my_id))
        last_msg = cursor.fetchone()

        # Get unread count from this partner
        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM direct_messages
            WHERE sender_id = ? AND recipient_id = ? AND is_read = 0;
        """, (partner_id, my_id))
        unread_count = cursor.fetchone()["count"]

        item = {
            "partner": dict(partner),
            "partner_badges": compute_user_badges(partner_id, conn=conn),
            "last_message": dict(last_msg) if last_msg else None,
            "unread_count": unread_count,
            "is_friend": is_friend,
            "is_request": (not is_friend and req_info.get("status") == "pending"),
            "request_info": req_info
        }

        if is_friend or req_info.get("status") == "accepted":
            primary_convos.append(item)
        elif req_info.get("status") == "pending":
            request_convos.append(item)
        else:
            primary_convos.append(item)

    # Sort conversations by latest message timestamp DESC
    primary_convos.sort(key=lambda c: (c["last_message"]["created_at"] if c["last_message"] else ""), reverse=True)
    request_convos.sort(key=lambda c: (c["last_message"]["created_at"] if c["last_message"] else ""), reverse=True)

    pending_incoming_count = len([c for c in request_convos if c.get("request_info", {}).get("is_recipient")])

    conn.close()
    return jsonify({
        "success": True,
        "primary": primary_convos,
        "requests": request_convos,
        "conversations": primary_convos if tab == "primary" else (request_convos if tab == "requests" else primary_convos + request_convos),
        "requests_count": pending_incoming_count
    })

@app.route("/api/messages/<int:partner_id>", methods=["GET"])
@require_auth
def get_message_thread(partner_id):
    my_id = g.current_user["id"]
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, username, display_name, avatar_url, is_verified FROM users WHERE id = ? AND is_active = 1;", (partner_id,))
    partner = cursor.fetchone()
    if not partner:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Chef not found"}), 404

    # Check blocking & friendship
    is_blocked = is_user_blocked(my_id, partner_id, conn=conn)
    is_friend = are_users_friends(my_id, partner_id, conn=conn)
    req_info = get_message_request_info(my_id, partner_id, conn=conn)

    # Mark incoming messages from partner as read
    cursor.execute("""
        UPDATE direct_messages
        SET is_read = 1
        WHERE sender_id = ? AND recipient_id = ? AND is_read = 0;
    """, (partner_id, my_id))
    conn.commit()

    # Query chronological messages
    cursor.execute("""
        SELECT dm.id, dm.sender_id, dm.recipient_id, dm.message, dm.recipe_id, dm.post_id, dm.is_read, dm.created_at,
               r.title AS recipe_title, r.image_url AS recipe_image, r.difficulty AS recipe_difficulty,
               p.content AS post_snippet, p.image_url AS post_image
        FROM direct_messages dm
        LEFT JOIN recipes r ON dm.recipe_id = r.id
        LEFT JOIN community_posts p ON dm.post_id = p.id
        WHERE (dm.sender_id = ? AND dm.recipient_id = ?) OR (dm.sender_id = ? AND dm.recipient_id = ?)
        ORDER BY dm.created_at ASC, dm.id ASC
        LIMIT 100;
    """, (my_id, partner_id, partner_id, my_id))
    messages = [dict(m) for m in cursor.fetchall()]

    conn.close()
    return jsonify({
        "success": True,
        "partner": dict(partner),
        "is_blocked": is_blocked,
        "is_friend": is_friend,
        "request_info": req_info,
        "is_pending_request": (not is_friend and req_info.get("status") == "pending"),
        "is_request_recipient": bool(req_info.get("is_recipient") and req_info.get("status") == "pending"),
        "is_request_sender": bool(req_info.get("is_sender") and req_info.get("status") == "pending"),
        "messages": messages
    })

@app.route("/api/messages/<int:recipient_id>", methods=["POST"])
@require_auth
def send_direct_message(recipient_id):
    if recipient_id == g.current_user["id"]:
        return jsonify({"error": "Bad Request", "message": "You cannot send messages to yourself"}), 400

    data = request.get_json() or {}
    message_text = (data.get("message") or "").strip()
    recipe_id = data.get("recipe_id")
    post_id = data.get("post_id")

    if not message_text and not recipe_id and not post_id:
        return jsonify({"error": "Validation Error", "message": "Message cannot be empty"}), 400

    if message_text:
        is_clean, err_msg = validate_clean_content(message_text, "Message")
        if not is_clean:
            return jsonify({"error": "Validation Error", "message": err_msg}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, username, display_name FROM users WHERE id = ? AND is_active = 1;", (recipient_id,))
    recipient = cursor.fetchone()
    if not recipient:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Recipient chef not found"}), 404

    # IDOR / Safety Check: Blocked validation
    if is_user_blocked(g.current_user["id"], recipient_id, conn=conn):
        conn.close()
        return jsonify({"error": "Forbidden", "message": "Unable to send message to this chef."}), 403

    # Check friendship & message request rules
    is_friend = are_users_friends(g.current_user["id"], recipient_id, conn=conn)
    req_info = get_message_request_info(g.current_user["id"], recipient_id, conn=conn)

    is_request = False
    if not is_friend:
        # If current user already sent a pending request that recipient hasn't accepted -> prevent spam
        if req_info.get("status") == "pending" and req_info.get("is_sender"):
            conn.close()
            return jsonify({
                "error": "Pending Request",
                "message": f"You already have a pending message request with Chef @{recipient['username']}. Please wait for them to accept before sending more messages."
            }), 400
        elif req_info.get("status") == "pending" and req_info.get("is_recipient"):
            # Recipient is replying to the pending request -> automatically accept!
            cursor.execute("""
                UPDATE message_requests
                SET status = 'accepted', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
            """, (req_info["id"],))
            conn.commit()
            is_friend = True
        else:
            # First message from non-friend -> create or update message_requests as pending
            cursor.execute("""
                INSERT INTO message_requests (sender_id, recipient_id, status)
                VALUES (?, ?, 'pending')
                ON CONFLICT(sender_id, recipient_id) DO UPDATE SET status = 'pending', updated_at = CURRENT_TIMESTAMP;
            """, (g.current_user["id"], recipient_id))
            conn.commit()
            is_request = True

    cursor.execute("""
        INSERT INTO direct_messages (sender_id, recipient_id, message, recipe_id, post_id)
        VALUES (?, ?, ?, ?, ?);
    """, (g.current_user["id"], recipient_id, message_text, recipe_id, post_id))
    msg_id = cursor.lastrowid
    conn.commit()

    # Create notification for recipient
    snippet = message_text[:40] if message_text else "shared culinary craft with you"
    if is_request:
        notif_msg = f"@{g.current_user['username']} sent you a message request: \"{snippet}\""
        notif_type = "message_request"
    else:
        notif_msg = f"@{g.current_user['username']} sent you a whisper: \"{snippet}\""
        notif_type = "dm"

    create_notification(
        user_id=recipient_id,
        actor_id=g.current_user["id"],
        notif_type=notif_type,
        entity_type="message",
        entity_id=msg_id,
        message=notif_msg,
        conn=conn
    )
    conn.commit()

    # Hydrate attached recipe/post details if any
    recipe_data = None
    if recipe_id:
        cursor.execute("SELECT id, title, image_url, difficulty FROM recipes WHERE id = ?;", (recipe_id,))
        r_row = cursor.fetchone()
        if r_row:
            recipe_data = dict(r_row)

    post_data = None
    if post_id:
        cursor.execute("SELECT id, content, image_url FROM community_posts WHERE id = ?;", (post_id,))
        p_row = cursor.fetchone()
        if p_row:
            post_data = dict(p_row)

    conn.close()

    return jsonify({
        "success": True,
        "message": "Message request sent!" if is_request else "Whisper sent!",
        "is_request": is_request,
        "dm": {
            "id": msg_id,
            "sender_id": g.current_user["id"],
            "recipient_id": recipient_id,
            "message": message_text,
            "recipe_id": recipe_id,
            "recipe_title": recipe_data["title"] if recipe_data else None,
            "recipe_image": recipe_data["image_url"] if recipe_data else None,
            "post_id": post_id,
            "post_snippet": post_data["content"] if post_data else None,
            "post_image": post_data["image_url"] if post_data else None,
            "is_read": 0,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }
    }), 201

@app.route("/api/messages/requests/<int:partner_id>/accept", methods=["POST"])
@require_auth
def accept_message_request(partner_id):
    my_id = g.current_user["id"]
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, username FROM users WHERE id = ?;", (partner_id,))
    partner = cursor.fetchone()
    if not partner:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Chef not found"}), 404

    cursor.execute("""
        SELECT id, sender_id, recipient_id, status
        FROM message_requests
        WHERE (sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?);
    """, (partner_id, my_id, my_id, partner_id))
    req = cursor.fetchone()

    if req:
        cursor.execute("""
            UPDATE message_requests
            SET status = 'accepted', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
        """, (req["id"],))
    else:
        cursor.execute("""
            INSERT INTO message_requests (sender_id, recipient_id, status)
            VALUES (?, ?, 'accepted')
            ON CONFLICT(sender_id, recipient_id) DO UPDATE SET status = 'accepted', updated_at = CURRENT_TIMESTAMP;
        """, (partner_id, my_id))

    # Mark all incoming messages from partner as read
    cursor.execute("""
        UPDATE direct_messages
        SET is_read = 1
        WHERE sender_id = ? AND recipient_id = ?;
    """, (partner_id, my_id))

    # Notify requester
    create_notification(
        user_id=partner_id,
        actor_id=my_id,
        notif_type="message_request_accepted",
        entity_type="user",
        entity_id=my_id,
        message=f"@{g.current_user['username']} accepted your message request! You can now whisper freely.",
        conn=conn
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Message request from @{partner['username']} accepted."})

@app.route("/api/messages/requests/<int:partner_id>/decline", methods=["POST"])
@require_auth
def decline_message_request(partner_id):
    my_id = g.current_user["id"]
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE message_requests
        SET status = 'declined', updated_at = CURRENT_TIMESTAMP
        WHERE (sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?);
    """, (partner_id, my_id, my_id, partner_id))

    # Delete unaccepted direct messages from that sender to keep inbox clean
    cursor.execute("""
        DELETE FROM direct_messages
        WHERE sender_id = ? AND recipient_id = ?;
    """, (partner_id, my_id))

    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Message request declined."})

@app.route("/api/messages/read", methods=["POST"])
@require_auth
def mark_messages_read():
    data = request.get_json() or {}
    sender_id = data.get("sender_id")

    conn = get_db_connection()
    cursor = conn.cursor()

    if sender_id:
        cursor.execute("""
            UPDATE direct_messages
            SET is_read = 1
            WHERE sender_id = ? AND recipient_id = ? AND is_read = 0;
        """, (sender_id, g.current_user["id"]))
    else:
        cursor.execute("""
            UPDATE direct_messages
            SET is_read = 1
            WHERE recipient_id = ? AND is_read = 0;
        """, (g.current_user["id"],))

    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Messages marked as read"})


# ==============================================================================
# IN-APP NOTIFICATIONS & ACTIVITY INBOX
# ==============================================================================

@app.route("/api/notifications", methods=["GET"])
@require_auth
def get_notifications():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT n.id, n.user_id, n.actor_id, n.type, n.entity_type, n.entity_id, n.message, n.is_read, n.created_at,
               u.username AS actor_username, u.display_name AS actor_display_name, u.avatar_url AS actor_avatar
        FROM notifications n
        LEFT JOIN users u ON n.actor_id = u.id
        WHERE n.user_id = ?
        ORDER BY n.created_at DESC
        LIMIT 50;
    """, (g.current_user["id"],))
    notifications = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT COUNT(*) AS unread_count
        FROM notifications
        WHERE user_id = ? AND is_read = 0;
    """, (g.current_user["id"],))
    unread_count = cursor.fetchone()["unread_count"]

    conn.close()
    return jsonify({
        "success": True,
        "notifications": notifications,
        "unread_count": unread_count
    })

@app.route("/api/notifications/read", methods=["POST"])
@require_auth
def mark_notifications_read():
    data = request.get_json() or {}
    notif_ids = data.get("notification_ids")

    conn = get_db_connection()
    cursor = conn.cursor()

    if notif_ids and isinstance(notif_ids, list):
        placeholders = ",".join(["?"] * len(notif_ids))
        cursor.execute(f"""
            UPDATE notifications
            SET is_read = 1
            WHERE user_id = ? AND id IN ({placeholders});
        """, [g.current_user["id"]] + notif_ids)
    else:
        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE user_id = ?;
        """, (g.current_user["id"],))

    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Notifications marked as read"})

@app.route("/api/notifications/<int:notif_id>", methods=["DELETE"])
@require_auth
def delete_notification(notif_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id FROM notifications WHERE id = ?;", (notif_id,))
    notif = cursor.fetchone()
    if not notif:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Notification not found"}), 404

    if notif["user_id"] != g.current_user["id"] and g.current_user.get("is_admin") != 1:
        conn.close()
        return jsonify({"error": "Forbidden", "message": "You can only delete your own notifications"}), 403

    cursor.execute("DELETE FROM notifications WHERE id = ?;", (notif_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Notification deleted"})


# ==============================================================================
# ADMIN & MODERATION DASHBOARD
# ==============================================================================

@app.route("/api/admin/stats", methods=["GET"])
@admin_required
def get_admin_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users;")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM recipes;")
    total_recipes = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM community_posts;")
    total_posts = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM post_reports;")
    total_reports = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM planner;")
    total_plans = cursor.fetchone()[0]
    conn.close()

    return jsonify({
        "success": True,
        "stats": {
            "total_users": total_users,
            "total_recipes": total_recipes,
            "total_posts": total_posts,
            "total_reports": total_reports,
            "total_plans": total_plans
        }
    })

# Moderation Endpoints (Admin Required)
@app.route("/api/admin/reports", methods=["GET"])
@admin_required
def get_reports():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, r.post_id, r.comment_id, r.reason, r.created_at,
               u.username AS reporter_username,
               p.content AS post_content, p.is_hidden AS post_is_hidden,
               c.comment AS comment_content
        FROM post_reports r
        JOIN users u ON r.reported_by = u.id
        LEFT JOIN community_posts p ON r.post_id = p.id
        LEFT JOIN post_comments c ON r.comment_id = c.id
        ORDER BY r.created_at DESC;
    """)
    reports = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"reports": reports})

@app.route("/api/admin/reports/<int:report_id>/action", methods=["POST"])
@admin_required
def act_on_report(report_id):
    data = request.get_json() or {}
    action = data.get("action")  # 'hide_post', 'delete_post', 'dismiss'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM post_reports WHERE id = ?;", (report_id,))
    report = cursor.fetchone()
    if not report:
        conn.close()
        return jsonify({"error": "Not Found", "message": "Report not found"}), 404

    if action == "hide_post" and report["post_id"]:
        cursor.execute("UPDATE community_posts SET is_hidden = 1 WHERE id = ?;", (report["post_id"],))
    elif action == "delete_post" and report["post_id"]:
        cursor.execute("DELETE FROM community_posts WHERE id = ?;", (report["post_id"],))
    elif action == "hide_comment" and report["comment_id"]:
        cursor.execute("UPDATE post_comments SET is_hidden = 1 WHERE id = ?;", (report["comment_id"],))

    cursor.execute("DELETE FROM post_reports WHERE id = ?;", (report_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Report action '{action}' completed"})

@app.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_get_users():
    query = (request.args.get("q") or "").strip()
    conn = get_db_connection()
    cursor = conn.cursor()

    if query:
        clean_q = query.lstrip("@").strip()
        search_param = f"%{clean_q}%"
        cursor.execute("""
            SELECT u.id, u.username, u.display_name, u.email, u.avatar_url, u.bio, u.is_admin, u.is_active, u.created_at,
                   (SELECT COUNT(*) FROM recipes r WHERE r.user_id = u.id) AS recipe_count,
                   (SELECT COUNT(*) FROM community_posts cp WHERE cp.user_id = u.id) AS post_count,
                   (SELECT COUNT(*) FROM friendships f WHERE f.friend_id = u.id) AS follower_count
            FROM users u
            WHERE u.username LIKE ? OR u.display_name LIKE ? OR u.email LIKE ?
            ORDER BY u.id DESC
            LIMIT 50;
        """, (search_param, search_param, search_param))
    else:
        cursor.execute("""
            SELECT u.id, u.username, u.display_name, u.email, u.avatar_url, u.bio, u.is_admin, u.is_active, u.created_at,
                   (SELECT COUNT(*) FROM recipes r WHERE r.user_id = u.id) AS recipe_count,
                   (SELECT COUNT(*) FROM community_posts cp WHERE cp.user_id = u.id) AS post_count,
                   (SELECT COUNT(*) FROM friendships f WHERE f.friend_id = u.id) AS follower_count
            FROM users u
            ORDER BY u.id DESC
            LIMIT 50;
        """)

    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"users": users})


@app.route("/api/admin/users/<int:target_user_id>", methods=["DELETE"])
@admin_required
def admin_delete_user(target_user_id):
    current_user = get_authenticated_user()
    if current_user["id"] == target_user_id:
        return jsonify({"error": "Forbidden", "message": "Cannot delete your own admin account"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, is_admin FROM users WHERE id = ?;", (target_user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        return jsonify({"error": "Not Found", "message": "User not found"}), 404

    cursor.execute("DELETE FROM users WHERE id = ?;", (target_user_id,))
    conn.commit()
    conn.close()
    invalidate_user_sessions(user_id=target_user_id)
    return jsonify({"success": True, "message": f"User @{target['username']} has been permanently removed"})

@app.route("/api/admin/users/purge-offensive", methods=["POST"])
@admin_required
def admin_purge_offensive_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, display_name, bio, is_admin FROM users WHERE is_admin = 0;")
    users = cursor.fetchall()
    purged = []

    for u in users:
        has_prof_u, term_u = contains_profanity(u["username"])
        has_prof_d, term_d = contains_profanity(u["display_name"])
        has_prof_b, term_b = contains_profanity(u["bio"] or "")
        if has_prof_u or has_prof_d or has_prof_b:
            cursor.execute("DELETE FROM users WHERE id = ?;", (u["id"],))
            purged.append({
                "id": u["id"],
                "username": u["username"],
                "reason": term_u or term_d or term_b
            })

    conn.commit()
    conn.close()
    return jsonify({
        "success": True,
        "purged_count": len(purged),
        "purged_users": purged,
        "message": f"Purged {len(purged)} offensive accounts."
    })

@app.route("/api/admin/purge-stress-data", methods=["POST"])
@admin_required
def admin_purge_stress_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM users
        WHERE is_admin = 0 AND (
            bio LIKE '%Virtual load-testing%'
            OR username LIKE 'stress_chef_%'
            OR username LIKE 'chef_stress_%'
            OR (username LIKE 'chef_%' AND email LIKE '%@comecook.app' AND bio LIKE '%Virtual%')
        );
    """)
    ids = [r["id"] for r in cursor.fetchall()]
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        cursor.execute(f"DELETE FROM users WHERE id IN ({placeholders});", ids)
    
    # Always clean orphaned test artifacts and resync counts
    cursor.execute("DELETE FROM login_attempts WHERE username LIKE 'stress_%' OR username LIKE 'chef_%';")
    cursor.execute("DELETE FROM hashtag_references WHERE entity_type = 'post' AND entity_id NOT IN (SELECT id FROM community_posts);")
    cursor.execute("DELETE FROM hashtag_references WHERE entity_type = 'recipe' AND entity_id NOT IN (SELECT id FROM recipes);")
    cursor.execute("DELETE FROM hashtag_references WHERE entity_type = 'review' AND entity_id NOT IN (SELECT id FROM recipe_reviews);")
    cursor.execute("UPDATE hashtags SET usage_count = (SELECT COUNT(*) FROM hashtag_references hr WHERE hr.hashtag_id = hashtags.id);")
    cursor.execute("DELETE FROM hashtags WHERE usage_count <= 0 OR id NOT IN (SELECT DISTINCT hashtag_id FROM hashtag_references);")
    cursor.execute("UPDATE recipes SET fork_count = (SELECT COUNT(*) FROM recipes r2 WHERE r2.parent_recipe_id = recipes.id);")
    conn.commit()
    cursor.execute("VACUUM;")
    conn.close()

    return jsonify({
        "success": True,
        "message": f"Successfully cleaned all stress test accounts, synced hashtag counts, and purged unused hashtags! (Purged {len(ids)} users)",
        "purged_count": len(ids)
    })


# ==============================================================================
# MEAL PLANNER
# ==============================================================================

@app.route("/api/planner", methods=["GET"])
@require_auth
def get_planner():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = ["p.user_id = ?"]
    params = [g.current_user["id"]]

    if start_date:
        conditions.append("p.plan_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("p.plan_date <= ?")
        params.append(end_date)

    where_clause = "WHERE " + " AND ".join(conditions)

    cursor.execute(f"""
        SELECT p.*, 
               r.title AS recipe_title, 
               r.image_url AS recipe_image, 
               r.prep_time_min, 
               r.cook_time_min,
               r.servings AS recipe_servings,
               r.cuisine AS recipe_cuisine,
               r.difficulty AS recipe_difficulty,
               r.ingredients_json AS recipe_ingredients,
               r.tags_json AS recipe_tags
        FROM planner p
        LEFT JOIN recipes r ON p.recipe_id = r.id
        {where_clause}
        ORDER BY p.plan_date ASC, 
                 CASE p.meal_type 
                    WHEN 'breakfast' THEN 1 
                    WHEN 'lunch' THEN 2 
                    WHEN 'dinner' THEN 3 
                    WHEN 'snack' THEN 4 
                    ELSE 5 
                 END;
    """, params)
    
    rows = cursor.fetchall()
    conn.close()

    plans = []
    for r in rows:
        item = dict(r)
        # Parse JSON fields safely
        if item.get("recipe_ingredients") and isinstance(item["recipe_ingredients"], str):
            try:
                item["recipe_ingredients"] = json.loads(item["recipe_ingredients"])
            except Exception:
                item["recipe_ingredients"] = []
        if item.get("recipe_tags") and isinstance(item["recipe_tags"], str):
            try:
                item["recipe_tags"] = json.loads(item["recipe_tags"])
            except Exception:
                item["recipe_tags"] = []
        item["recipe_time"] = (item.get("prep_time_min") or 0) + (item.get("cook_time_min") or 0)
        plans.append(item)

    return jsonify({"planner": plans})

@app.route("/api/planner", methods=["POST"])
@require_auth
def add_planner_item():
    data = request.get_json() or {}
    plan_date = (data.get("plan_date") or "").strip()
    meal_type = (data.get("meal_type") or "dinner").strip().lower()
    recipe_id = data.get("recipe_id")
    custom_title = (data.get("custom_title") or "").strip()
    notes = (data.get("notes") or "").strip()

    if not plan_date or not meal_type:
        return jsonify({"error": "Validation Error", "message": "Plan date and meal type required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO planner (user_id, plan_date, meal_type, recipe_id, custom_title, notes)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (g.current_user["id"], plan_date, meal_type, recipe_id, custom_title, notes))
    plan_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({"success": True, "plan_id": plan_id, "message": "Meal planned"}), 201

@app.route("/api/planner/<int:plan_id>", methods=["DELETE"])
@require_auth
def delete_planner_item(plan_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Security Mitigation: IDOR Protection
    cursor.execute("DELETE FROM planner WHERE id = ? AND user_id = ?;", (plan_id, g.current_user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Planned meal removed"})

@app.route("/api/planner/grocery-list", methods=["GET"])
@require_auth
def get_planner_grocery_list():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = ["p.user_id = ?", "p.recipe_id IS NOT NULL"]
    params = [g.current_user["id"]]

    if start_date:
        conditions.append("p.plan_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("p.plan_date <= ?")
        params.append(end_date)

    where_clause = "WHERE " + " AND ".join(conditions)

    cursor.execute(f"""
        SELECT p.plan_date, p.meal_type, r.title AS recipe_title, r.ingredients_json AS ingredients
        FROM planner p
        JOIN recipes r ON p.recipe_id = r.id
        {where_clause}
        ORDER BY p.plan_date ASC;
    """, params)

    rows = cursor.fetchall()
    conn.close()

    categorized = {
        "Produce": [],
        "Dairy": [],
        "Meat": [],
        "Bakery": [],
        "Spices": [],
        "Pantry": []
    }
    
    total_items = 0
    for row in rows:
        raw_ings = row["ingredients"]
        if not raw_ings:
            continue
        try:
            ings_list = json.loads(raw_ings) if isinstance(raw_ings, str) else raw_ings
        except Exception:
            ings_list = []

        for ing in ings_list:
            if isinstance(ing, dict) and ing.get("name"):
                name = ing.get("name", "").strip()
                amount = str(ing.get("amount", "")).strip()
                unit = str(ing.get("unit", "")).strip()
                cat = ing.get("category", "Pantry")
                if cat not in categorized:
                    cat = "Pantry"
                
                parts = [p for p in [amount, unit, name] if p]
                display_str = " ".join(parts)
                categorized[cat].append({
                    "name": name,
                    "amount": amount,
                    "unit": unit,
                    "display": display_str,
                    "recipe_title": row["recipe_title"],
                    "plan_date": row["plan_date"]
                })
                total_items += 1

    return jsonify({
        "success": True,
        "start_date": start_date,
        "end_date": end_date,
        "total_items": total_items,
        "categories": categorized
    })

@app.route("/api/planner/clear-week", methods=["POST"])
@require_auth
def clear_planner_week():
    data = request.get_json() or {}
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    if not start_date or not end_date:
        return jsonify({"error": "Validation Error", "message": "start_date and end_date required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM planner
        WHERE user_id = ? AND plan_date >= ? AND plan_date <= ?;
    """, (g.current_user["id"], start_date, end_date))
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return jsonify({"success": True, "deleted_count": deleted_count, "message": f"Cleared {deleted_count} planned meals"})


# ==============================================================================
# IMAGE UPLOADS WITH SERVER-SIDE PILLOW PROCESSING & TOKENIZATION
# ==============================================================================

@app.route("/api/upload", methods=["POST"])
@require_auth
def upload_image():
    if "image" not in request.files:
        return jsonify({"error": "Validation Error", "message": "No image file provided"}), 400

    file = request.files["image"]
    if not file or file.filename == "":
        return jsonify({"error": "Validation Error", "message": "Empty file"}), 400

    try:
        # Verify and sanitize with Pillow
        image_bytes = file.read()
        image = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB (handles RGBA / PNG transparency / CMYK)
        if image.mode in ("RGBA", "P"):
            rgb_image = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "RGBA":
                rgb_image.paste(image, mask=image.split()[3])
            else:
                rgb_image.paste(image)
            image = rgb_image
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Downsample to max 1280x1280 preserving aspect ratio
        max_dim = 1280
        image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        # Generate secure randomized hex token filename in modern WebP format
        hex_token = secrets.token_hex(16)
        filename = f"{hex_token}.webp"
        save_path = os.path.join(UPLOAD_FOLDER, filename)

        # Save as WebP with quality 85 for 30-50% smaller payloads
        image.save(save_path, format="WEBP", quality=85, method=4)

        image_url = f"/uploads/{filename}"
        return jsonify({"success": True, "url": image_url, "filename": filename})
    except Exception as e:
        return jsonify({"error": "Upload Error", "message": f"Failed to process image: {str(e)}"}), 400


# ==============================================================================
# ERROR HANDLERS
# ==============================================================================

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not Found", "message": "API endpoint does not exist"}), 404
    return send_from_directory(app.static_folder, "index.html")

@app.errorhandler(413)
def request_entity_too_large(e):
    return jsonify({"error": "Payload Too Large", "message": "Uploaded file exceeds maximum limit"}), 413

@app.errorhandler(500)
def server_error(e):
    import traceback
    traceback.print_exc()
    original_err = getattr(e, "original_exception", e)
    return jsonify({"error": "Internal Server Error", "message": str(original_err)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
