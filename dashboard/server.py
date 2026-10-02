"""Local read-only(ish) dashboard over the trading ledger -- mirrors the
Deposits / Trade Log / Daily Summary / Dashboard sheets of the user's
spreadsheet. Runs as its own process; safe to run alongside main.py, which
writes to the same ledger.db.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request, send_from_directory

from kalshi_bot.ledger import Ledger

app = Flask(__name__, static_folder="static")
ledger = Ledger()


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/dashboard")
def api_dashboard():
    mode = request.args.get("mode") or None
    return jsonify(ledger.get_dashboard_stats(mode=mode))


@app.get("/api/trades")
def api_trades():
    mode = request.args.get("mode") or None
    limit = int(request.args.get("limit", 500))
    rows = ledger.get_trade_log(mode=mode, limit=limit)
    return jsonify([dict(r) for r in rows])


@app.get("/api/daily")
def api_daily():
    mode = request.args.get("mode") or None
    return jsonify(ledger.get_daily_summary(mode=mode))


@app.get("/api/deposits")
def api_deposits():
    mode = request.args.get("mode") or None
    rows = ledger.get_deposits(mode=mode)
    return jsonify([dict(r) for r in rows])


@app.post("/api/deposits")
def api_add_deposit():
    # Manual deposits entered through the UI are real money into the real
    # account -- paper mode's seed cash is recorded separately by PaperBroker.
    body = request.get_json(force=True)
    amount = float(body["amount"])
    source = body.get("source", "")
    deposit_id = ledger.record_deposit(amount=amount, source=source, mode="live")
    return jsonify({"id": deposit_id}), 201


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
