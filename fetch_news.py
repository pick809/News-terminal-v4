#!/usr/bin/env python3
"""
Trae el feed RSS público de FinancialJuice, lo fusiona con el histórico
ya guardado en data/news.json (sin duplicar) y vuelve a escribir el archivo.
Pensado para correr en GitHub Actions cada pocos minutos.
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

FEED_URL = "https://www.financialjuice.com/feed.ashx?xy=rss"
DATA_PATH = Path("data/news.json")
MAX_ITEMS = 20000  # tope de seguridad para no dejar crecer el archivo sin límite
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_feed_xml() -> str:
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_items(xml_text: str):
    # Escapa & sueltos que rompen el parser XML (común en estos feeds)
    xml_text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", xml_text)
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").replace("FinancialJuice: ", "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        desc_raw = item.findtext("description") or ""
        desc = re.sub(r"<[^>]+>", " ", desc_raw)
        desc = re.sub(r"\s+", " ", desc).strip()
        guid = (item.findtext("guid") or link).strip()
        if not title or not link:
            continue
        items.append(
            {"id": guid, "title": title, "link": link, "pubDate": pub_date, "desc": desc}
        )
    return items


def load_existing():
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def merge(existing, new_items):
    seen = {it["id"] for it in existing}
    added = 0
    for it in new_items:
        if it["id"] not in seen:
            existing.append(it)
            seen.add(it["id"])
            added += 1

    def sort_key(it):
        try:
            return datetime.strptime(it["pubDate"], "%a, %d %b %Y %H:%M:%S %Z")
        except Exception:
            return datetime.min

    existing.sort(key=sort_key, reverse=True)
    if len(existing) > MAX_ITEMS:
        existing = existing[:MAX_ITEMS]
    return existing, added


def main():
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        xml_text = fetch_feed_xml()
        new_items = parse_items(xml_text)
    except Exception as e:
        print(f"ERROR al traer/parsear el feed: {e}", file=sys.stderr)
        sys.exit(1)

    existing = load_existing()
    merged, added = merge(existing, new_items)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(merged),
        "items": merged,
    }
    DATA_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"OK. {added} noticias nuevas. Total acumulado: {len(merged)}")
    # exit code 0 siempre que no haya habido error de red/parseo


if __name__ == "__main__":
    main()
