import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys

from .analysis import AnalysisFormatError, AnalyzerError, OpenAIAnalyzer
from .dashboard import serve_dashboard, write_static_dashboard
from .report import render_report, write_report
from .scoring import build_opportunities
from .sources import (
    CATEGORIES,
    AppleSource,
    GooglePlaySource,
    ProbeReport,
    probe_sources,
)
from .storage import Database


def probe_report_dict(report: ProbeReport) -> dict:
    return {
        "passed": report.passed,
        "stores": {
            store: {
                "passed": result.passed,
                "apps_by_category": result.apps_by_category,
                "low_star_reviews": result.low_star_reviews,
                "errors": list(result.errors),
            }
            for store, result in report.stores.items()
        },
    }


def _sources():
    return {"app_store": AppleSource(), "google_play": GooglePlaySource()}


def _run_probe(*, sample_size: int, minimum_apps: int) -> ProbeReport:
    return probe_sources(
        _sources(), sample_size=sample_size, minimum_apps=minimum_apps
    )


def _collect_reviews(database: Database, *, review_limit_per_app: int) -> None:
    for store, source in _sources().items():
        for category in CATEGORIES:
            apps = source.discover_apps(category, 20)
            for app in apps:
                database.insert_app(app)
                reviews = source.fetch_reviews(app)
                enrich_app = getattr(source, "enrich_app", None)
                if enrich_app:
                    database.insert_app(enrich_app(app))
                for review in reviews[:review_limit_per_app]:
                    database.insert_review(review)


def _select_cluster_evidence(evidence, reviews, limit):
    stores = {}
    for item in evidence:
        review = reviews.get(item.review_id)
        if review:
            stores.setdefault(review.store, {}).setdefault(
                review.app_external_id, []
            ).append(item)
    selected = []
    store_names = sorted(stores)
    for index, store in enumerate(store_names):
        store_limit = (limit + len(store_names) - index - 1) // len(store_names)
        groups = list(stores[store].values())
        while groups and store_limit:
            next_groups = []
            for group in groups:
                if group and store_limit:
                    selected.append(group.pop(0))
                    store_limit -= 1
                if group:
                    next_groups.append(group)
            groups = next_groups
    return selected


