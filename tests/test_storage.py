import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


class StorageTests(unittest.TestCase):
    def test_public_text_is_redacted_on_insert_and_legacy_migration(self):
        from opportunity_radar.models import App, Evidence, Review
        from opportunity_radar.storage import Database, PUBLIC_REDACTION_VERSION

        fake_secret = "sk-" + "testtokenabcdefghijklmnop"
        raw = (
            "Contact test@example.com, visit https://private.example/u/alice, "
            f"call +1 555-123-4567, or message @alice; {fake_secret}."
        )
        review = Review(
            "google_play",
            "review-private",
            "com.example.app",
            1,
            raw,
            raw,
            "2026-08-18",
            None,
            "https://example.test/review-private",
        )
        evidence = Evidence(
            "google_play:review-private",
            raw,
            raw,
            raw,
            4,
            2,
            raw,
            0.9,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "atlas.sqlite3"
            database = Database(str(path))
            database.insert_app(
                App(
                    "google_play",
                    "com.example.app",
                    raw,
                    raw,
                    1,
                    "https://example.test/app",
                    raw,
                    raw,
                    "Free",
                )
            )
            database.insert_review(review)
            database.insert_evidence(evidence)
            self.assertNotIn("test@example.com", database.get_apps()[0].description)
            stored_review = database.get_reviews()[0]
            stored_evidence = database.get_evidence()[0]
            stored_app = database.get_apps()[0]
            self.assertIn("[redacted-email]", stored_review.body)
            self.assertIn("[redacted-secret]", stored_review.body)
            self.assertNotIn("test@example.com", stored_review.body)
            self.assertNotIn("test@example.com", stored_app.name)
            self.assertNotIn("test@example.com", stored_app.price)
            self.assertIn("[redacted-phone]", stored_evidence.quote)
            self.assertIn("[redacted-url]", stored_evidence.quote)
            database.insert_run("test", "failed", {"error": raw})
            stored_details = database.connection.execute(
                "SELECT details FROM runs"
            ).fetchone()[0]
            self.assertNotIn("test@example.com", stored_details)
            database.close()

            connection = sqlite3.connect(path)
            connection.execute(
                "UPDATE reviews SET title = ?, body = ? WHERE external_id = ?",
                (raw, raw, "review-private"),
            )
            connection.execute(
                "UPDATE evidence SET pain = ?, quote = ? WHERE review_id = ?",
                (raw, raw, "google_play:review-private"),
            )
            connection.execute(
                "UPDATE apps SET description = ?, developer = ? WHERE external_id = ?",
                (raw, raw, "com.example.app"),
            )
            connection.execute(
                "UPDATE apps SET name = ?, category = ?, price = ? WHERE external_id = ?",
                (raw, raw, raw, "com.example.app"),
            )
            connection.execute(
                "UPDATE runs SET details = ?",
                (json.dumps({"error": raw}, ensure_ascii=False),),
            )
            connection.execute("PRAGMA user_version = 0")
            connection.commit()
            connection.close()

            migrated = Database(str(path))
            migrated_review = migrated.get_reviews()[0]
            migrated_evidence = migrated.get_evidence()[0]
            migrated_app = migrated.get_apps()[0]
            migrated_details = migrated.connection.execute(
                "SELECT details FROM runs"
            ).fetchone()[0]
            self.assertNotIn("test@example.com", migrated_review.body)
            self.assertNotIn("private.example", migrated_evidence.quote)
            self.assertNotIn("test@example.com", migrated_app.description)
            self.assertNotIn("test@example.com", migrated_app.name)
            self.assertNotIn("test@example.com", migrated_details)
            self.assertEqual(
                migrated.connection.execute("PRAGMA user_version").fetchone()[0],
                PUBLIC_REDACTION_VERSION,
            )
            migrated.close()

    def test_review_insert_is_idempotent(self):
        from opportunity_radar.models import App, Cluster, Evidence, Opportunity, Review
        from opportunity_radar.storage import Database

        review = Review(
            store="google_play",
            external_id="review-1",
            app_external_id="com.example.app",
            rating=1,
            title="Broken",
            body="It fails.",
            published_at="2026-08-18",
            version=None,
            source_url="https://example.test/review-1",
        )
        database = Database(":memory:")
        self.assertTrue(database.insert_review(review))
        self.assertFalse(database.insert_review(review))
        self.assertEqual(database.count_reviews(), 1)

        app = App(
            store="google_play",
            external_id="com.example.app",
            name="Example",
            category="productivity",
            rank=1,
            url="https://example.test/app",
        )
        self.assertTrue(database.insert_app(app))
        self.assertFalse(database.insert_app(app))
        enriched_app = App(
            store="google_play",
            external_id="com.example.app",
            name="Example",
            category="productivity",
            rank=1,
            url="https://example.test/app",
            description="A workspace for small teams.",
            developer="Example Labs",
            price="Free",
        )
        database.insert_app(enriched_app)
        self.assertEqual(database.get_apps()[0].description, "A workspace for small teams.")
        self.assertEqual(database.count_apps(), 1)

        evidence = Evidence(
            review_id="review-1",
            pain="Exports fail",
            affected_user="Small teams",
            context="After creating a report",
            severity=4,
            paid_signal=2,
            quote="It fails.",
            confidence=0.9,
        )
        self.assertTrue(database.insert_evidence(evidence))
        self.assertFalse(database.insert_evidence(evidence))
        self.assertEqual(database.count_evidence(), 1)
        self.assertEqual(database.get_reviews()[0], review)
        self.assertEqual(database.get_evidence()[0], evidence)

        cluster = Cluster(
            label="Export failures",
            summary="Users cannot export reports",
            evidence_ids=("google_play:review-1",),
            affected_user="Small teams",
            validation_action="Interview five teams",
        )
        opportunity = Opportunity(
            label="Export failures",
            summary="Users cannot export reports",
            affected_user="Small teams",
            validation_action="Interview five teams",
            evidence_ids=("google_play:review-1",),
            score=72.5,
            review_count=3,
            app_count=2,
            average_severity=4.0,
            average_paid_signal=2.0,
        )
        cluster_id = database.insert_cluster(cluster)
        database.insert_opportunity(cluster_id, opportunity)
        self.assertEqual(database.count_clusters(), 1)
        self.assertEqual(database.count_opportunities(), 1)


if __name__ == "__main__":
    unittest.main()
