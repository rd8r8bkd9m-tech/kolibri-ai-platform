from __future__ import annotations

import asyncio

from app import web_search


OBSERVED_AT = "2026-07-15T10:00:00+00:00"


def test_bing_rss_parser_sanitizes_markup_urls_and_timestamps():
    xml = """
    <rss>
      <channel>
        <item>
          <title><![CDATA[<b>Колибри</b> &amp; P7]]></title>
          <link>https://example.test/path?q=1#private</link>
          <description><![CDATA[<p>Проверенный&nbsp;фрагмент</p>]]></description>
        </item>
        <item>
          <title>Опасный результат</title>
          <link>javascript:alert(1)</link>
          <description>Не должен попасть в выдачу</description>
        </item>
      </channel>
    </rss>
    """

    results = web_search._parse_bing_rss(xml, 5, retrieved_at=OBSERVED_AT)

    assert results == [
        {
            "title": "Колибри & P7",
            "snippet": "Проверенный фрагмент",
            "url": "https://example.test/path?q=1",
            "retrieved_at": OBSERVED_AT,
        }
    ]


def test_web_search_tries_bing_rss_after_ddg_before_google(monkeypatch):
    calls: list[str] = []

    async def searx(_query: str, _num: int):
        calls.append("searx")
        return []

    async def ddg(_query: str, _num: int):
        calls.append("ddg")
        return []

    async def bing(_query: str, _num: int):
        calls.append("bing")
        return [
            {
                "title": "Bing RSS result",
                "snippet": "Live XML result",
                "url": "https://example.test/result",
                "retrieved_at": OBSERVED_AT,
            }
        ]

    async def google(_query: str, _num: int):
        calls.append("google")
        raise AssertionError("Google fallback must not run after Bing succeeds")

    monkeypatch.setattr(web_search, "_search_searx", searx)
    monkeypatch.setattr(web_search, "_search_ddg_html", ddg)
    monkeypatch.setattr(web_search, "_search_bing_rss", bing)
    monkeypatch.setattr(web_search, "_search_google", google)

    results = asyncio.run(web_search.web_search("цены бетон Татарстан", 3))

    assert calls == ["searx", "ddg", "bing"]
    assert results[0]["url"] == "https://example.test/result"
    assert results[0]["retrieved_at"] == OBSERVED_AT
