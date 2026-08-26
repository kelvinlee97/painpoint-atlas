import unittest


class ScoringTests(unittest.TestCase):
    def test_maximum_signals_produce_score_of_100(self):
        from opportunity_radar.scoring import ClusterStats, score_cluster

        score = score_cluster(
            ClusterStats(
                review_count=25,
                app_count=5,
                average_reviews_per_app=5,
                average_severity=5,
                average_paid_signal=3,
                newest_age_days=0,
            )
        )

        self.assertEqual(score, 100.0)

    def test_cluster_requires_three_reviews_across_two_apps(self):
        from opportunity_radar.scoring import qualifies_as_opportunity

        self.assertTrue(qualifies_as_opportunity(review_count=3, app_count=2))
        self.assertFalse(qualifies_as_opportunity(review_count=10, app_count=1))
        self.assertFalse(qualifies_as_opportunity(review_count=2, app_count=2))

    def test_build_opportunities_ranks_qualified_clusters(self):
        from opportunity_radar.models import Cluster, Evidence, Review
        from opportunity_radar.scoring import build_opportunities

        reviews = {
            "google_play:r1": Review(
                store="google_play",
                external_id="r1",
                app_external_id="app-a",
                rating=1,
                title=None,
                body="Export fails.",
                published_at="2026-08-20",
                version=None,
                source_url="https://example.test/r1",
            ),
            "google_play:r2": Review(
                store="google_play",
                external_id="r2",
                app_external_id="app-a",
                rating=2,
                title=None,
                body="Export fails again.",
                published_at="2026-08-19",
                version=None,
                source_url="https://example.test/r2",
            ),
            "app_store:r3": Review(
                store="app_store",
                external_id="r3",
                app_external_id="app-b",
                rating=1,
                title=None,
                body="Cannot export.",
                published_at="2026-08-18",
                version=None,
                source_url="https://example.test/r3",
            ),
        }
        evidence = [
            Evidence(
                review_id=review_id,
                pain="Exports fail",
                affected_user="Small teams",
                context="After creating a report",
                severity=4,
                paid_signal=2,
                quote="Export fails.",
                confidence=0.9,
            )
            for review_id in reviews
        ]
        clusters = [
            Cluster(
                label="Export failures",
                summary="Users cannot export reports",
                evidence_ids=tuple(reviews),
                affected_user="Small teams",
                validation_action="Interview five teams",
            )
        ]

        opportunities = build_opportunities(clusters, evidence, reviews, now="2026-08-25")

        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].app_count, 2)
        self.assertGreater(opportunities[0].score, 0)


if __name__ == "__main__":
    unittest.main()
