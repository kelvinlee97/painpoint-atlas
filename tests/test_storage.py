import unittest


class StorageTests(unittest.TestCase):
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
