from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import google.generativeai as genai
from jinja2 import Environment, FileSystemLoader, select_autoescape
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "latest.json"
TEMPLATES_DIR = ROOT / "templates"
KST = ZoneInfo("Asia/Seoul")
SITE_URL = "https://aisyncclub.github.io/moneyclub"

SECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "headline",
        "is_urgent",
        "lead",
        "og_description",
        "archive_summary",
        "timeline_title",
        "narrative",
        "timeline",
        "asset_impact",
        "asset_callout",
        "calendar",
        "calendar_takeaway",
        "scenarios",
        "insights",
        "historical_context",
        "historical_callout",
        "glossary_terms",
        "investor_guide",
    ],
    "properties": {
        "headline": {"type": "string"},
        "is_urgent": {"type": "boolean"},
        "lead": {"type": "string"},
        "og_description": {"type": "string"},
        "archive_summary": {"type": "string"},
        "timeline_title": {"type": "string"},
        "narrative": {"type": "array", "minItems": 3, "maxItems": 5, "items": {"type": "string"}},
        "timeline": {
            "type": "array",
            "minItems": 4,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["date", "title", "desc", "color"],
                "properties": {
                    "date": {"type": "string"},
                    "title": {"type": "string"},
                    "desc": {"type": "string"},
                    "color": {"type": "string", "enum": ["red", "yellow", "green"]},
                },
            },
        },
        "asset_impact": {"type": "array", "minItems": 3, "maxItems": 4, "items": {"type": "string"}},
        "asset_callout": {"type": "string"},
        "calendar": {
            "type": "array",
            "minItems": 4,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["day", "event", "star"],
                "properties": {
                    "day": {"type": "string"},
                    "event": {"type": "string"},
                    "star": {"type": "boolean"},
                },
            },
        },
        "calendar_takeaway": {"type": "string"},
        "scenarios": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["title", "probability", "desc", "tone"],
                "properties": {
                    "title": {"type": "string"},
                    "probability": {"type": "string"},
                    "desc": {"type": "string"},
                    "tone": {"type": "string", "enum": ["a", "b", "c"]},
                },
            },
        },
        "insights": {"type": "array", "minItems": 5, "maxItems": 5, "items": {"type": "string"}},
        "historical_context": {"type": "array", "minItems": 2, "maxItems": 3, "items": {"type": "string"}},
        "historical_callout": {"type": "string"},
        "glossary_terms": {"type": "array", "minItems": 5, "maxItems": 9, "items": {"type": "string"}},
        "investor_guide": {
            "type": "object",
            "required": ["paragraphs", "checklist", "warning"],
            "properties": {
                "paragraphs": {"type": "array", "minItems": 3, "maxItems": 4, "items": {"type": "string"}},
                "checklist": {"type": "array", "minItems": 3, "maxItems": 5, "items": {"type": "string"}},
                "warning": {"type": "string"},
            },
        },
    },
}

LIVE_NUMBER_PATTERN = re.compile(
    r"(WTI|S&P|나스닥|비트코인|BTC|VIX|USD/KRW|달러/원|달러원|DXY|금|유가)[^\n]{0,24}?(\$?\d[\d,]*(?:\.\d+)?%?|\d[\d,]*(?:\.\d+)?원)"
)
OG_DESCRIPTION_PATTERN = re.compile(r"<meta property=\"og:description\" content=\"([^\"]+)\"")
LIVE_NUMBER_TOLERANCE_PCT = 1.0


def load_data() -> dict[str, Any]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing {DATA_PATH}. Run collect_data.py first.")
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def previous_og_description(current_date: str) -> str:
    candidates = sorted(ROOT.glob("briefing-*.html"), reverse=True)
    for path in candidates:
        if path.name == f"briefing-{current_date}.html":
            continue
        match = OG_DESCRIPTION_PATTERN.search(path.read_text(encoding="utf-8"))
        if match:
            return html.unescape(match.group(1))
    return ""


