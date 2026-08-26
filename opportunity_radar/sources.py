import json
import re
from dataclasses import dataclass, replace
from html import unescape
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit
from urllib.request import Request, urlopen

from .models import App, Review


CATEGORIES = {
    "productivity": {
        "apple_term": "productivity",
        "apple_genres": {"Productivity"},
        "google_slug": "PRODUCTIVITY",
    },
    "business": {
        "apple_term": "business",
        "apple_genres": {"Business"},
        "google_slug": "BUSINESS",
    },
    "ai_utilities": {
        "apple_term": "artificial intelligence",
        "apple_genres": {"Productivity", "Utilities"},
        "google_slug": "TOOLS",
    },
}


def _label(value):
    if isinstance(value, dict):
        return value.get("label")
    return value


def _meta_value(html: str, key: str) -> str | None:
    for attribute in ("name", "property"):
        patterns = (
            rf'<meta[^>]+{attribute}=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']*)',
            rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+{attribute}=["\']{re.escape(key)}["\']',
        )
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return unescape(match.group(1)).strip() or None
    return None


def parse_google_app_metadata(html: str) -> dict[str, str | None]:
    return {
        "description": _meta_value(html, "description")
        or _meta_value(html, "og:description"),
        "developer": _meta_value(html, "author"),
    }


def parse_apple_reviews(
    payload: str | dict,
    *,
    app_external_id: str,
    source_url: str,
    max_rating: int = 3,
) -> list[Review]:
    data = json.loads(payload) if isinstance(payload, str) else payload
    entries = data.get("feed", {}).get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    reviews = []
    for entry in entries:
        rating = _label(entry.get("im:rating"))
        body = _label(entry.get("content"))
        if not rating or not body:
            continue
        rating = int(rating)
        if rating > max_rating:
            continue
        reviews.append(
            Review(
                store="app_store",
                external_id=str(_label(entry.get("id"))),
                app_external_id=app_external_id,
                rating=rating,
                title=_label(entry.get("title")),
                body=body.strip(),
                published_at=_label(entry.get("updated")),
                version=_label(entry.get("im:version")),
                source_url=source_url,
            )
        )
    return reviews


def parse_apple_search_results(
    payload: str | dict,
    *,
    category: str,
    limit: int = 20,
) -> list[App]:
    config = CATEGORIES[category]
    data = json.loads(payload) if isinstance(payload, str) else payload
    apps = []
    seen = set()
    for result in data.get("results", []):
        external_id = result.get("trackId")
        if (
            result.get("wrapperType") != "software"
            or not external_id
            or external_id in seen
            or result.get("primaryGenreName") not in config["apple_genres"]
        ):
            continue
        seen.add(external_id)
        apps.append(
            App(
                store="app_store",
                external_id=str(external_id),
                name=result.get("trackName", "").strip(),
                category=category,
                rank=len(apps) + 1,
                url=result.get("trackViewUrl", ""),
                description=(result.get("description") or "").strip() or None,
                developer=(result.get("sellerName") or "").strip() or None,
                price=(result.get("formattedPrice") or "").strip() or None,
            )
        )
        if len(apps) == limit:
            break
    return apps


