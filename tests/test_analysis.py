import unittest
from http.client import RemoteDisconnected
from unittest.mock import patch


class AnalysisTests(unittest.TestCase):
    def test_post_json_wraps_remote_disconnect(self):
        from opportunity_radar.analysis import AnalyzerError, post_json

        with patch(
            "opportunity_radar.analysis.urlopen",
            side_effect=RemoteDisconnected("closed"),
        ):
            with self.assertRaises(AnalyzerError):
                post_json("https://api.example.test", {}, {})

    def test_structured_analysis_requires_evidence_fields(self):
        from opportunity_radar.analysis import AnalysisFormatError, parse_analysis

        with self.assertRaises(AnalysisFormatError):
            parse_analysis({"pain": "Missing required fields"})

    def test_structured_analysis_keeps_review_id_and_signal_values(self):
        from opportunity_radar.analysis import parse_analysis

        result = parse_analysis(
            {
                "review_id": "review-1",
                "pain": "Exports fail",
                "affected_user": "Small teams",
                "context": "After creating a report",
                "severity": 4,
                "paid_signal": 2,
                "quote": "The export fails every time.",
                "confidence": 0.9,
            }
        )

        self.assertEqual(result.review_id, "review-1")
        self.assertEqual(result.severity, 4)
        self.assertEqual(result.paid_signal, 2)

    def test_openai_analyzer_sends_structured_schema(self):
        from opportunity_radar.analysis import OpenAIAnalyzer
        from opportunity_radar.models import Review

        calls = []

        def requester(url, headers, payload):
            calls.append((url, headers, payload))
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"review_id":"google_play:review-1",'
                                    '"pain":"Exports fail",'
                                    '"affected_user":"Small teams",'
                                    '"context":"After creating a report",'
                                    '"severity":4,"paid_signal":2,'
                                    '"quote":"It fails.","confidence":0.9}'
                                ),
                            }
                        ],
                    }
                ]
            }

        analyzer = OpenAIAnalyzer(
            api_key="test-key",
            model="test-model",
            requester=requester,
        )
        result = analyzer.analyze_review(
            Review(
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
        )

        self.assertEqual(result.review_id, "google_play:review-1")
        self.assertEqual(calls[0][0], "https://api.openai.com/v1/responses")
        self.assertFalse(calls[0][2]["store"])
        self.assertNotIn("temperature", calls[0][2])
        self.assertEqual(calls[0][2]["text"]["format"]["type"], "json_schema")

    def test_openai_analyzer_rejects_quote_outside_review(self):
        from opportunity_radar.analysis import AnalyzerError, OpenAIAnalyzer
        from opportunity_radar.models import Review

        def requester(url, headers, payload):
            return {
                "output_text": (
                    '{"review_id":"app_store:review-1",'
                    '"pain":"Exports fail",'
                    '"affected_user":"Small teams",'
                    '"context":"After creating a report",'
                    '"severity":4,"paid_signal":0,'
                    '"quote":"This text is not in the review.","confidence":0.9}'
                )
            }

        analyzer = OpenAIAnalyzer(
            api_key="test-key",
            model="test-model",
            requester=requester,
        )
        with self.assertRaises(AnalyzerError):
            analyzer.analyze_review(
                Review(
                    store="app_store",
                    external_id="review-1",
                    app_external_id="123",
                    rating=1,
                    title="Broken",
                    body="It fails.",
                    published_at=None,
                    version=None,
                    source_url="https://example.test/review-1",
                )
            )

    def test_openai_analyzer_groups_evidence_into_clusters(self):
        from opportunity_radar.analysis import OpenAIAnalyzer
        from opportunity_radar.models import Evidence

        def requester(url, headers, payload):
            return {
                "output_text": (
                    '{"clusters":[{"label":"Export failures",'
                    '"summary":"Users cannot export reports",'
                    '"evidence_ids":["google_play:review-1"],'
                    '"affected_user":"Small teams",'
                    '"validation_action":"Interview five teams"}]}'
                )
            }

        analyzer = OpenAIAnalyzer(
            api_key="test-key",
            model="test-model",
            requester=requester,
        )
        clusters = analyzer.cluster_evidence(
            [
                Evidence(
                    review_id="google_play:review-1",
                    pain="Exports fail",
                    affected_user="Small teams",
                    context="After creating a report",
                    severity=4,
                    paid_signal=2,
                    quote="It fails.",
                    confidence=0.9,
                )
            ]
        )

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].evidence_ids, ("google_play:review-1",))

    def test_openai_analyzer_adds_business_judgment_to_opportunities(self):
        from opportunity_radar.analysis import OpenAIAnalyzer
        from opportunity_radar.models import App, Evidence, Opportunity, Review

        calls = []

        def requester(url, headers, payload):
            calls.append((url, headers, payload))
            return {
                "output_text": (
                    '{"insights":[{"opportunity_index":0,'
                    '"failure_stage":"核心使用",'
                    '"root_cause":"导出链路不可靠，错误未被产品兜底",'
                    '"user_consequence":"用户无法交付报告并开始寻找替代品",'
                    '"commercial_implication":"团队型用户有明确替代和付费理由",'
                    '"decision":"值得优先验证",'
                    '"confidence":0.88}]}'
                )
            }

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
        enriched = OpenAIAnalyzer(
            api_key="test-key",
            model="test-model",
            requester=requester,
        ).enrich_opportunities(
            [opportunity],
            {"google_play:com.example.app": App(
                store="google_play",
                external_id="com.example.app",
                name="Example Docs",
                category="productivity",
                rank=1,
                url="https://example.test/app",
                description="A document workspace.",
            )},
            {"google_play:review-1": Evidence(
                review_id="google_play:review-1",
                pain="Exports fail",
                affected_user="Small teams",
                context="After creating a report",
                severity=4,
                paid_signal=2,
                quote="It fails.",
                confidence=0.9,
            )},
            {"google_play:review-1": Review(
                store="google_play",
                external_id="review-1",
                app_external_id="com.example.app",
                rating=1,
                title="Broken",
                body="It fails.",
                published_at="2026-08-18",
                version=None,
                source_url="https://example.test/review-1",
            )},
        )

        self.assertEqual(enriched[0].failure_stage, "核心使用")
        self.assertEqual(enriched[0].decision, "值得优先验证")
        self.assertEqual(enriched[0].analysis_confidence, 0.88)
        self.assertIn("Example Docs", calls[0][2]["input"][1]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
