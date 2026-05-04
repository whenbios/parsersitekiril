import json
import sqlite3
import threading
from pathlib import Path

from app.schemas import EnrichedRow, JobStatusResponse


class JobStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  status TEXT NOT NULL,
                  total_items INTEGER NOT NULL,
                  queued_items INTEGER NOT NULL,
                  processing_items INTEGER NOT NULL,
                  done_items INTEGER NOT NULL,
                  failed_items INTEGER NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS job_items (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  job_id INTEGER NOT NULL,
                  row_index INTEGER NOT NULL,
                  company_name TEXT NOT NULL,
                  workua_url TEXT NOT NULL,
                  status TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS job_results (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  job_id INTEGER NOT NULL,
                  row_index INTEGER,
                  payload TEXT NOT NULL
                )
                """
            )
            self.connection.commit()

    def create_job(self, *, total_items: int) -> int:
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                INSERT INTO jobs (status, total_items, queued_items, processing_items, done_items, failed_items)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("queued", total_items, total_items, 0, 0, 0),
            )
            self.connection.commit()
            return int(cursor.lastrowid)

    def set_job_status(self, job_id: int, status: str) -> None:
        with self.lock:
            self.connection.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (status, job_id),
            )
            self.connection.commit()

    def add_job_item(self, job_id: int, row_index: int, company_name: str, workua_url: str, status: str) -> None:
        with self.lock:
            self.connection.execute(
                """
                INSERT INTO job_items (job_id, row_index, company_name, workua_url, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, row_index, company_name, workua_url, status),
            )
            self.connection.commit()

    def update_job_item_status(self, job_id: int, row_index: int, status: str) -> None:
        with self.lock:
            self.connection.execute(
                "UPDATE job_items SET status = ? WHERE job_id = ? AND row_index = ?",
                (status, job_id, row_index),
            )
            self.connection.commit()

    def update_job_items_status(self, job_id: int, row_indices: list[int], status: str) -> None:
        if not row_indices:
            return
        placeholders = ",".join("?" for _ in row_indices)
        with self.lock:
            self.connection.execute(
                f"UPDATE job_items SET status = ? WHERE job_id = ? AND row_index IN ({placeholders})",
                [status, job_id, *row_indices],
            )
            self.connection.commit()

    def save_job_result(self, job_id: int, result: EnrichedRow) -> None:
        with self.lock:
            self.connection.execute(
                "DELETE FROM job_results WHERE job_id = ? AND row_index = ?",
                (job_id, result.row_index),
            )
            self.connection.execute(
                "INSERT INTO job_results (job_id, row_index, payload) VALUES (?, ?, ?)",
                (job_id, result.row_index, json.dumps(result.model_dump())),
            )
            self.connection.commit()

    def finalize_job(self, job_id: int, status: str, done_items: int, failed_items: int) -> None:
        with self.lock:
            row = self.connection.execute(
                "SELECT total_items FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            total_items = int(row["total_items"]) if row else 0
            processing_items = max(0, total_items - done_items - failed_items)
            self.connection.execute(
                """
                UPDATE jobs
                SET status = ?, processing_items = ?, done_items = ?, failed_items = ?
                WHERE id = ?
                """,
                (status, processing_items, done_items, failed_items, job_id),
            )
            self.connection.commit()

    def get_total_items(self, job_id: int) -> int:
        with self.lock:
            row = self.connection.execute(
                "SELECT total_items FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            return int(row["total_items"]) if row else 0

    def get_job_status(self, job_id: int) -> JobStatusResponse | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT id, status, total_items FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            status_rows = self.connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM job_items
                WHERE job_id = ?
                GROUP BY status
                """,
                (job_id,),
            ).fetchall()
            counts = {status_row["status"]: int(status_row["count"]) for status_row in status_rows}
            return JobStatusResponse(
                job_id=int(row["id"]),
                status=row["status"],
                total_items=int(row["total_items"]),
                queued_items=counts.get("queued", 0),
                processing_items=counts.get("processing", 0),
                done_items=counts.get("done", 0) + counts.get("partial", 0),
                failed_items=counts.get("failed", 0),
            )

    def get_job_results(self, job_id: int) -> list[EnrichedRow] | None:
        with self.lock:
            exists = self.connection.execute(
                "SELECT 1 FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if exists is None:
                return None
            rows = self.connection.execute(
                "SELECT payload FROM job_results WHERE job_id = ? ORDER BY row_index ASC",
                (job_id,),
            ).fetchall()
            return [EnrichedRow.model_validate(json.loads(row["payload"])) for row in rows]
