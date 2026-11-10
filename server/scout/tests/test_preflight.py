"""Server preflight of mode B: sitemap parsing."""

from __future__ import annotations

from scout.preflight import parse_sitemap


def test_sitemap_parsing() -> None:
    xml = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://s.uz/a</loc></url><url><loc>https://s.uz/b</loc></url></urlset>"
    )
    assert parse_sitemap(xml) == (["https://s.uz/a", "https://s.uz/b"], [])
    assert parse_sitemap("<broken") == ([], [])
