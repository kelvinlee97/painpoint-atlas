import unittest


class ReportTests(unittest.TestCase):
    def test_report_contains_ranked_opportunity_and_source_link(self):
        from opportunity_radar.models import App, Evidence, Opportunity, Review
        from opportunity_radar.report import render_report

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
            failure_stage="核心使用",
            root_cause="导出链路不可靠",
            user_consequence="团队无法交付报告",
            commercial_implication="有明确的替代和付费验证空间",
            decision="值得优先验证",
            analysis_confidence=0.88,
        )
        evidence = {
            "google_play:review-1": Evidence(
                review_id="google_play:review-1",
                pain="Exports fail",
                affected_user="Small teams",
                context="After creating a report",
                severity=4,
                paid_signal=2,
                quote="The export fails every time.",
                confidence=0.9,
            )
        }
        reviews = {
            "google_play:review-1": Review(
                store="google_play",
                external_id="review-1",
                app_external_id="com.example.app",
                rating=1,
                title=None,
                body="The export fails every time.",
                published_at="2026-08-20",
                version=None,
                source_url="https://example.test/review-1",
            )
        }
        apps = {
            "google_play:com.example.app": App(
                store="google_play",
                external_id="com.example.app",
                name="Example Docs",
                category="productivity",
                rank=1,
                url="https://example.test/app",
                description="A document workspace for small teams.",
                developer="Example Labs",
                price="Free",
            )
        }

        report = render_report(
            [opportunity], evidence, reviews, apps, generated_at="2026-08-25"
        )

        self.assertIn("# Opportunity Radar", report)
        self.assertIn("Export failures", report)
        self.assertIn("72.5", report)
        self.assertIn("https://example.test/review-1", report)
        self.assertIn("The export fails every time.", report)
        self.assertIn("Example Docs", report)
        self.assertIn("A document workspace for small teams.", report)
        self.assertIn("导出链路不可靠", report)
        self.assertIn("商业判断", report)


if __name__ == "__main__":
    unittest.main()
