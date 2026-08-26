from dataclasses import dataclass
from datetime import date, datetime
from math import exp

from .models import Cluster, Evidence, Opportunity, Review


@dataclass(frozen=True)
class ClusterStats:
    review_count: int
    app_count: int
    average_reviews_per_app: float
    average_severity: float
    average_paid_signal: float
    newest_age_days: int


def qualifies_as_opportunity(*, review_count: int, app_count: int) -> bool:
    return review_count >= 3 and app_count >= 2


def score_cluster(stats: ClusterStats) -> float:
    # ponytail: fixed heuristic ranking; calibrate weights from reviewed reports before adding ML.
    spread = min(stats.app_count / 5, 1.0)
    frequency = min(stats.average_reviews_per_app / 5, 1.0)
    severity = min(max((stats.average_severity - 1) / 4, 0.0), 1.0)
    recency = exp(-max(stats.newest_age_days, 0) / 180)
    paid_signal = min(max(stats.average_paid_signal / 3, 0.0), 1.0)
    score = 100 * (
        0.25 * spread
        + 0.25 * frequency
        + 0.20 * severity
        + 0.15 * recency
        + 0.15 * paid_signal
    )
    return round(score, 2)


def _review_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        try:
            return datetime.strptime(value, "%B %d, %Y").date()
        except ValueError:
            return None


def build_opportunities(
    clusters: list[Cluster],
    evidence: list[Evidence],
    reviews: dict[str, Review],
    *,
    now: str | None = None,
) -> list[Opportunity]:
    evidence_by_id = {item.review_id: item for item in evidence}
    today = date.fromisoformat(now) if now else date.today()
    opportunities = []
    for cluster in clusters:
        selected_evidence = []
        selected_reviews = []
        for review_id in cluster.evidence_ids:
            if review_id not in evidence_by_id or review_id not in reviews:
                raise ValueError(f"cluster references missing evidence: {review_id}")
            selected_evidence.append(evidence_by_id[review_id])
            selected_reviews.append(reviews[review_id])
        app_count = len({review.app_external_id for review in selected_reviews})
        if not qualifies_as_opportunity(
            review_count=len(selected_reviews), app_count=app_count
        ):
            continue
        dates = [_review_date(review.published_at) for review in selected_reviews]
        dates = [published for published in dates if published]
        newest_age_days = min((today - published).days for published in dates) if dates else 365
        stats = ClusterStats(
            review_count=len(selected_reviews),
            app_count=app_count,
            average_reviews_per_app=len(selected_reviews) / app_count,
            average_severity=sum(item.severity for item in selected_evidence)
            / len(selected_evidence),
            average_paid_signal=sum(item.paid_signal for item in selected_evidence)
            / len(selected_evidence),
            newest_age_days=max(newest_age_days, 0),
        )
        opportunities.append(
            Opportunity(
                label=cluster.label,
                summary=cluster.summary,
                affected_user=cluster.affected_user,
                validation_action=cluster.validation_action,
                evidence_ids=cluster.evidence_ids,
                score=score_cluster(stats),
                review_count=len(selected_reviews),
                app_count=app_count,
                average_severity=round(stats.average_severity, 2),
                average_paid_signal=round(stats.average_paid_signal, 2),
            )
        )
    return sorted(opportunities, key=lambda item: item.score, reverse=True)