def validate_schema(payload: dict[str, Any]) -> None:
    missing = [key for key in SECTION_SCHEMA["required"] if key not in payload]
    if missing:
        raise ValueError(f"Missing top-level keys: {missing}")
    if len(payload["narrative"]) < 3 or len(payload["narrative"]) > 5:
        raise ValueError("narrative must contain 3-5 paragraphs")
    if len(payload["scenarios"]) != 3:
        raise ValueError("scenarios must contain exactly 3 entries")
    if len(payload["insights"]) != 5:
        raise ValueError("insights must contain exactly 5 items")
    if len(payload["calendar"]) < 4:
        raise ValueError("calendar must contain at least 4 rows")
    if len(payload["glossary_terms"]) < 5:
        raise ValueError("glossary_terms must contain at least 5 terms")
    scenario_tones = {item["tone"] for item in payload["scenarios"]}
    if scenario_tones != {"a", "b", "c"}:
        raise ValueError("scenario tones must include a, b, c exactly once")
    try:
        probabilities = [int(re.sub(r"[^0-9]", "", item["probability"])) for item in payload["scenarios"]]
    except Exception as exc:
        raise ValueError("scenario probabilities must contain numeric percentages") from exc
    if not 95 <= sum(probabilities) <= 105:
        raise ValueError("scenario probabilities should sum to roughly 100%")


def metric_value_for_keyword(keyword: str, data: dict[str, Any]) -> float | None:
    metrics = data["metrics"]
    normalized = keyword.casefold()
    mapping = {
        "wti": metrics["wti"]["value"],
        "유가": metrics["wti"]["value"],
        "s&p": metrics["sp500"]["value"],
        "나스닥": metrics["nasdaq"]["value"],
        "비트코인": metrics["btc"]["value"],
        "btc": metrics["btc"]["value"],
        "vix": metrics["vix"]["value"],
        "usd/krw": metrics["usd_krw"]["value"],
        "달러/원": metrics["usd_krw"]["value"],
        "달러원": metrics["usd_krw"]["value"],
        "dxy": metrics["dxy"]["value"],
        "금": metrics["gold"]["value"],
    }
    return mapping.get(normalized)


def parse_numeric_token(token: str) -> float:
    cleaned = token.replace("$", "").replace("%", "").replace("원", "").replace(",", "").strip()
    return float(cleaned)


def validate_no_live_numbers(payload: dict[str, Any], data: dict[str, Any]) -> None:
    text_fields: list[str] = []
    text_fields.extend(payload["narrative"])
    text_fields.extend(item["desc"] for item in payload["timeline"])
    text_fields.extend(payload["asset_impact"])
    text_fields.append(payload["asset_callout"])
    text_fields.extend(item["event"] for item in payload["calendar"])
    text_fields.append(payload["calendar_takeaway"])
    text_fields.extend(item["desc"] for item in payload["scenarios"])
    text_fields.extend(payload["insights"])
    text_fields.extend(payload["historical_context"])
    text_fields.append(payload["historical_callout"])
    text_fields.extend(payload["investor_guide"]["paragraphs"])
    text_fields.extend(payload["investor_guide"]["checklist"])
    text_fields.append(payload["investor_guide"]["warning"])

    for field in text_fields:
        for keyword, token in LIVE_NUMBER_PATTERN.findall(field):
            expected = metric_value_for_keyword(keyword, data)
            if expected is None:
                raise ValueError(f"Unexpected live-number keyword detected: {keyword}")
            actual = parse_numeric_token(token)
            drift_pct = abs(actual - expected) / expected * 100 if expected else 0.0
            if drift_pct > LIVE_NUMBER_TOLERANCE_PCT:
                raise ValueError(
                    f"Generated live number drifted too far for {keyword}: got {actual}, expected {expected:.4f}"
                )


def load_glossary_terms() -> list[str]:
    glossary_html = (ROOT / "glossary.html").read_text(encoding="utf-8")
    terms = re.findall(r'<span class="term-name">([^<]+)</span>', glossary_html)
    return sorted(set(html.unescape(term) for term in terms))


