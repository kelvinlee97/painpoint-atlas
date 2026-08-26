from dataclasses import dataclass


@dataclass(frozen=True)
class App:
    store: str
    external_id: str
    name: str
    category: str
    rank: int
    url: str
    description: str | None = None
    developer: str | None = None
    price: str | None = None


@dataclass(frozen=True)
class Review:
    store: str
    external_id: str
    app_external_id: str
    rating: int
    title: str | None
    body: str
    published_at: str | None
    version: str | None
    source_url: str


@dataclass(frozen=True)
class Evidence:
    review_id: str
    pain: str
    affected_user: str
    context: str
    severity: int
    paid_signal: int
    quote: str
    confidence: float


@dataclass(frozen=True)
class Cluster:
    label: str
    summary: str
    evidence_ids: tuple[str, ...]
    affected_user: str
    validation_action: str


@dataclass(frozen=True)
class Opportunity:
    label: str
    summary: str
    affected_user: str
    validation_action: str
    evidence_ids: tuple[str, ...]
    score: float
    review_count: int
    app_count: int
    average_severity: float
    average_paid_signal: float
    failure_stage: str = ""
    root_cause: str = ""
    user_consequence: str = ""
    commercial_implication: str = ""
    decision: str = ""
    analysis_confidence: float = 0.0
