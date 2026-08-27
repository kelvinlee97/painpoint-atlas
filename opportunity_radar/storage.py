import json
import sqlite3
from pathlib import Path

from .models import App, Cluster, Evidence, Opportunity, Review
from .redaction import sanitize_public_text


PUBLIC_REDACTION_VERSION = 3


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS apps (
                id INTEGER PRIMARY KEY,
                store TEXT NOT NULL,
                external_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                rank INTEGER NOT NULL,
                url TEXT NOT NULL,
                description TEXT,
                developer TEXT,
                price TEXT,
                UNIQUE(store, external_id)
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY,
                store TEXT NOT NULL,
                external_id TEXT NOT NULL,
                app_external_id TEXT NOT NULL,
                rating INTEGER NOT NULL,
                title TEXT,
                body TEXT NOT NULL,
                published_at TEXT,
                version TEXT,
                source_url TEXT NOT NULL,
                UNIQUE(store, external_id)
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY,
                review_id TEXT NOT NULL UNIQUE,
                pain TEXT NOT NULL,
                affected_user TEXT NOT NULL,
                context TEXT NOT NULL,
                severity INTEGER NOT NULL,
                paid_signal INTEGER NOT NULL,
                quote TEXT NOT NULL,
                confidence REAL NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS clusters (
                id INTEGER PRIMARY KEY,
                label TEXT NOT NULL,
                summary TEXT NOT NULL,
                affected_user TEXT NOT NULL,
                validation_action TEXT NOT NULL,
                evidence_ids TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY,
                cluster_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                summary TEXT NOT NULL,
                affected_user TEXT NOT NULL,
                validation_action TEXT NOT NULL,
                evidence_ids TEXT NOT NULL,
                score REAL NOT NULL,
                review_count INTEGER NOT NULL,
                app_count INTEGER NOT NULL,
                average_severity REAL NOT NULL,
                average_paid_signal REAL NOT NULL,
                FOREIGN KEY(cluster_id) REFERENCES clusters(id)
            )
            """
        )
        for table, column, definition in (
            ("apps", "description", "TEXT"),
            ("apps", "developer", "TEXT"),
            ("apps", "price", "TEXT"),
            ("opportunities", "failure_stage", "TEXT NOT NULL DEFAULT ''"),
            ("opportunities", "root_cause", "TEXT NOT NULL DEFAULT ''"),
            ("opportunities", "user_consequence", "TEXT NOT NULL DEFAULT ''"),
            (
                "opportunities",
                "commercial_implication",
                "TEXT NOT NULL DEFAULT ''",
            ),
            ("opportunities", "decision", "TEXT NOT NULL DEFAULT ''"),
            (
                "opportunities",
                "analysis_confidence",
                "REAL NOT NULL DEFAULT 0",
            ),
        ):
            self._ensure_column(table, column, definition)
        self._migrate_public_text()
        self.connection.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")
        }
        if column not in columns:
            self.connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )

    def _migrate_public_text(self) -> None:
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version >= PUBLIC_REDACTION_VERSION:
            return

        # ponytail: one full scan for the small committed database; batch this migration if it grows large.
        for table, columns in (
            ("apps", ("name", "category", "description", "developer", "price")),
            ("reviews", ("title", "body")),
            ("evidence", ("pain", "affected_user", "context", "quote")),
            (
                "clusters",
                ("label", "summary", "affected_user", "validation_action"),
            ),
            (
                "opportunities",
                (
                    "label",
                    "summary",
                    "affected_user",
                    "validation_action",
                    "failure_stage",
                    "root_cause",
                    "user_consequence",
                    "commercial_implication",
                    "decision",
                ),
            ),
            ("runs", ("details",)),
        ):
            selected = ", ".join(columns)
            updates = ", ".join(f"{column} = ?" for column in columns)
            for row in self.connection.execute(
                f"SELECT id, {selected} FROM {table}"
            ).fetchall():
                original = row[1:]
                sanitized = tuple(sanitize_public_text(value) for value in original)
                if sanitized != original:
                    self.connection.execute(
                        f"UPDATE {table} SET {updates} WHERE id = ?",
                        (*sanitized, row[0]),
                    )
        self.connection.execute(f"PRAGMA user_version = {PUBLIC_REDACTION_VERSION}")

    def insert_app(self, app: App) -> bool:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO apps
            (store, external_id, name, category, rank, url, description, developer, price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                app.store,
                app.external_id,
                sanitize_public_text(app.name),
                sanitize_public_text(app.category),
                app.rank,
                app.url,
                sanitize_public_text(app.description),
                sanitize_public_text(app.developer),
                sanitize_public_text(app.price),
            ),
        )
        self.connection.execute(
            """
            UPDATE apps
            SET description = COALESCE(?, description),
                developer = COALESCE(?, developer),
                price = COALESCE(?, price)
            WHERE store = ? AND external_id = ?
            """,
            (
                sanitize_public_text(app.description),
                sanitize_public_text(app.developer),
                sanitize_public_text(app.price),
                app.store,
                app.external_id,
            ),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def insert_review(self, review: Review) -> bool:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO reviews
            (store, external_id, app_external_id, rating, title, body,
             published_at, version, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.store,
                review.external_id,
                review.app_external_id,
                review.rating,
                sanitize_public_text(review.title),
                sanitize_public_text(review.body),
                review.published_at,
                review.version,
                review.source_url,
            ),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def count_reviews(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM reviews").fetchone()
        return int(row[0])

    def insert_evidence(self, evidence: Evidence) -> bool:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO evidence
            (review_id, pain, affected_user, context, severity, paid_signal,
             quote, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence.review_id,
                sanitize_public_text(evidence.pain),
                sanitize_public_text(evidence.affected_user),
                sanitize_public_text(evidence.context),
                evidence.severity,
                evidence.paid_signal,
                sanitize_public_text(evidence.quote),
                evidence.confidence,
            ),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def count_apps(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM apps").fetchone()
        return int(row[0])

    def count_evidence(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()
        return int(row[0])

    def get_reviews(self) -> list[Review]:
        rows = self.connection.execute(
            """
            SELECT store, external_id, app_external_id, rating, title, body,
                   published_at, version, source_url
            FROM reviews ORDER BY id
            """
        ).fetchall()
        return [
            Review(
                *row[:4],
                sanitize_public_text(row[4]),
                sanitize_public_text(row[5]),
                *row[6:],
            )
            for row in rows
        ]

    def get_apps(self) -> list[App]:
        rows = self.connection.execute(
            """
            SELECT store, external_id, name, category, rank, url,
                   description, developer, price
            FROM apps ORDER BY id
            """
        ).fetchall()
        return [
            App(
                row[0],
                row[1],
                sanitize_public_text(row[2]),
                sanitize_public_text(row[3]),
                row[4],
                row[5],
                sanitize_public_text(row[6]),
                sanitize_public_text(row[7]),
                sanitize_public_text(row[8]),
            )
            for row in rows
        ]

    def get_evidence(self) -> list[Evidence]:
        rows = self.connection.execute(
            """
            SELECT review_id, pain, affected_user, context, severity, paid_signal,
                   quote, confidence
            FROM evidence ORDER BY id
            """
        ).fetchall()
        return [
            Evidence(
                row[0],
                sanitize_public_text(row[1]),
                sanitize_public_text(row[2]),
                sanitize_public_text(row[3]),
                row[4],
                row[5],
                sanitize_public_text(row[6]),
                row[7],
            )
            for row in rows
        ]

    def insert_cluster(self, cluster: Cluster) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO clusters
            (label, summary, affected_user, validation_action, evidence_ids)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                sanitize_public_text(cluster.label),
                sanitize_public_text(cluster.summary),
                sanitize_public_text(cluster.affected_user),
                sanitize_public_text(cluster.validation_action),
                json.dumps(cluster.evidence_ids),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def insert_opportunity(self, cluster_id: int, opportunity: Opportunity) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO opportunities
            (cluster_id, label, summary, affected_user, validation_action,
             evidence_ids, score, review_count, app_count, average_severity,
             average_paid_signal, failure_stage, root_cause, user_consequence,
             commercial_implication, decision, analysis_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cluster_id,
                sanitize_public_text(opportunity.label),
                sanitize_public_text(opportunity.summary),
                sanitize_public_text(opportunity.affected_user),
                sanitize_public_text(opportunity.validation_action),
                json.dumps(opportunity.evidence_ids),
                opportunity.score,
                opportunity.review_count,
                opportunity.app_count,
                opportunity.average_severity,
                opportunity.average_paid_signal,
                sanitize_public_text(opportunity.failure_stage),
                sanitize_public_text(opportunity.root_cause),
                sanitize_public_text(opportunity.user_consequence),
                sanitize_public_text(opportunity.commercial_implication),
                sanitize_public_text(opportunity.decision),
                opportunity.analysis_confidence,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def insert_run(self, kind: str, status: str, details: dict) -> int:
        cursor = self.connection.execute(
            "INSERT INTO runs (kind, status, details) VALUES (?, ?, ?)",
            (
                kind,
                status,
                sanitize_public_text(json.dumps(details, ensure_ascii=False)),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def count_clusters(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM clusters").fetchone()
        return int(row[0])

    def count_opportunities(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM opportunities").fetchone()
        return int(row[0])

    def clear_analysis(self) -> None:
        self.connection.execute("DELETE FROM opportunities")
        self.connection.execute("DELETE FROM clusters")
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
