#!/usr/bin/env python3
"""
Cooked - Made for Cooks, By Cooks
Server Runner Script
"""

import os
from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("FLASK_DEBUG", "True").lower() in ("1", "true", "yes")

    print(f"🍳 Cooked platform starting on http://localhost:{port}")
    app.run(host=host, port=port, debug=debug)