def _analyze_and_report(args: argparse.Namespace) -> int:
    probe = _run_probe(
        sample_size=args.sample_size,
        minimum_apps=args.minimum_apps,
    )
    print(json.dumps(probe_report_dict(probe), ensure_ascii=False, indent=2))
    if not probe.passed:
        print("来源探针未通过，停止 run。", file=sys.stderr)
        return 2

    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "")
    if not api_key or not model:
        print("run 需要 OPENAI_API_KEY 和 OPENAI_MODEL。", file=sys.stderr)
        return 3

    database = Database(args.db)
    try:
        _collect_reviews(
            database,
            review_limit_per_app=args.review_limit_per_app,
        )
        reviews = database.get_reviews()
        review_map = {
            f"{review.store}:{review.external_id}": review for review in reviews
        }
        apps = {
            f"{app.store}:{app.external_id}": app for app in database.get_apps()
        }
        evidence = database.get_evidence()
        evidence_ids = {item.review_id for item in evidence}
        analyzer = OpenAIAnalyzer(api_key=api_key, model=model)
        failures = []
        for review_id, review in review_map.items():
            if review_id in evidence_ids:
                continue
            try:
                item = analyzer.analyze_review(review)
                if database.insert_evidence(item):
                    evidence.append(item)
            except (AnalyzerError, ValueError) as exc:
                failures.append(f"{review_id}: {exc}")

        if not evidence:
            database.insert_run("run", "failed", {"reason": "no evidence", "failures": failures})
            print("没有成功分析的评论，未生成报告。", file=sys.stderr)
            return 4

        cluster_input = _select_cluster_evidence(evidence, review_map, args.cluster_limit)
        cluster_attempts = [cluster_input]
        if len(cluster_input) > 20:
            cluster_attempts.append(_select_cluster_evidence(evidence, review_map, 20))
        if len(cluster_input) > 10:
            cluster_attempts.append(_select_cluster_evidence(evidence, review_map, 10))
        if len(cluster_input) < len(evidence):
            print(f"仅使用受控样本 {len(cluster_input)} 条证据进行聚类。", file=sys.stderr)
        evidence_map = {item.review_id: item for item in evidence}
        try:
            clusters = None
            for attempt, candidate in enumerate(cluster_attempts):
                if attempt:
                    print(
                        f"聚类证据校验失败，降级重试前 {len(candidate)} 条。",
                        file=sys.stderr,
                    )
                try:
                    clusters = analyzer.cluster_evidence(candidate, strict=bool(attempt))
                    cluster_input = candidate
                    break
                except AnalysisFormatError:
                    if attempt == len(cluster_attempts) - 1:
                        raise
            opportunities = build_opportunities(
                clusters, evidence_map.values(), review_map
            )
            opportunities = analyzer.enrich_opportunities(
                opportunities, apps, evidence_map, review_map
            )
        except (AnalyzerError, ValueError) as exc:
            database.insert_run(
                "run",
                "failed",
                {"reason": "analysis synthesis failed", "error": str(exc)},
            )
            print(f"高级分析未完成：{exc}", file=sys.stderr)
            return 5
        database.clear_analysis()
        cluster_ids = {}
        for cluster in clusters:
            cluster_ids[cluster.evidence_ids] = database.insert_cluster(cluster)
        for opportunity in opportunities:
            database.insert_opportunity(
                cluster_ids[opportunity.evidence_ids], opportunity
            )

        content = render_report(
            opportunities,
            evidence_map,
            review_map,
            apps,
            clustered_evidence_count=len(cluster_input),
        )
        report_path = Path(args.reports) / f"{date.today().isoformat()}.md"
        write_report(report_path, content)
        database.insert_run(
            "run",
            "success",
            {
                "reviews": len(reviews),
                "evidence": len(evidence),
                "clustered_evidence": len(cluster_input),
                "opportunities": len(opportunities),
                "failures": failures,
                "report": str(report_path),
            },
        )
        print(f"报告已生成：{report_path}")
        return 0
    finally:
        database.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="painpoint-atlas")
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser(
        "probe-sources", help="验证 Apple App Store 与 Google Play 公开来源"
    )
    probe.add_argument("--sample-size", type=int, default=5)
    probe.add_argument("--minimum-apps", type=int, default=20)

    run = subparsers.add_parser("run", help="采集低星评论、分析并生成机会简报")
    run.add_argument("--db", default="data/opportunity_radar.sqlite3")
    run.add_argument("--reports", default="reports")
    run.add_argument("--sample-size", type=int, default=5)
    run.add_argument("--minimum-apps", type=int, default=20)
    run.add_argument("--review-limit-per-app", type=int, default=5)
    # ponytail: cap one cluster prompt at 40; add batch-merge before increasing it.
    run.add_argument("--cluster-limit", type=int, default=40)

    dashboard = subparsers.add_parser(
        "dashboard", help="启动仅监听本机的分析 Dashboard"
    )
    dashboard.add_argument("--db", default="data/opportunity_radar.sqlite3")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8000)

    pages = subparsers.add_parser("build-pages", help="生成 GitHub Pages 静态 Dashboard")
    pages.add_argument("--db", default="data/opportunity_radar.sqlite3")
    pages.add_argument("--output", default="site")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "probe-sources":
        report = _run_probe(
            sample_size=args.sample_size,
            minimum_apps=args.minimum_apps,
        )
        print(json.dumps(probe_report_dict(report), ensure_ascii=False, indent=2))
        return 0 if report.passed else 2
    if args.command == "dashboard":
        serve_dashboard(args.db, host=args.host, port=args.port)
        return 0
    if args.command == "build-pages":
        output = write_static_dashboard(args.db, args.output)
        print(f"静态 Dashboard 已生成：{output}")
        return 0
    return _analyze_and_report(args)
