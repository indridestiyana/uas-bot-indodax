"""
=============================================================================
ENDPOINT MEMBACA STATE & LOG UNTUK DASHBOARD (api/state.py)
UAS Algoritma Trading - Bot Dry Run Indodax di Vercel
Mahasiswa   : Indri Destiyana (NIM: 25120200007)
=============================================================================
Menyediakan data JSON state forward test dan backtest ke dashboard web.
=============================================================================
"""

import os
import sys
import json
from http.server import BaseHTTPRequestHandler

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from engine.storage import BotStorage

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        storage = BotStorage()
        state = storage.load_state()

        # Baca juga data hasil backtest jika ada
        bt_path = os.path.join(ROOT_DIR, "data", "backtest_results.json")
        bt_data = {}
        if os.path.exists(bt_path):
            try:
                with open(bt_path, "r", encoding="utf-8") as f:
                    bt_data = json.load(f)
            except Exception:
                pass

        payload = {
            "forward_test": state,
            "backtest": bt_data
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))