def prompt_text(data: dict[str, Any], previous_summary: str, glossary_terms: list[str]) -> str:
    metrics = data["metrics"]
    headlines = "\n".join(
        f"- [{item['source']}] {item['title']} ({item['published']})"
        for item in data["news"][:12]
    )
    return f"""
너는 한국어 투자 브리핑 에디터다. 출력은 반드시 JSON만 반환한다.

목표:
- briefing-2026-04-20.html 스타일과 톤을 계승한다.
- 숫자 나열이 아니라 원인→전개→영향의 인과관계를 설명한다.
- 초보 투자자도 이해할 수 있는 한국어로 쓴다.
- 과장 금지, 확률/시나리오 분리는 명확하게 한다.

절대 규칙:
- 현재 시장의 실시간 가격, 수익률, 환율, 지수 레벨은 서술 문장에 직접 쓰지 마라.
- WTI, S&P, BTC, VIX, USD/KRW 등의 최신 숫자는 템플릿이 별도로 삽입한다.
- 문장 속에 '$89', '1,460원', 'VIX 20', '+3%' 같은 라이브 숫자를 쓰지 마라.
- 시나리오도 정성적으로 써라. 미래 가격 목표 숫자 제시 금지.
- HTML은 쓰지 말고 문자열만 준다. 단, <strong>, <span class="hl-up|hl-dn|hl-wr"> 정도의 인라인 태그는 허용한다.

오늘 데이터:
{json.dumps(metrics, ensure_ascii=False, indent=2)}

크립토 공포탐욕:
{json.dumps(data["fear_greed_crypto"], ensure_ascii=False)}

최근 뉴스 헤드라인:
{headlines}

직전 브리핑 OG 설명:
{previous_summary or "없음"}

용어집 후보:
{", ".join(glossary_terms[:120])}

JSON 필드 작성 규칙:
- headline: 메인 제목
- is_urgent: true/false
- lead: 2~3문장 요약
- og_description: 1~2문장, 140자 안팎
- archive_summary: index 카드용 요약, 2문장 이내
- timeline_title: 타임라인 섹션 제목
- narrative: 3~5개 문단
- timeline: 4~6개 이벤트
- asset_impact: 3~4개 문단
- asset_callout: 경고/핵심 패턴 1개
- calendar: 이번 주 일정 4~6개, 가장 중요한 날 star=true
- calendar_takeaway: 일정 요약 1문단
- scenarios: 정확히 3개, tone은 a/b/c 하나씩
- insights: 정확히 5개
- historical_context: 2~3개 문단
- historical_callout: 녹색 인용/교훈 1개
- glossary_terms: 실제 용어집에 있는 용어만 5~9개
- investor_guide.paragraphs: 3~4개
- investor_guide.checklist: 3~5개
- investor_guide.warning: 빨간 경고 박스 본문
""".strip()


def call_gemini(prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is required.")

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name=model_name)
    response = model.generate_content(
        prompt,
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": schema,
            "temperature": 0.5,
        },
    )
    text = (response.text or "").strip()
    if not text:
        raise ValueError("Gemini returned empty response")
    return json.loads(text)


def retry_prompt(base_prompt: str, error: Exception) -> str:
    return base_prompt + f"\n\n이전 응답이 실패한 이유: {error}\n위 규칙을 모두 지키는 JSON만 다시 출력해라."


def metric_tone(change_pct: float, invert: bool = False) -> str:
    change = -change_pct if invert else change_pct
    if change > 0.15:
        return "up"
    if change < -0.15:
        return "dn"
    return "wr"


def format_number(value: float, digits: int = 2) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.{digits}f}"


def build_dashboard(data: dict[str, Any]) -> list[dict[str, str]]:
    metrics = data["metrics"]
    fear = data["fear_greed_crypto"]
    usd_krw = metrics["usd_krw"]["value"]
    return [
        {
            "label": "🛢️ WTI 유가",
            "value": f"${format_number(metrics['wti']['value'])}",
            "sub": f"{metrics['wti']['change_pct']:+.1f}% 전일 대비",
            "tone": metric_tone(metrics["wti"]["change_pct"], invert=True),
        },
        {
            "label": "📉 S&P 500",
            "value": format_number(metrics["sp500"]["value"]),
            "sub": f"{metrics['sp500']['change_pct']:+.1f}% 전일 대비",
            "tone": metric_tone(metrics["sp500"]["change_pct"]),
        },
        {
            "label": "🪙 비트코인",
            "value": f"${format_number(metrics['btc']['value'])}",
            "sub": f"{metrics['btc']['change_pct']:+.1f}% 전일 대비",
            "tone": metric_tone(metrics["btc"]["change_pct"]),
        },
        {
            "label": "😨 코인 F&G",
            "value": str(fear["value"]),
            "sub": f"{fear['classification']} 구간",
            "tone": "dn" if fear["value"] < 40 else "wr" if fear["value"] < 60 else "up",
        },
        {
            "label": "📊 VIX",
            "value": format_number(metrics["vix"]["value"]),
            "sub": f"{metrics['vix']['change_pct']:+.1f}% 전일 대비",
            "tone": metric_tone(metrics["vix"]["change_pct"], invert=True),
        },
        {
            "label": "💵 USD/KRW",
            "value": format_number(usd_krw, 0),
            "sub": f"{metrics['usd_krw']['change_pct']:+.1f}% 전일 대비",
            "tone": metric_tone(metrics["usd_krw"]["change_pct"], invert=True),
        },
    ]


