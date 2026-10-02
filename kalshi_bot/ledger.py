from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "ledger.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL DEFAULT 'live',  -- 'live' for real money, 'paper' for the simulation's seed cash
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    source TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,                  -- 'paper' or 'live'
    opened_at TEXT NOT NULL,
    ticker TEXT NOT NULL,
    market_title TEXT NOT NULL DEFAULT '',  -- human-readable label, e.g. "Oil Price (WTI) on Oct 1, 2026?"
    event_ticker TEXT NOT NULL DEFAULT '',  -- groups correlated strikes on the same underlying
    side TEXT NOT NULL,                  -- 'bid' (bought yes) or 'ask' (bought no)
    target_probability REAL NOT NULL,    -- limit price paid, 0-1
    count REAL NOT NULL,
    cost REAL NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'Open', -- Open / Won / Lost / Cashed Out
    payout REAL,
    pnl REAL,
    return_pct REAL,
    settled_at TEXT
);
"""


class Ledger:
    """Mirrors the shape of the user's own trade-tracking spreadsheet:
    a Deposits table and a Trade Log table, with Daily Summary / Dashboard
    numbers computed from them the same way the spreadsheet's formulas do.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """CREATE TABLE IF NOT EXISTS doesn't add new columns to an existing
        table, so handle any columns added after the initial schema here."""
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(trades)")}
        if "market_title" not in existing:
            conn.execute("ALTER TABLE trades ADD COLUMN market_title TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- writes ----

    def record_deposit(self, amount: float, source: str = "", date: Optional[str] = None,
                        mode: str = "live") -> int:
        date = date or datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO deposits (mode, date, amount, source) VALUES (?, ?, ?, ?)",
                (mode, date, amount, source),
            )
            return cur.lastrowid

    def record_trade_open(self, mode: str, ticker: str, side: str, price: float,
                           count: float, reason: str, event_ticker: str = "",
                           market_title: str = "") -> int:
        cost = price * count
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO trades
                   (mode, opened_at, ticker, market_title, event_ticker, side,
                    target_probability, count, cost, reason, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Open')""",
                (mode, datetime.now(timezone.utc).isoformat(), ticker, market_title or ticker,
                 event_ticker, side, price, count, cost, reason),
            )
            return cur.lastrowid

    def record_settlement(self, trade_id: int, status: str, payout: float) -> None:
        """status: 'Won', 'Lost', or 'Cashed Out'."""
        with self._connect() as conn:
            row = conn.execute("SELECT cost FROM trades WHERE id = ?", (trade_id,)).fetchone()
            if row is None:
                return
            cost = row["cost"]
            pnl = payout - cost
            return_pct = (pnl / cost) if cost else 0.0
            conn.execute(
                """UPDATE trades SET status = ?, payout = ?, pnl = ?, return_pct = ?, settled_at = ?
                   WHERE id = ?""",
                (status, payout, pnl, return_pct, datetime.now(timezone.utc).isoformat(), trade_id),
            )

    # ---- reads ----

    def get_open_trades(self, mode: Optional[str] = None) -> list[sqlite3.Row]:
        with self._connect() as conn:
            if mode:
                return conn.execute(
                    "SELECT * FROM trades WHERE status = 'Open' AND mode = ? ORDER BY id", (mode,)
                ).fetchall()
            return conn.execute("SELECT * FROM trades WHERE status = 'Open' ORDER BY id").fetchall()

    def get_trade_log(self, mode: Optional[str] = None, limit: int = 500) -> list[sqlite3.Row]:
        with self._connect() as conn:
            if mode:
                return conn.execute(
                    "SELECT * FROM trades WHERE mode = ? ORDER BY id DESC LIMIT ?", (mode, limit)
                ).fetchall()
            return conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def get_deposits(self, mode: Optional[str] = None) -> list[sqlite3.Row]:
        with self._connect() as conn:
            if mode:
                return conn.execute(
                    "SELECT * FROM deposits WHERE mode = ? ORDER BY date", (mode,)
                ).fetchall()
            return conn.execute("SELECT * FROM deposits ORDER BY date").fetchall()

    def get_daily_summary(self, mode: Optional[str] = None) -> list[dict]:
        trades = self.get_trade_log(mode=mode, limit=100000)
        deposits = self.get_deposits(mode=mode)
        deposits_by_day: dict[str, float] = {}
        for d in deposits:
            day = d["date"][:10]
            deposits_by_day[day] = deposits_by_day.get(day, 0.0) + d["amount"]

        by_day: dict[str, list] = {}
        for t in trades:
            day = t["opened_at"][:10]
            by_day.setdefault(day, []).append(t)

        days = sorted(set(by_day) | set(deposits_by_day))
        rows = []
        running_balance = 0.0
        for day_num, day in enumerate(days, start=1):
            day_trades = by_day.get(day, [])
            deposits_added = deposits_by_day.get(day, 0.0)
            daily_pnl = sum(t["pnl"] or 0.0 for t in day_trades)
            wins = sum(1 for t in day_trades if t["status"] == "Won")
            losses = sum(1 for t in day_trades if t["status"] == "Lost")
            resolved = wins + losses
            # Starting balance includes that day's own deposit (matches the
            # user's spreadsheet convention: a deposit posted on day 1 makes
            # day 1's starting balance equal the deposit, not $0 before it).
            starting_balance = running_balance + deposits_added
            running_balance = starting_balance + daily_pnl
            rows.append({
                "date": day,
                "day_num": day_num,
                "trades_that_day": len(day_trades),
                "starting_balance": round(starting_balance, 2),
                "deposits_added": round(deposits_added, 2),
                "ending_balance": round(running_balance, 2),
                "daily_pnl": round(daily_pnl, 2),
                "daily_return_pct": round(daily_pnl / starting_balance, 4) if starting_balance else 0.0,
                "win_rate_that_day": round(wins / resolved, 4) if resolved else None,
                "wins_that_day": wins,
                "losses_that_day": losses,
            })
        return rows

    def get_dashboard_stats(self, mode: Optional[str] = None) -> dict:
        trades = self.get_trade_log(mode=mode, limit=100000)
        deposits = self.get_deposits(mode=mode)

        total_deposited = sum(d["amount"] for d in deposits)
        resolved = [t for t in trades if t["status"] in ("Won", "Lost", "Cashed Out")]
        total_trading_profit = sum(t["pnl"] or 0.0 for t in resolved)
        current_balance = total_deposited + total_trading_profit

        won = sum(1 for t in trades if t["status"] == "Won")
        lost = sum(1 for t in trades if t["status"] == "Lost")
        cashed_out = sum(1 for t in trades if t["status"] == "Cashed Out")
        open_count = sum(1 for t in trades if t["status"] == "Open")

        profitable = sum(1 for t in resolved if (t["pnl"] or 0) > 0)
        losing = sum(1 for t in resolved if (t["pnl"] or 0) < 0)
        win_rate = profitable / len(resolved) if resolved else None

        wins_pnl = [t["pnl"] for t in resolved if (t["pnl"] or 0) > 0]
        losses_pnl = [t["pnl"] for t in resolved if (t["pnl"] or 0) < 0]
        avg_win = sum(wins_pnl) / len(wins_pnl) if wins_pnl else 0.0
        avg_loss = sum(losses_pnl) / len(losses_pnl) if losses_pnl else 0.0

        avg_target_prob = (
            sum(t["target_probability"] for t in trades) / len(trades) if trades else None
        )

        daily = self.get_daily_summary(mode=mode)
        days_active = len([d for d in daily if d["trades_that_day"] > 0])
        avg_daily_return = (
            sum(d["daily_return_pct"] for d in daily if d["starting_balance"]) /
            len([d for d in daily if d["starting_balance"]])
        ) if any(d["starting_balance"] for d in daily) else 0.0

        return {
            "total_deposited": round(total_deposited, 2),
            "total_trading_profit": round(total_trading_profit, 2),
            "current_balance": round(current_balance, 2),
            "overall_return_pct": round(total_trading_profit / total_deposited, 4) if total_deposited else None,
            "days_active": days_active,
            "avg_daily_return_pct": round(avg_daily_return, 4),
            "total_trades_logged": len(trades),
            "open": open_count,
            "won": won,
            "lost": lost,
            "cashed_out": cashed_out,
            "profitable_trades": profitable,
            "losing_trades": losing,
            "overall_win_rate": round(win_rate, 4) if win_rate is not None else None,
            "avg_win_dollars": round(avg_win, 4),
            "avg_loss_dollars": round(avg_loss, 4),
            "avg_target_probability": round(avg_target_prob, 4) if avg_target_prob is not None else None,
        }
