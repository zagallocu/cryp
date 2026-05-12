#!/usr/bin/env python3
"""
Günlük Yapay Zeka Haber Toplayıcısı ve Editörü
Her sabah 08:00 Türkiye saatiyle çalışır, son 24 saatin AI haberlerini Türkçe özetler.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field
from typing import Optional
import time

import json
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import urllib.request
import urllib.error
import urllib.parse

import anthropic
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

TURKEY_TZ = ZoneInfo("Europe/Istanbul")

# RSS kaynakları ve öncelik skorları
RSS_SOURCES = [
    {"name": "TechCrunch AI",          "url": "https://techcrunch.com/category/artificial-intelligence/feed/",          "priority": 10},
    {"name": "The Verge AI",            "url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",      "priority": 10},
    {"name": "VentureBeat AI",          "url": "https://venturebeat.com/category/ai/feed/",                              "priority": 9},
    {"name": "MIT Technology Review",   "url": "https://www.technologyreview.com/feed/",                                 "priority": 9},
    {"name": "Wired AI",                "url": "https://www.wired.com/feed/tag/ai/latest/rss",                          "priority": 8},
    {"name": "Reuters Technology",      "url": "https://feeds.reuters.com/reuters/technologyNews",                       "priority": 8},
    {"name": "Bloomberg Technology",    "url": "https://feeds.bloomberg.com/technology/news.rss",                        "priority": 8},
    {"name": "Hacker News",             "url": "https://news.ycombinator.com/rss",                                       "priority": 6},
    {"name": "ArXiv CS.AI",             "url": "https://rss.arxiv.org/rss/cs.AI",                                       "priority": 7},
    {"name": "Google News AI",          "url": "https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en", "priority": 7},
]

# Öncelik artıran anahtar kelimeler
HIGH_PRIORITY_KEYWORDS = [
    "gpt", "gemini", "claude", "llama", "mistral", "deepseek", "grok",
    "openai", "anthropic", "google deepmind", "meta ai", "mistral ai",
    "model release", "new model", "launch", "breakthrough", "benchmark",
    "regulation", "ban", "law", "policy", "billion", "acquisition",
    "agi", "superintelligence", "reasoning model", "multimodal",
    "fine-tuning", "open source", "open-weight", "foundation model",
]

AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning", "neural network",
    "large language model", "llm", "generative ai", "ai model", "ai system",
    "chatgpt", "gpt", "gemini", "claude", "llama", "openai", "anthropic",
    "deepmind", "hugging face", "transformer", "diffusion model", "computer vision",
    "natural language", "reinforcement learning", "fine-tuning", "inference",
    "ai chip", "ai regulation", "ai safety", "alignment", "agi",
    "copilot", "ai assistant", "ai agent", "agentic", "autonomous",
]


@dataclass
class NewsArticle:
    title: str
    url: str
    source: str
    published: datetime
    summary: str = ""
    source_priority: int = 5
    relevance_score: float = 0.0
    turkish_title: str = ""
    turkish_summary: str = ""


def is_ai_related(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in AI_KEYWORDS)


def compute_relevance(article: NewsArticle) -> float:
    text = (article.title + " " + article.summary).lower()
    score = float(article.source_priority)
    for kw in HIGH_PRIORITY_KEYWORDS:
        if kw in text:
            score += 2.0
    # Yenilik bonusu: ne kadar yeni o kadar yüksek
    age_hours = (datetime.now(timezone.utc) - article.published).total_seconds() / 3600
    freshness = max(0, 24 - age_hours)
    score += freshness * 0.3
    return score


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}


def _fetch_rss_xml(url: str, timeout: int = 20) -> Optional[str]:
    req = urllib.request.Request(url, headers=_HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            log.warning("HTTP %d hatası %s (deneme %d/3)", exc.code, url, attempt + 1)
            if exc.code in (403, 404, 410):
                break
            time.sleep(2 ** attempt)
        except urllib.error.URLError as exc:
            log.warning("Bağlantı hatası %s: %s (deneme %d/3)", url, exc, attempt + 1)
            time.sleep(2 ** attempt)
        except Exception as exc:
            log.warning("Beklenmeyen hata %s: %s", url, exc)
            break
    return None


def _parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        pass
    # ISO 8601 denemesi
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str[:19], fmt[:len(date_str)])
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _parse_rss(xml_text: str, source_name: str, source_priority: int, cutoff: datetime) -> list[NewsArticle]:
    articles: list[NewsArticle] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("XML parse hatası (%s): %s", source_name, exc)
        return articles

    # RSS 2.0 ve Atom desteği
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns) or root.findall(".//entry")

    for item in items:
        def txt(tag: str) -> str:
            el = item.find(tag)
            return (el.text or "").strip() if el is not None else ""

        title = txt("title")
        url = txt("link")
        if not url:
            # Atom <link href="...">
            link_el = item.find("link")
            if link_el is not None:
                url = link_el.get("href", "")

        summary = txt("description") or txt("summary") or txt("content")
        pub_str = txt("pubDate") or txt("published") or txt("updated")
        pub = _parse_date(pub_str)

        if not title or not url:
            continue
        if pub is not None and pub < cutoff:
            continue
        if not is_ai_related(title, summary):
            continue

        art = NewsArticle(
            title=title,
            url=url,
            source=source_name,
            published=pub or datetime.now(timezone.utc),
            summary=summary[:1000],
            source_priority=source_priority,
        )
        art.relevance_score = compute_relevance(art)
        articles.append(art)

    return articles


def fetch_gnews(hours: int = 24) -> list[NewsArticle]:
    """GNews API üzerinden haber çeker (GNEWS_KEY gerekir, gnews.io ücretsiz plan: 100 istek/gün)."""
    api_key = os.getenv("GNEWS_KEY", "")
    if not api_key:
        return []

    queries = [
        "artificial intelligence",
        "OpenAI OR Anthropic OR DeepMind",
        "LLM OR ChatGPT OR Gemini OR Claude",
    ]
    articles: list[NewsArticle] = []

    for q in queries:
        params = urllib.parse.urlencode({
            "q": q,
            "lang": "en",
            "sortby": "publishedAt",
            "max": 10,
            "token": api_key,
        })
        url = f"https://gnews.io/api/v4/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "AINewsAggregator/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            log.warning("GNews API hatası (%s): %s", q, exc)
            continue

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        for item in data.get("articles", []):
            title = (item.get("title") or "").strip()
            url_ = (item.get("url") or "").strip()
            summary = (item.get("description") or item.get("content") or "").strip()
            pub_str = item.get("publishedAt", "")
            pub = _parse_date(pub_str)
            source_name = item.get("source", {}).get("name", "GNews")

            if not title or not url_:
                continue
            if pub is not None and pub < cutoff:
                continue
            if not is_ai_related(title, summary):
                continue

            art = NewsArticle(
                title=title,
                url=url_,
                source=f"GNews/{source_name}",
                published=pub or datetime.now(timezone.utc),
                summary=summary[:1000],
                source_priority=7,
            )
            art.relevance_score = compute_relevance(art)
            articles.append(art)

    log.info("GNews: %d AI haberi bulundu", len(articles))
    return articles


def fetch_articles(hours: int = 24) -> list[NewsArticle]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    articles: list[NewsArticle] = []

    for source in RSS_SOURCES:
        log.info("Çekiliyor: %s", source["name"])
        xml_text = _fetch_rss_xml(source["url"])
        if xml_text:
            found = _parse_rss(xml_text, source["name"], source["priority"], cutoff)
            log.info("  → %d AI haberi bulundu", len(found))
            articles.extend(found)

    # GNews ek kaynak olarak
    articles.extend(fetch_gnews(hours=hours))

    # Tekrar eden URL'leri temizle
    seen: set[str] = set()
    unique: list[NewsArticle] = []
    for a in articles:
        if a.url not in seen:
            seen.add(a.url)
            unique.append(a)

    unique.sort(key=lambda a: a.relevance_score, reverse=True)
    log.info("Toplam %d benzersiz AI haberi bulundu.", len(unique))
    return unique


def summarize_with_claude(articles: list[NewsArticle], max_articles: int = 10) -> list[NewsArticle]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY ortam değişkeni ayarlanmamış.")

    client = anthropic.Anthropic(api_key=api_key)
    top = articles[:max_articles]

    articles_text = ""
    for i, art in enumerate(top, 1):
        articles_text += (
            f"\n---HABER {i}---\n"
            f"Başlık: {art.title}\n"
            f"Kaynak: {art.source}\n"
            f"URL: {art.url}\n"
            f"Özet/İçerik: {art.summary}\n"
        )

    prompt = f"""Sen deneyimli bir teknoloji gazetecisisin. Aşağıdaki {len(top)} yapay zeka haberini Türkçe olarak özetle.