def date_labels(date_str: str) -> tuple[str, str]:
    dt = datetime.fromisoformat(date_str).date()
    weekday = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
    return f"{dt.year}년 {dt.month}월 {dt.day}일 {weekday}요일", f"{dt.year}년 {dt.month}월 {dt.day}일 ({weekday})"


def archive_tags(data: dict[str, Any]) -> list[dict[str, str]]:
    metrics = data["metrics"]
    fear = data["fear_greed_crypto"]
    return [
        {"kind": "dn" if metrics["wti"]["change_pct"] > 0 else "hl", "text": f"🛢️ WTI ${format_number(metrics['wti']['value'])}"},
        {
            "kind": "dn" if metrics["sp500"]["change_pct"] < 0 else "hl",
            "text": f"📉 S&P {metrics['sp500']['change_pct']:+.1f}%",
        },
        {"kind": "wr", "text": f"🪙 BTC ${format_number(metrics['btc']['value'])}"},
        {"kind": "hl" if fear["value"] >= 60 else "wr" if fear["value"] >= 40 else "dn", "text": f"😨 F&G {fear['value']}"},
    ]


def render_briefing(payload: dict[str, Any], data: dict[str, Any]) -> Path:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=False,
        lstrip_blocks=False,
    )
    template = env.get_template("briefing.html.j2")
    date_label, archive_date_label = date_labels(data["date"])
    briefing_path = ROOT / f"briefing-{data['date']}.html"
    meta_title = payload["headline"]
    html_output = template.render(
        meta={
            "title": meta_title,
            "description": payload["og_description"],
            "twitter_description": payload["og_description"][:120],
            "url": f"{SITE_URL}/briefing-{data['date']}.html",
        },
        article={
            "date_label": date_label,
            "archive_date_label": archive_date_label,
            **payload,
        },
        dashboard=build_dashboard(data),
    )
    briefing_path.write_text(html_output, encoding="utf-8")
    return briefing_path


def render_card_context(payload: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    _, archive_date_label = date_labels(data["date"])
    return {
        "href": f"briefing-{data['date']}.html",
        "date_label": archive_date_label,
        "title": payload["headline"],
        "summary": payload["archive_summary"],
        "is_crisis": payload["is_urgent"],
        "report_type": "crisis" if payload["is_urgent"] else "daily",
        "tags": archive_tags(data),
    }


def write_manifest(card_context: dict[str, Any]) -> None:
    manifest_path = ROOT / "data" / "render_manifest.json"
    manifest_path.write_text(json.dumps(card_context, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    data = load_data()
    glossary_terms = load_glossary_terms()
    prompt = prompt_text(data, previous_og_description(data["date"]), glossary_terms)
    last_error: Exception | None = None
    payload: dict[str, Any] | None = None

    for attempt in range(2):
        try:
            payload = call_gemini(prompt if attempt == 0 else retry_prompt(prompt, last_error or Exception("unknown")), SECTION_SCHEMA)
            validate_schema(payload)
            validate_no_live_numbers(payload, data)
            invalid_terms = [term for term in payload["glossary_terms"] if html.unescape(term) not in glossary_terms]
            if invalid_terms:
                raise ValueError(f"glossary_terms contained unknown terms: {invalid_terms}")
            break
        except Exception as exc:
            last_error = exc
            payload = None

    if payload is None:
        raise RuntimeError(f"Failed to generate valid briefing JSON after retry: {last_error}")

    briefing_path = render_briefing(payload, data)
    write_manifest(render_card_context(payload, data))
    print(f"Rendered {briefing_path}")


if __name__ == "__main__":
    main()
