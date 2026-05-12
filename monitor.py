"""
IREN News Monitor — polls the IREN press release RSS feed and emails
new items (Korean summary + excerpt + publish time + original link).

Run by GitHub Actions on a 5-minute cron. State (seen guids) is committed
back to the repo after each successful send so reruns don't duplicate.
"""
import html
import json
import os
import smtplib
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from pathlib import Path

from anthropic import Anthropic

RSS_URL = "https://irisenergy.gcs-web.com/rss/news-releases.xml"
STATE_PATH = Path("state/seen.json")
MAX_PER_RUN = 5
MODEL = "claude-haiku-4-5-20251001"

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_PASSWORD = os.environ["GMAIL_PASSWORD"]
RECIPIENTS = [r.strip() for r in os.environ["RECIPIENTS"].split(",") if r.strip()]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or ""


def fetch_rss() -> bytes:
    req = urllib.request.Request(
        RSS_URL,
        headers={"User-Agent": "iren-news-monitor/1.0 (+github.com/bestfo/iren-news-monitor)"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_items(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.iter("item"):
        def text(tag):
            el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""
        items.append({
            "guid": text("guid"),
            "title": html.unescape(text("title")),
            "link": text("link"),
            "pubDate": text("pubDate"),
            "description": html.unescape(text("description")),
        })
    return items


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"seen_guids": [], "first_run": True}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def summarize_ko(client, title: str, description: str) -> str:
    if client is None:
        return description  # fallback: original English description
    msg = client.messages.create(
        model=MODEL,
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": (
                "다음 IREN(NASDAQ: IREN) 보도자료를 한국어로 2~3문장 객관적으로 요약하세요. "
                "주식 투자자가 핵심 정보를 빠르게 파악할 수 있도록 숫자·사실 위주로. "
                "감탄사, 추측, 과장 표현 금지. 본문에 없는 내용 추가 금지.\n\n"
                f"제목: {title}\n\n"
                f"본문(영문 요약):\n{description}"
            ),
        }],
    )
    return msg.content[0].text.strip()


def build_email_html(item: dict, summary_ko: str) -> str:
    return (
        '<html><body style="font-family: -apple-system, Segoe UI, sans-serif; max-width: 640px;">'
        f'<h2 style="margin-bottom:4px;">{html.escape(item["title"])}</h2>'
        f'<p style="color:#666; margin-top:0;"><b>발표 시각:</b> {html.escape(item["pubDate"])}</p>'
        f'<p><b>요약</b><br>{html.escape(summary_ko).replace(chr(10), "<br>")}</p>'
        '<p><b>발췌 (원문)</b></p>'
        f'<blockquote style="border-left:3px solid #ccc; margin:0; padding:8px 12px; color:#444;">'
        f'{html.escape(item["description"])}</blockquote>'
        f'<p><a href="{html.escape(item["link"])}">▶ 원문 보기</a></p>'
        '<hr><p style="font-size:11px; color:#999;">IREN News Monitor · GitHub Actions</p>'
        '</body></html>'
    )


def send_email(subject: str, body_html: str) -> None:
    msg = EmailMessage()
    msg["From"] = f"IREN News <{GMAIL_USER}>"
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Subject"] = subject
    msg.set_content("HTML 본문을 표시할 수 없는 메일 클라이언트입니다. HTML 보기를 활성화하세요.")
    msg.add_alternative(body_html, subtype="html")
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(GMAIL_USER, GMAIL_PASSWORD)
        smtp.send_message(msg)


def main() -> int:
    try:
        xml_bytes = fetch_rss()
    except Exception as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        return 0  # next run retries

    items = parse_items(xml_bytes)
    if not items:
        print("no items parsed")
        return 0

    state = load_state()
    if state.get("first_run") or not state.get("seen_guids"):
        state = {
            "seen_guids": [it["guid"] for it in items],
            "first_run": False,
        }
        save_state(state)
        print(f"first run — seeded {len(items)} items")
        return 0

    seen = set(state["seen_guids"])
    new_items = [it for it in items if it["guid"] not in seen]
    if not new_items:
        print("no new items")
        return 0

    # RSS lists newest first; emit oldest-new first for chronological email order
    new_items = list(reversed(new_items))[:MAX_PER_RUN]
    print(f"new items to send: {len(new_items)}")

    client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
    if client is None:
        print("WARNING: ANTHROPIC_API_KEY not set — using raw English description as summary", file=sys.stderr)

    for item in new_items:
        try:
            summary = summarize_ko(client, item["title"], item["description"])
            html_body = build_email_html(item, summary)
            subject = f"[IREN] {item['title']}"
            send_email(subject, html_body)
            print(f"sent: {item['guid']} {item['title'][:60]}")
            state["seen_guids"].append(item["guid"])
            save_state(state)
        except Exception as e:
            print(f"failed item {item['guid']}: {e}", file=sys.stderr)
            return 1  # surface failure but don't lose progress (seen.json already saved per-success)

    return 0


if __name__ == "__main__":
    sys.exit(main())