Her haber için şunları üret:
1. TÜRKÇE_BAŞLIK: Haberin Türkçe başlığı (doğal ve akıcı olsun)
2. TÜRKÇE_ÖZET: 3-5 cümlelik Türkçe özet. Şu soruları yanıtla: Ne oldu? Kim yaptı? Neden önemli?

Kurallar:
- LLM, fine-tuning, benchmark, GPU, API, RAG, AGI gibi teknik terimleri olduğu gibi bırak, ilk geçişte parantez içinde kısaca açıkla.
- Özet akıcı, bilgilendirici ve tarafsız olsun.
- Her haberi aşağıdaki formatta ver:

===HABER_1===
TÜRKÇE_BAŞLIK: ...
TÜRKÇE_ÖZET: ...
===HABER_2===
...

Haberler:
{articles_text}
"""

    log.info("Claude API'ye %d haber gönderiliyor...", len(top))
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text
    _parse_claude_response(response_text, top)
    return top


def _parse_claude_response(text: str, articles: list[NewsArticle]) -> None:
    blocks = re.split(r"===HABER_\d+===", text)
    blocks = [b.strip() for b in blocks if b.strip()]

    for i, block in enumerate(blocks):
        if i >= len(articles):
            break
        title_match = re.search(r"TÜRKÇE_BAŞLIK:\s*(.+)", block)
        summary_match = re.search(r"TÜRKÇE_ÖZET:\s*([\s\S]+?)(?=TÜRKÇE_|$)", block)

        if title_match:
            articles[i].turkish_title = title_match.group(1).strip()
        if summary_match:
            articles[i].turkish_summary = summary_match.group(1).strip()


def format_digest(articles: list[NewsArticle]) -> str:
    now_tr = datetime.now(TURKEY_TZ)
    date_str = now_tr.strftime("%d/%m/%Y")
    total = len(articles)
    translated = sum(1 for a in articles if a.turkish_title)

    lines = []
    lines.append("─" * 60)
    lines.append(f"📅 TARİH: {date_str} — Günlük Yapay Zeka Haber Özeti")
    lines.append("─" * 60)

    if not articles:
        lines.append("\n⚠️  Son 24 saatte önemli bir AI haberi bulunamadı.\n")
        lines.append("─" * 60)
        return "\n".join(lines)

    # Öne çıkan haber
    top = articles[0]
    lines.append("")
    lines.append("🔥 GÜNÜN ÖNE ÇIKAN HABERİ")
    lines.append(top.turkish_title or top.title)
    lines.append("")
    lines.append(top.turkish_summary or top.summary)
    lines.append(f"🔗 Kaynak: {top.url}")

    # Diğer haberler
    if len(articles) > 1:
        lines.append("")
        lines.append("─" * 60)
        lines.append("📰 DİĞER ÖNEMLİ HABERLER")
        lines.append("")
        for idx, art in enumerate(articles[1:], 1):
            lines.append(f"{idx}. {art.turkish_title or art.title}")
            lines.append(art.turkish_summary or art.summary)
            lines.append(f"   🔗 Kaynak: {art.url}")
            lines.append("")

    lines.append("─" * 60)
    lines.append(f"📊 BUGÜNÜN ÖZETİ: Toplam {total} haber işlendi, {translated} tanesi Türkçeye çevrildi.")
    lines.append("─" * 60)

    return "\n".join(lines)


def save_digest(digest: str) -> str:
    now_tr = datetime.now(TURKEY_TZ)
    filename = f"ai_news_{now_tr.strftime('%Y-%m-%d')}.txt"
    output_dir = os.getenv("OUTPUT_DIR", ".")
    path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(digest)
    return path


def run() -> str:
    log.info("Haber toplama başlıyor...")
    articles = fetch_articles(hours=24)

    if not articles:
        log.warning("Son 24 saatte AI haberi bulunamadı.")
        digest = format_digest([])
        path = save_digest(digest)
        print(digest)
        return path

    articles = summarize_with_claude(articles, max_articles=10)
    digest = format_digest(articles)
    path = save_digest(digest)
    print(digest)
    log.info("Özet kaydedildi: %s", path)
    return path


def run_demo() -> None:
    """API anahtarı olmadan örnek çıktı gösterir."""
    sample_articles = [
        NewsArticle(
            title="OpenAI Launches GPT-5 with Enhanced Reasoning",
            url="https://openai.com/blog/gpt-5",
            source="Demo",
            published=datetime.now(timezone.utc),
            summary="OpenAI released GPT-5, a new frontier model with improved reasoning capabilities.",
            source_priority=10,
            turkish_title="OpenAI, Gelişmiş Akıl Yürütme Özelliğiyle GPT-5'i Tanıttı",
            turkish_summary=(
                "OpenAI, yapay zeka (YZ) alanında yeni bir çığır açan GPT-5 modelini duyurdu. "
                "GPT-5, karmaşık mantıksal problemleri çözmede önceki sürümlere kıyasla belirgin "
                "bir performans artışı sunuyor. Model, özellikle kodlama, matematik ve bilimsel "
                "çıkarım görevlerinde benchmark (performans ölçüt) testlerinde rekor kırdı. "
                "Bu gelişme, LLM (Büyük Dil Modeli) yarışında rekabeti daha da kızıştıracak."
            ),
            relevance_score=30.0,
        ),
        NewsArticle(
            title="Google Releases Gemma 4 Open-Weight Model",
            url="https://blog.google/technology/developers-tools/gemma-4/",
            source="Demo",
            published=datetime.now(timezone.utc),
            summary="Google released Gemma 4, an open-source model for advanced reasoning.",
            source_priority=9,
            turkish_title="Google, Açık Ağırlıklı Gemma 4 Modelini Yayımladı",
            turkish_summary=(
                "Google DeepMind, Gemma 4 adlı yeni açık kaynaklı (open-weight) modelini Apache 2.0 "
                "lisansıyla yayımladı. Model, 256K token'lık (metin birimi) bağlam penceresi ve "
                "140'tan fazla dil desteğiyle dikkat çekiyor. Gemma 4, özellikle ajan (agentic) "
                "iş akışları ve ileri akıl yürütme görevleri için optimize edildi. "
                "Geliştiriciler modeli ücretsiz olarak indirip kendi uygulamalarına entegre edebilir."
            ),
            relevance_score=25.0,
        ),
    ]
    digest = format_digest(sample_articles)
    print(digest)
    print("\n[DEMO MODU — Gerçek haberler için ANTHROPIC_API_KEY tanımlayın]")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        run()
