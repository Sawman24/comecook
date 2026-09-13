#!/usr/bin/env python3
"""
Cooked - Database Reset & Initialization Tool
Wipes the existing SQLite database and re-creates fresh tables with default stations.
Guarantees 0 users so the very first registered account becomes the Owner/Admin.
"""

import os
import sys
import sqlite3

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import DB_PATH, get_db_connection, init_db

def wipe_and_reset_database():
    db_path = os.environ.get("COOKED_DB_PATH", DB_PATH)
    print(f"🧹 Preparing database wipe for: {db_path}")

    # Remove main db file and SQLite WAL/SHM temporary files
    for suffix in ["", "-wal", "-shm", "-journal"]:
        file_to_remove = db_path + suffix
        if os.path.exists(file_to_remove):
            try:
                os.remove(file_to_remove)
                print(f"  ✓ Removed: {file_to_remove}")
            except Exception as e:
                print(f"  ⚠️ Could not remove {file_to_remove}: {e}")

    # Initialize fresh schema & default stations
    print("🔨 Initializing fresh database schema and stations...")
    init_db()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM users;")
    user_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM stations;")
    station_count = cursor.fetchone()["count"]
    conn.close()

    print(f"  ✓ Database successfully initialized!")
    print(f"  ✓ Active Users: {user_count} (The first registered user will become Owner / Admin)")
    print(f"  ✓ Culinary Kitchen Stations: {station_count} ready")
    print("🎉 Database wipe and reset complete!\n")

if __name__ == "__main__":
    wipe_and_reset_database()
