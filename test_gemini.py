#!/usr/bin/env python3
"""Gemini bağlantı ve çeviri testi."""
import os, sys, json, urllib.request, urllib.error
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

key = os.getenv("GEMINI_API_KEY", "")
print(f"GEMINI_API_KEY: {'✅ yüklendi (' + key[:8] + '...)' if key else '❌ BULUNAMADI'}")

if not key:
    print("\n.env dosyasını kontrol et:")
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        print(env_file.read_text())
    else:
        print("❌ .env dosyası yok!")
    sys.exit(1)

print("\nGemini'ye test isteği gönderiliyor...")
payload = json.dumps({
    "contents": [{"parts": [{"text": "Merhaba, sadece 'Bağlantı başarılı!' yaz."}]}],
    "generationConfig": {"maxOutputTokens": 50},
}).encode()

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

try:
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    print(f"✅ Gemini yanıtı: {text.strip()}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"❌ HTTP {e.code} hatası:")
    print(body[:500])
except Exception as e:
    print(f"❌ Bağlantı hatası: {e}")
