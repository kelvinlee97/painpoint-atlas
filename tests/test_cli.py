import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class CliTests(unittest.TestCase):
    def test_probe_report_json_has_store_status_and_counts(self):
        from opportunity_radar.cli import probe_report_dict
        from opportunity_radar.sources import ProbeReport, StoreProbe

        report = ProbeReport(
            stores={
                "app_store": StoreProbe(
                    store="app_store",
                    apps_by_category={"productivity": 20},
                    low_star_reviews=4,
                    errors=(),
                )
            }
        )

        result = probe_report_dict(report)

        self.assertTrue(result["passed"])
        self.assertEqual(result["stores"]["app_store"]["low_star_reviews"], 4)

    def test_run_defaults_to_a_smaller_cluster_batch(self):
        from opportunity_radar.cli import build_parser

        args = build_parser().parse_args(["run"])

        self.assertEqual(args.cluster_limit, 40)

    def test_cluster_sample_covers_each_store_before_repeating_apps(self):
        from opportunity_radar.cli import _select_cluster_evidence
        from opportunity_radar.models import Evidence, Review

        evidence = [
            Evidence(f"app_store:r{i}", "p", "u", "c", 3, 0, "q", 0.8)
            for i in range(3)
        ] + [
            Evidence(f"google_play:r{i}", "p", "u", "c", 3, 0, "q", 0.8)
            for i in range(3)
        ]
        reviews = {
            f"app_store:r{i}": Review("app_store", f"r{i}", f"a{i}", 1, None, "b", None, None, "u")
            for i in range(3)
        } | {
            f"google_play:r{i}": Review("google_play", f"r{i}", f"g{i}", 1, None, "b", None, None, "u")
            for i in range(3)
        }

        selected = _select_cluster_evidence(evidence, reviews, 4)

        self.assertEqual(
            {reviews[item.review_id].store for item in selected},
            {"app_store", "google_play"},
        )
        self.assertEqual(len(selected), 4)

    def test_dashboard_defaults_to_local_server(self):
        from opportunity_radar.cli import build_parser

        args = build_parser().parse_args(["dashboard"])

        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8000)

    def test_build_pages_defaults_to_static_output(self):
        from opportunity_radar.cli import build_parser

        args = build_parser().parse_args(["build-pages"])

        self.assertEqual(args.output, "site")
        self.assertEqual(args.db, "data/opportunity_radar.sqlite3")

    def test_static_dashboard_writes_index_html(self):
        from opportunity_radar.dashboard import write_static_dashboard

        payload = {
            "summary": {"apps": 1, "reviews": 1, "evidence": 1, "opportunities": 1},
            "opportunities": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "opportunity_radar.dashboard.load_dashboard_payload",
                return_value=payload,
            ):
                output = write_static_dashboard("ignored.sqlite3", directory)

            self.assertEqual(output, Path(directory) / "index.html")
            self.assertIn("Opportunity Radar", output.read_text(encoding="utf-8"))

    def test_dashboard_html_contains_opportunity_details(self):
        from opportunity_radar.dashboard import render_dashboard

        html = render_dashboard({
            "summary": {"apps": 1, "reviews": 2, "evidence": 2, "opportunities": 1},
            "opportunities": [{
                "label": "导出失败",
                "score": 72.5,
                "decision": "值得优先验证",
                "failure_stage": "核心使用",
                "root_cause": "导出链路不可靠",
                "commercial_implication": "有明确的替代和付费验证空间",
                "apps": [{"name": "Example Docs"}],
                "evidence": [],
            }],
        })

        self.assertIn("Opportunity Radar", html)
        self.assertIn("导出失败", html)
        self.assertIn("值得优先验证", html)
        self.assertIn('id="search"', html)


if __name__ == "__main__":
    unittest.main()