def parse_google_category_page(
    html: str,
    *,
    category: str,
    limit: int = 20,
) -> list[App]:
    pattern = re.compile(
        r'<a[^>]+href=[\'\"](/store/apps/details\?id=[^\'\"]+)[\'\"][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    apps = []
    seen = set()
    for match in pattern.finditer(html):
        href = unescape(match.group(1))
        query = parse_qs(urlsplit(href).query)
        external_id = query.get("id", [""])[0]
        if not external_id or external_id in seen:
            continue
        name_match = re.search(r'(?:title|alt)=[\'\"]([^\'\"]+)', match.group(2))
        name = name_match.group(1) if name_match else external_id
        name = unescape(name.removeprefix("Icon image ")).strip()
        seen.add(external_id)
        apps.append(
            App(
                store="google_play",
                external_id=unquote(external_id),
                name=name,
                category=category,
                rank=len(apps) + 1,
                url=f"https://play.google.com{href}",
            )
        )
        if len(apps) == limit:
            break
    return apps


def fetch_text(url: str, *, timeout: int = 30) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "opportunity-radar/0.1 (+local research)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, "replace")


class AppleSource:
    store = "app_store"

    def __init__(self, *, country: str = "us", fetcher=fetch_text):
        self.country = country
        self.fetcher = fetcher

    def discover_apps(self, category: str, limit: int = 20) -> list[App]:
        config = CATEGORIES[category]
        url = (
            "https://itunes.apple.com/search?"
            f"term={quote_plus(config['apple_term'])}&country={self.country}"
            f"&entity=software&limit={max(limit * 3, 50)}"
        )
        return parse_apple_search_results(
            self.fetcher(url), category=category, limit=limit
        )

    def fetch_reviews(self, app: App) -> list[Review]:
        url = (
            f"https://itunes.apple.com/{self.country}/rss/customerreviews/"
            f"page=1/id={app.external_id}/sortby=mostrecent/json"
        )
        return parse_apple_reviews(
            self.fetcher(url),
            app_external_id=app.external_id,
            source_url=url,
        )


class GooglePlaySource:
    store = "google_play"

    def __init__(self, *, country: str = "US", language: str = "en", fetcher=fetch_text):
        self.country = country
        self.language = language
        self.fetcher = fetcher
        self._metadata = {}

    def discover_apps(self, category: str, limit: int = 20) -> list[App]:
        slug = CATEGORIES[category]["google_slug"]
        url = (
            f"https://play.google.com/store/apps/category/{slug}"
            f"?hl={self.language}&gl={self.country}"
        )
        return parse_google_category_page(
            self.fetcher(url), category=category, limit=limit
        )

    def fetch_reviews(self, app: App) -> list[Review]:
        url = (
            "https://play.google.com/store/apps/details?"
            f"id={quote_plus(app.external_id)}&hl={self.language}&gl={self.country}"
        )
        html = self.fetcher(url)
        self._metadata[app.external_id] = parse_google_app_metadata(html)
        return parse_google_reviews(
            html,
            app_external_id=app.external_id,
            source_url=url,
        )

    def enrich_app(self, app: App) -> App:
        return replace(app, **self._metadata.get(app.external_id, {}))


@dataclass(frozen=True)
class StoreProbe:
    store: str
    apps_by_category: dict[str, int]
    low_star_reviews: int
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return (
            not self.errors
            and bool(self.apps_by_category)
            and all(count >= 20 for count in self.apps_by_category.values())
            and self.low_star_reviews > 0
        )


@dataclass(frozen=True)
class ProbeReport:
    stores: dict[str, StoreProbe]

    @property
    def passed(self) -> bool:
        return bool(self.stores) and all(probe.passed for probe in self.stores.values())


def probe_sources(
    sources: dict[str, object],
    *,
    categories: tuple[str, ...] = tuple(CATEGORIES),
    sample_size: int = 5,
    minimum_apps: int = 20,
) -> ProbeReport:
    results = {}
    for store, source in sources.items():
        apps_by_category = {}
        low_star_reviews = 0
        errors = []
        for category in categories:
            try:
                apps = source.discover_apps(category, minimum_apps)
                apps_by_category[category] = len(apps)
                if len(apps) < minimum_apps:
                    errors.append(
                        f"{category}: discovered {len(apps)}, expected {minimum_apps}"
                    )
                for app in apps[:sample_size]:
                    try:
                        low_star_reviews += len(source.fetch_reviews(app))
                    except Exception as exc:
                        errors.append(f"{category}/{app.external_id}: {exc}")
            except Exception as exc:
                apps_by_category[category] = 0
                errors.append(f"{category}: {exc}")
        results[store] = StoreProbe(
            store=store,
            apps_by_category=apps_by_category,
            low_star_reviews=low_star_reviews,
            errors=tuple(errors),
        )
    return ProbeReport(stores=results)


def parse_google_reviews(
    html: str,
    *,
    app_external_id: str,
    source_url: str,
    max_rating: int = 3,
) -> list[Review]:
    pattern = re.compile(
        r'<header[^>]*data-review-id=[\'\"]([^\'\"]+)[\'\"][^>]*>.*?'
        r'</header>\s*<div[^>]*class=[\'\"]h3YV2d[\'\"][^>]*>(.*?)</div>',
        re.IGNORECASE | re.DOTALL,
    )
    reviews = []
    for match in pattern.finditer(html):
        block = match.group(0)
        rating_match = re.search(
            r'aria-label=[\'\"]Rated\s+(\d)\s+stars', block, re.IGNORECASE
        )
        date_match = re.search(
            r'class=[\'\"]bp9Aid[\'\"]>([^<]+)', block, re.IGNORECASE
        )
        body = re.sub(r"<[^>]+>", "", match.group(2))
        body = unescape(body).strip()
        if not rating_match or not body:
            continue
        rating = int(rating_match.group(1))
        if rating > max_rating:
            continue
        reviews.append(
            Review(
                store="google_play",
                external_id=match.group(1),
                app_external_id=app_external_id,
                rating=rating,
                title=None,
                body=body,
                published_at=date_match.group(1).strip() if date_match else None,
                version=None,
                source_url=source_url,
            )
        )
    return reviews
