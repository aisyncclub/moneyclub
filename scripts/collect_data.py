from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen
import ssl

import feedparser
import yfinance as yf
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_PATH = DATA_DIR / "latest.json"
KST = ZoneInfo("Asia/Seoul")

TICKERS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "vix": "^VIX",
    "wti": "CL=F",
    "brent": "BZ=F",
    "btc": "BTC-USD",
    "gold": "GC=F",
    "usd_krw": "KRW=X",
    "dxy": "DX-Y.NYB",
}

RSS_FEEDS = [
    ("CNBC Markets", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("MarketWatch Top", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("네이버 경제", "https://rss.naver.com/rss.nhn?mode=general&sectionId=101"),
]


@dataclass
class Metric:
    ticker: str
    value: float
    change_pct: float
    change_abs: float
    previous_close: float
    as_of: str
    currency: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "value": round(self.value, 4),
            "change_pct": round(self.change_pct, 4),
            "change_abs": round(self.change_abs, 4),
            "previous_close": round(self.previous_close, 4),
            "as_of": self.as_of,
            "currency": self.currency,
        }


def fetch_history(symbol: str) -> Metric:
    history = yf.Ticker(symbol).history(period="7d", interval="1d", auto_adjust=False)
    closes = history["Close"].dropna()
    if len(closes) < 2:
        raise RuntimeError(f"Not enough price history for {symbol}")

    latest = float(closes.iloc[-1])
    previous = float(closes.iloc[-2])
    change_abs = latest - previous
    change_pct = (change_abs / previous) * 100 if previous else 0.0
    as_of = closes.index[-1].to_pydatetime().astimezone(KST).isoformat()
    currency = None
    try:
        info = yf.Ticker(symbol).fast_info
        currency = info.get("currency")
    except Exception:
        currency = None

    return Metric(
        ticker=symbol,
        value=latest,
        change_pct=change_pct,
        change_abs=change_abs,
        previous_close=previous,
        as_of=as_of,
        currency=currency,
    )


def fetch_fear_greed() -> dict[str, Any]:
    context = ssl.create_default_context()
    with urlopen("https://api.alternative.me/fng/?limit=1", context=context, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    latest = payload["data"][0]
    return {
        "value": int(latest["value"]),
        "classification": latest["value_classification"],
        "timestamp": latest["timestamp"],
    }


def normalize_link(link: str) -> str:
    return link.split("?")[0].rstrip("/")


def collect_news(limit: int = 15) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for source_name, url in RSS_FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            title = " ".join((entry.get("title") or "").split())
            link = entry.get("link") or ""
            if not title or not link:
                continue
            key = (title.casefold(), normalize_link(link))
            if key in seen:
                continue
            seen.add(key)
            published = (
                entry.get("published")
                or entry.get("updated")
                or entry.get("pubDate")
                or ""
            )
            items.append(
                {
                    "source": source_name,
                    "title": title,
                    "link": link,
                    "published": published,
                    "summary": " ".join((entry.get("summary") or "").split())[:280],
                }
            )

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        published = item["published"]
        if published:
            parsed = feedparser._parse_date(published)  # type: ignore[attr-defined]
            if parsed:
                return (1, datetime(*parsed[:6], tzinfo=UTC).isoformat())
        return (0, "")

    items.sort(key=sort_key, reverse=True)
    return items[:limit]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    metrics: dict[str, Any] = {}
    errors: list[str] = []
    for key, symbol in TICKERS.items():
        try:
            metrics[key] = fetch_history(symbol).to_dict()
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")

    if errors:
        raise RuntimeError("Price collection failed:\n" + "\n".join(errors))

    try:
        fear_greed = fetch_fear_greed()
    except URLError as exc:
        raise RuntimeError(f"Fear & Greed fetch failed: {exc}") from exc

    news = collect_news(limit=15)
    now_kst = datetime.now(KST)
    payload = {
        "date": now_kst.date().isoformat(),
        "generated_at_kst": now_kst.isoformat(),
        "metrics": metrics,
        "fear_greed_crypto": fear_greed,
        "news": news,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
