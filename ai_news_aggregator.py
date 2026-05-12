#!/usr/bin/env python3
"""
Günlük Yapay Zeka Haber Toplayıcısı ve Editörü
Her sabah 08:00 Türkiye saatiyle çalışır, son 24 saatin AI haberlerini Türkçe özetler.
"""

import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
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

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

TURKEY_TZ = ZoneInfo("Europe/Istanbul")

# ── RSS Kaynakları ─────────────────────────────────────────────────────────────
# Öncelik: 10=en yüksek (resmi lab blogları), 6=genel tech haberleri
RSS_SOURCES = [
    # Resmi AI Lab Blogları (öncelik 10)
    {"name": "OpenAI Blog",         "url": "https://openai.com/news/rss.xml",                                                                    "priority": 10},
    {"name": "Anthropic Blog",      "url": "https://www.anthropic.com/news/rss",                                                                 "priority": 10},
    {"name": "Google DeepMind",     "url": "https://deepmind.google/discover/blog/rss.xml",                                                      "priority": 10},
    {"name": "Google AI Blog",      "url": "https://blog.google/technology/ai/rss/",                                                             "priority": 10},
    {"name": "Meta AI Blog",        "url": "https://engineering.fb.com/category/ai-research/feed/",                                              "priority": 10},
    {"name": "Hugging Face Blog",   "url": "https://huggingface.co/blog/feed.xml",                                                               "priority": 10},
    {"name": "Mistral AI Blog",     "url": "https://mistral.ai/fr/news/rss",                                                                     "priority": 9},
    {"name": "xAI Blog",            "url": "https://x.ai/news/rss.xml",                                                                          "priority": 9},
    {"name": "Microsoft AI Blog",   "url": "https://blogs.microsoft.com/ai/feed/",                                                               "priority": 9},
    {"name": "NVIDIA AI Blog",      "url": "https://blogs.nvidia.com/blog/category/deep-learning/feed/",                                         "priority": 9},

    # Haber & Analiz (öncelik 8-7)
    {"name": "TechCrunch AI",       "url": "https://techcrunch.com/category/artificial-intelligence/feed/",                                      "priority": 8},
    {"name": "The Verge AI",        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",                                  "priority": 8},
    {"name": "VentureBeat AI",      "url": "https://venturebeat.com/category/ai/feed/",                                                          "priority": 8},
    {"name": "MIT Tech Review AI",  "url": "https://www.technologyreview.com/feed/",                                                             "priority": 8},
    {"name": "Wired AI",            "url": "https://www.wired.com/feed/tag/ai/latest/rss",                                                       "priority": 7},
    {"name": "Ars Technica AI",     "url": "https://feeds.arstechnica.com/arstechnica/index",                                                    "priority": 7},
    {"name": "MarkTechPost",        "url": "https://www.marktechpost.com/feed/",                                                                 "priority": 7},
    {"name": "The Gradient",        "url": "https://thegradient.pub/rss/",                                                                       "priority": 7},

    # Araştırma / Teknik — SINIRLI (öncelik 6, en fazla 15 makale alınır)
    {"name": "ArXiv CS.AI",         "url": "https://rss.arxiv.org/rss/cs.AI",                                                                   "priority": 6, "max_items": 15},
    {"name": "ArXiv CS.LG",         "url": "https://rss.arxiv.org/rss/cs.LG",                                                                   "priority": 6, "max_items": 10},
    {"name": "ArXiv CS.CL",         "url": "https://rss.arxiv.org/rss/cs.CL",                                                                   "priority": 6, "max_items": 10},
    {"name": "AI Alignment Forum",  "url": "https://www.alignmentforum.org/feed.xml",                                                            "priority": 7},

    # Topluluk (öncelik 6)
    {"name": "Reddit r/MachineLearning", "url": "https://www.reddit.com/r/MachineLearning/.rss?sort=top&t=day",                                 "priority": 6},
    {"name": "Reddit r/LocalLLaMA",      "url": "https://www.reddit.com/r/LocalLLaMA/.rss?sort=top&t=day",                                      "priority": 6},
    {"name": "Hacker News AI",           "url": "https://hnrss.org/newest?q=AI+OR+LLM+OR+GPT+OR+machine+learning&points=50",                   "priority": 6},

    # Google News (öncelik 7)
    {"name": "GNews: Model Releases",   "url": "https://news.google.com/rss/search?q=AI+model+release+OR+LLM+launch&hl=en-US&gl=US&ceid=US:en", "priority": 7},
    {"name": "GNews: AI Research",      "url": "https://news.google.com/rss/search?q=OpenAI+OR+Anthropic+OR+DeepMind+AI+2026&hl=en-US&gl=US&ceid=US:en", "priority": 7},
]

# ── Öncelik artıran anahtar kelimeler ────────────────────────────────────────
HIGH_PRIORITY_KEYWORDS = [
    # Model ve lab isimleri
    "gpt", "gemini", "claude", "llama", "mistral", "deepseek", "grok", "phi",
    "qwen", "gemma", "command r", "falcon", "yi ", "solar", "wizard",
    "openai", "anthropic", "deepmind", "meta ai", "mistral ai", "xai", "cohere",
    "stability ai", "inflection", "adept", "character.ai", "perplexity",
    # Teknik gelişmeler
    "model release", "new model", "launched", "released", "unveiled", "introduced",
    "benchmark", "state-of-the-art", "sota", "outperforms", "surpasses",
    "reasoning", "multimodal", "vision language", "text-to-", "diffusion",
    "fine-tuning", "rlhf", "dpo", "rag", "agent", "agentic", "tool use",
    "context window", "inference", "quantization", "open-weight", "open source",
    "foundation model", "pre-training", "post-training", "alignment",
    # Önemli olaylar
    "agi", "superintelligence", "breakthrough", "billion parameters",
    "acquisition", "funding", "valuation", "regulation", "executive order",
    "safety", "alignment", "hallucination", "jailbreak", "copyright",
]

# ── AI ilgililik filtreleme ───────────────────────────────────────────────────
AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning", "neural network",
    "large language model", "llm", "generative ai", "foundation model",
    "chatgpt", "gpt-", "gpt4", "gpt5", "gemini", "claude", "llama", "mistral",
    "deepseek", "grok", "phi-", "qwen", "gemma", "falcon",
    "openai", "anthropic", "deepmind", "hugging face", "huggingface",
    "transformer", "diffusion model", "stable diffusion", "midjourney", "dall-e",
    "computer vision", "natural language processing", "nlp",
    "reinforcement learning", "rlhf", "fine-tuning", "fine tuning",
    "ai model", "ai system", "ai agent", "ai safety", "ai alignment",
    "ai regulation", "ai chip", "gpu", "tpu", "nvidia", "ai research",
    "benchmark", "reasoning model", "multimodal", "text-to-image", "text-to-video",
    "copilot", "ai assistant", "chatbot", "agi", "superintelligence",
    "inference", "context window", "tokenizer", "embedding", "vector",
    "prompt", "prompt engineering", "retrieval augmented", "rag",
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


ARXIV_SOURCES = {"ArXiv CS.AI", "ArXiv CS.LG", "ArXiv CS.CL"}

def is_ai_related(title: str, summary: str, source: str = "") -> bool:
    # ArXiv makaleleri zaten AI konuludur, hepsini dahil et
    if source in ARXIV_SOURCES:
        return True
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


def _strip_html(text: str) -> str:
    """HTML tag'lerini ve entity'leri temizler."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


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

        summary = _strip_html(txt("description") or txt("summary") or txt("content"))
        title   = _strip_html(title)
        pub_str = txt("pubDate") or txt("published") or txt("updated")
        pub = _parse_date(pub_str)

        if not title or not url:
            continue
        if pub is not None and pub < cutoff:
            continue
        if not is_ai_related(title, summary, source_name):
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
        "OpenAI OR Anthropic OR DeepMind OR \"Meta AI\"",
        "LLM OR \"large language model\" OR \"AI model\" release",
        "ChatGPT OR Gemini OR Claude OR Llama OR Mistral OR DeepSeek",
        "AI safety OR AI alignment OR AGI OR superintelligence",
        "AI regulation OR \"executive order\" AI OR AI law 2026",
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
            max_items = source.get("max_items")
            if max_items:
                found = found[:max_items]
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


def _build_prompt(articles_text: str, count: int) -> str:
    return f"""Sen deneyimli bir teknoloji gazetecisisin. Aşağıdaki {count} yapay zeka haberini Türkçe olarak özetle.

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
{articles_text}"""


def _articles_to_text(articles: list[NewsArticle]) -> str:
    text = ""
    for i, art in enumerate(articles, 1):
        text += (
            f"\n---HABER {i}---\n"
            f"Başlık: {art.title}\n"
            f"Kaynak: {art.source}\n"
            f"URL: {art.url}\n"
            f"Özet/İçerik: {art.summary}\n"
        )
    return text


def _summarize_anthropic(prompt: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _summarize_groq(prompt: str) -> str:
    """Groq ücretsiz API — console.groq.com üzerinden key alınabilir."""
    api_key = os.environ["GROQ_API_KEY"]
    groq_models = [
        "llama-3.3-70b-versatile",
        "llama3-70b-8192",
        "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768",
        "llama-3.1-8b-instant",
    ]
    last_error = ""
    for model in groq_models:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            log.info("Groq modeli kullanıldı: %s", model)
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            last_error = f"Groq/{model} HTTP {exc.code}: {body[:200]}"
            log.warning("Groq %s başarısız: HTTP %d — sıradaki model...", model, exc.code)
    raise RuntimeError(last_error)


def _summarize_gemini(prompt: str) -> str:
    """Google Gemini ücretsiz API — aistudio.google.com üzerinden key alınabilir."""
    api_key = os.environ["GEMINI_API_KEY"]
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.3},
    }).encode()

    for model in ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash-preview-05-20", "gemini-1.5-flash-latest", "gemini-1.5-pro-latest"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            log.info("Gemini modeli kullanıldı: %s", model)
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if exc.code in (429, 404):
                log.warning("Gemini %s başarısız (HTTP %d), sıradaki model deneniyor...", model, exc.code)
            else:
                raise RuntimeError(f"Gemini HTTP {exc.code}: {body[:200]}") from exc
    raise RuntimeError("Tüm Gemini modelleri kota aşımında. OpenRouter veya Groq deneyin.")


def _summarize_openrouter(prompt: str) -> str:
    """OpenRouter — ücretsiz modeller, Cloudflare yok. openrouter.ai üzerinden key alınabilir."""
    api_key = os.environ["OPENROUTER_API_KEY"]
    free_models = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "google/gemma-2-9b-it:free",
        "qwen/qwen-2.5-7b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-8b:free",
        "liquid/lfm-40b:free",
    ]
    last_error = ""
    for model in free_models:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/zagallocu/cryp",
                "X-Title": "AI News Aggregator",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
            if data.get("choices"):
                log.info("OpenRouter modeli kullanıldı: %s", model)
                return data["choices"][0]["message"]["content"]
            last_error = f"OpenRouter boş yanıt: {data}"
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            last_error = f"OpenRouter/{model} HTTP {exc.code}: {body[:200]}"
            if exc.code == 429:
                log.warning("OpenRouter %s rate limit, 15s bekleniyor...", model)
                time.sleep(15)
                # Aynı modeli bir kez daha dene
                try:
                    with urllib.request.urlopen(req, timeout=90) as resp2:
                        data = json.loads(resp2.read())
                    if data.get("choices"):
                        log.info("OpenRouter modeli kullanıldı (retry): %s", model)
                        return data["choices"][0]["message"]["content"]
                except Exception:
                    pass
            elif exc.code == 404:
                log.debug("OpenRouter %s mevcut değil, sonraki deneniyor.", model)
            else:
                log.warning("OpenRouter %s başarısız: HTTP %d", model, exc.code)
    raise RuntimeError(last_error)


def _summarize_cerebras(prompt: str) -> str:
    """Cerebras — ücretsiz, çok hızlı. inference.cerebras.ai üzerinden key alınabilir."""
    api_key = os.environ["CEREBRAS_API_KEY"]
    for model in ["llama-3.3-70b", "llama3.1-70b", "llama-4-scout-17b-16e-instruct", "llama3.1-8b"]:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            "https://api.cerebras.ai/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
            if data.get("choices"):
                log.info("Cerebras modeli kullanıldı: %s", model)
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            log.warning("Cerebras %s başarısız: HTTP %d — %s", model, exc.code, body[:100])
    raise RuntimeError("Tüm Cerebras modelleri başarısız.")


_PROVIDERS = [
    ("CEREBRAS_API_KEY",   "Cerebras (ücretsiz, hızlı)",  _summarize_cerebras),
    ("OPENROUTER_API_KEY", "OpenRouter (ücretsiz)",        _summarize_openrouter),
    ("GROQ_API_KEY",       "Llama 3.3 (Groq — ücretsiz)", _summarize_groq),
    ("ANTHROPIC_API_KEY",  "Claude (Anthropic)",           _summarize_anthropic),
    ("GEMINI_API_KEY",     "Gemini Flash (Google)",        _summarize_gemini),
]


def summarize_articles(articles: list[NewsArticle], max_articles: int = 10) -> list[NewsArticle]:
    top = articles[:max_articles]

    # ArXiv abstract'ları çok uzun — kırp
    for a in top:
        if "ArXiv" in a.source:
            # Abstract'ı 300 karakterde kes, "Announce Type" gürültüsünü temizle
            clean = re.sub(r"arXiv:\S+\s*Announce Type:\s*\S+\s*Abstract:\s*", "", a.summary)
            a.summary = clean[:300].strip()

    prompt = _build_prompt(_articles_to_text(top), len(top))
    log.debug("Prompt uzunluğu: %d karakter", len(prompt))

    # Hangi key'lerin yüklü olduğunu göster
    loaded = [name for env_var, name, _ in _PROVIDERS if os.getenv(env_var)]
    if not loaded:
        log.error("❌ Hiç LLM API key bulunamadı!")
        log.error("   .env yolu: %s", Path(__file__).parent / ".env")
        log.error("   GEMINI_API_KEY=%s", os.getenv("GEMINI_API_KEY", "—")[:12] + "...")
        return top
    log.info("Aktif provider(lar): %s", ", ".join(loaded))

    for env_var, provider_name, fn in _PROVIDERS:
        if not os.getenv(env_var):
            continue
        log.info("%s ile %d haber özetleniyor...", provider_name, len(top))
        try:
            response_text = fn(prompt)
            log.debug("Ham yanıt (ilk 300 karakter):\n%s", response_text[:300])
            _parse_claude_response(response_text, top)
            translated = sum(1 for a in top if a.turkish_title)
            if translated == 0:
                log.warning("Parse başarısız — yanıt beklenen formatta değil.")
                log.warning("Ham yanıt:\n%s", response_text[:600])
                # Yedek: daha esnek parse dene
                _parse_flexible(response_text, top)
                translated = sum(1 for a in top if a.turkish_title)
            log.info("%s tamamlandı — %d/%d haber çevrildi.", provider_name, translated, len(top))
            return top
        except Exception as exc:
            log.error("❌ %s hatası: %s", provider_name, exc)

    log.error("❌ Hiçbir provider çalışmadı.")
    return top


def _parse_flexible(text: str, articles: list[NewsArticle]) -> None:
    """Gemini farklı format döndürdüğünde devreye giren yedek parser."""
    # Satır satır tara, BAŞLIK: ve ÖZET: içeren satırları bul
    title_pat  = re.compile(r"(?:TÜRKÇE_?BAŞLIK|Turkish Title|Başlık)\s*[:：]\s*(.+)", re.IGNORECASE)
    summary_pat = re.compile(r"(?:TÜRKÇE_?ÖZET|Turkish Summary|Özet)\s*[:：]\s*([\s\S]+?)(?=(?:TÜRKÇE|Turkish|Başlık|Özet|===|\d+\.|$))", re.IGNORECASE)
    number_pat  = re.compile(r"(?:===HABER_?(\d+)===|^\*?\*?(\d+)\.\s)", re.MULTILINE)

    # Numaralı bloklara böl
    splits = list(number_pat.finditer(text))
    if not splits:
        # Numara yoksa tüm metni tek blok say
        blocks = [text]
        offsets = [0]
    else:
        offsets = [m.start() for m in splits]
        offsets.append(len(text))
        blocks = [text[offsets[i]:offsets[i+1]] for i in range(len(splits))]

    for i, block in enumerate(blocks):
        if i >= len(articles):
            break
        if articles[i].turkish_title:
            continue  # Zaten çevrilmiş
        tm = title_pat.search(block)
        sm = summary_pat.search(block)
        if tm:
            articles[i].turkish_title = tm.group(1).strip()
        if sm:
            articles[i].turkish_summary = sm.group(1).strip()


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

    articles = summarize_articles(articles, max_articles=10)
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
    if "--verbose" in sys.argv:
        logging.getLogger().setLevel(logging.DEBUG)
    if "--demo" in sys.argv:
        run_demo()
    else:
        run()
