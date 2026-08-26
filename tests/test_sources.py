import json
import unittest


APPLE_FIXTURE = {
    "feed": {
        "entry": [
            {
                "id": {"label": "apple-review-1"},
                "im:rating": {"label": "1"},
                "im:version": {"label": "1.2.3"},
                "updated": {"label": "2026-08-20T10:00:00-07:00"},
                "title": {"label": "Cannot export"},
                "content": {"label": "The export fails every time."},
            },
            {
                "id": {"label": "apple-review-2"},
                "im:rating": {"label": "4"},
                "updated": {"label": "2026-08-19T10:00:00-07:00"},
                "title": {"label": "Good"},
                "content": {"label": "Mostly useful."},
            },
        ]
    }
}

GOOGLE_FIXTURE = """
<div class="EGFGHd">
  <header data-review-id="google-review-1">
    <div class="Jx4nYe">
      <div aria-label="Rated 2 stars out of five stars" role="img"></div>
      <span class="bp9Aid">August 18, 2026</span>
    </div>
  </header>
  <div class="h3YV2d">The sync is unreliable and loses my work.</div>
</div>
<div class="EGFGHd">
  <header data-review-id="google-review-2">
    <div class="Jx4nYe">
      <div aria-label="Rated 5 stars out of five stars" role="img"></div>
      <span class="bp9Aid">August 17, 2026</span>
    </div>
  </header>
  <div class="h3YV2d">Excellent app.</div>
</div>
"""

APPLE_SEARCH_FIXTURE = {
    "resultCount": 3,
    "results": [
        {
            "wrapperType": "software",
            "trackId": 100,
            "trackName": "Productivity One",
            "description": "A focused workspace for small teams.",
            "sellerName": "Example Labs",
            "formattedPrice": "Free",
            "primaryGenreName": "Productivity",
            "trackViewUrl": "https://apps.apple.com/us/app/one/id100",
        },
        {
            "wrapperType": "software",
            "trackId": 101,
            "trackName": "Business One",
            "primaryGenreName": "Business",
            "trackViewUrl": "https://apps.apple.com/us/app/two/id101",
        },
        {
            "wrapperType": "software",
            "trackId": 102,
            "trackName": "Productivity Two",
            "primaryGenreName": "Productivity",
            "trackViewUrl": "https://apps.apple.com/us/app/three/id102",
        },
    ],
}

GOOGLE_CATEGORY_FIXTURE = """
<a href="/store/apps/details?id=com.example.one"><div title="Example One"></div></a>
<a href="/store/apps/details?id=com.example.one"><div title="Example One"></div></a>
<a href="/store/apps/details?id=com.example.two"><div title="Example Two"></div></a>
"""

GOOGLE_METADATA_FIXTURE = """
<html>
<head>
  <meta name="description" content="Plan tasks and keep projects moving.">
  <meta name="author" content="Example Labs">
</head>
</html>
"""


class SourceParsingTests(unittest.TestCase):
    def test_apple_parser_keeps_only_low_star_reviews(self):
        from opportunity_radar.sources import parse_apple_reviews

        reviews = parse_apple_reviews(
            json.dumps(APPLE_FIXTURE),
            app_external_id="app-1",
            source_url="https://example.test/apple",
        )

        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].external_id, "apple-review-1")
        self.assertEqual(reviews[0].rating, 1)
        self.assertEqual(reviews[0].body, "The export fails every time.")

    def test_google_parser_extracts_low_star_review_without_author_data(self):
        from opportunity_radar.sources import parse_google_reviews

        reviews = parse_google_reviews(
            GOOGLE_FIXTURE,
            app_external_id="com.example.app",
            source_url="https://example.test/google",
        )

        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].external_id, "google-review-1")
        self.assertEqual(reviews[0].rating, 2)
        self.assertEqual(reviews[0].body, "The sync is unreliable and loses my work.")
        self.assertFalse(hasattr(reviews[0], "author"))

    def test_catalog_parsers_keep_ranked_unique_apps(self):
        from opportunity_radar.sources import (
            parse_apple_search_results,
            parse_google_category_page,
        )

        apple_apps = parse_apple_search_results(
            APPLE_SEARCH_FIXTURE, category="productivity", limit=10
        )
        google_apps = parse_google_category_page(
            GOOGLE_CATEGORY_FIXTURE,
            category="productivity",
            limit=10,
        )

        self.assertEqual([app.external_id for app in apple_apps], ["100", "102"])
        self.assertEqual([app.rank for app in apple_apps], [1, 2])
        self.assertEqual(apple_apps[0].description, "A focused workspace for small teams.")
        self.assertEqual(apple_apps[0].developer, "Example Labs")
        self.assertEqual([app.external_id for app in google_apps], ["com.example.one", "com.example.two"])
        self.assertEqual(google_apps[1].name, "Example Two")

    def test_google_parser_extracts_product_description(self):
        from opportunity_radar.sources import parse_google_app_metadata

        metadata = parse_google_app_metadata(GOOGLE_METADATA_FIXTURE)

        self.assertEqual(metadata["description"], "Plan tasks and keep projects moving.")
        self.assertEqual(metadata["developer"], "Example Labs")

    def test_probe_fails_when_no_store_has_low_star_reviews(self):
        from opportunity_radar.models import App
        from opportunity_radar.sources import probe_sources

        class FakeSource:
            store = "fake"

            def discover_apps(self, category, limit):
                return [
                    App(
                        store="fake",
                        external_id=f"{category}-{index}",
                        name="Example",
                        category=category,
                        rank=index + 1,
                        url="https://example.test/app",
                    )
                    for index in range(limit)
                ]

            def fetch_reviews(self, app):
                return []

        report = probe_sources(
            {"app_store": FakeSource(), "google_play": FakeSource()},
            categories=("productivity",),
            sample_size=1,
            minimum_apps=20,
        )

        self.assertFalse(report.passed)
        self.assertIn("app_store", report.stores)

    def test_probe_allows_one_store_to_have_no_low_star_reviews(self):
        from opportunity_radar.models import App, Review
        from opportunity_radar.sources import probe_sources

        class FakeSource:
            def __init__(self, has_reviews):
                self.has_reviews = has_reviews

            def discover_apps(self, category, limit):
                return [
                    App(
                        store="fake",
                        external_id=f"{category}-{index}",
                        name="Example",
                        category=category,
                        rank=index + 1,
                        url="https://example.test/app",
                    )
                    for index in range(limit)
                ]

            def fetch_reviews(self, app):
                return [
                    Review(
                        store="fake",
                        external_id="review-1",
                        app_external_id=app.external_id,
                        rating=1,
                        title="Broken",
                        body="It fails.",
                        published_at=None,
                        version=None,
                        source_url="https://example.test/review-1",
                    )
                ] if self.has_reviews else []

        report = probe_sources(
            {
                "app_store": FakeSource(False),
                "google_play": FakeSource(True),
            },
            categories=("productivity",),
            sample_size=1,
            minimum_apps=20,
        )

        self.assertTrue(report.passed)


if __name__ == "__main__":
    unittest.main()
