#!/usr/bin/env python3
"""
AI Haber Toplayıcı — İnteraktif Menü
Kullanım: python3 app.py  veya  ./ai_news
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ENV_FILE = Path(__file__).parent / ".env"
TURKEY_TZ = ZoneInfo("Europe/Istanbul")

# ── Renkler ───────────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    DIM    = "\033[2m"

def c(color, text): return f"{color}{text}{C.RESET}"
def bold(t): return c(C.BOLD, t)
def ok(t):   return c(C.GREEN,  f"✅ {t}")
def warn(t): return c(C.YELLOW, f"⚠️  {t}")
def err(t):  return c(C.RED,    f"❌ {t}")
def info(t): return c(C.CYAN,   f"ℹ️  {t}")

# ── .env yardımcıları ─────────────────────────────────────────────────────────
def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

def save_env(env: dict):
    lines = []
    keys_written = set()

    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=")[0].strip()
                if k in env:
                    lines.append(f"{k}={env[k]}")
                    keys_written.add(k)
                else:
                    lines.append(line)
            else:
                lines.append(line)

    for k, v in env.items():
        if k not in keys_written:
            lines.append(f"{k}={v}")

    ENV_FILE.write_text("\n".join(lines) + "\n")

# ── Ekran ─────────────────────────────────────────────────────────────────────
def clear():
    os.system("clear" if os.name != "nt" else "cls")

def header():
    now = datetime.now(TURKEY_TZ).strftime("%d/%m/%Y %H:%M")
    print(c(C.CYAN, "╔" + "═" * 56 + "╗"))
    print(c(C.CYAN, "║") + bold(c(C.WHITE, "   🤖  Günlük AI Haber Toplayıcı & Editörü          ")) + c(C.CYAN, "║"))
    print(c(C.CYAN, "║") + c(C.DIM,  f"   📅 {now} (Türkiye)                          ") + c(C.CYAN, "║"))
    print(c(C.CYAN, "╚" + "═" * 56 + "╝"))
    print()

def api_status(env: dict) -> str:
    providers = [
        ("ANTHROPIC_API_KEY", "Claude"),
        ("GROQ_API_KEY",      "Groq"),
        ("GEMINI_API_KEY",    "Gemini"),
    ]
    active = [name for key, name in providers if env.get(key)]
    if active:
        return ok(f"LLM: {', '.join(active)}")
    return warn("LLM API key girilmemiş")

def gnews_status(env: dict) -> str:
    return ok("GNews bağlı") if env.get("GNEWS_KEY") else warn("GNews key girilmemiş (RSS ile devam eder)")

# ── Ana menü ─────────────────────────────────────────────────────────────────
def main_menu():
    while True:
        clear()
        header()
        env = load_env()
        print(f"  {api_status(env)}")
        print(f"  {gnews_status(env)}")
        print()
        print(bold("  ANA MENÜ"))
        print(c(C.WHITE, "  ─────────────────────────────────────"))
        print("  [1] 📰  Haberleri şimdi çek ve özetle")
        print("  [2] 🔑  API key ayarları")
        print("  [3] ⏰  Günlük zamanlayıcı kur (08:00 TR)")
        print("  [4] 📂  Kaydedilen özetleri görüntüle")
        print("  [5] 🎬  Demo modu (key olmadan önizle)")
        print("  [0] 🚪  Çıkış")
        print()
        choice = input(c(C.CYAN, "  Seçim: ")).strip()

        if choice == "1":
            menu_run(env)
        elif choice == "2":
            menu_keys(env)
        elif choice == "3":
            menu_cron()
        elif choice == "4":
            menu_digests()
        elif choice == "5":
            menu_demo()
        elif choice == "0":
            print(c(C.DIM, "\n  Görüşürüz! 👋\n"))
            sys.exit(0)


# ── Haberleri çek ────────────────────────────────────────────────────────────
def menu_run(env: dict):
    clear()
    header()
    providers = ["ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"]
    if not any(env.get(k) for k in providers):
        print(err("Hiç LLM API key tanımlı değil!"))
        print(info("Önce [2] API key ayarları menüsünden key girin."))
        input(c(C.DIM, "\n  Enter'a basın..."))
        return

    print(info("Haberler çekiliyor, lütfen bekleyin...\n"))
    # env değişkenlerini subprocess'e aktar
    run_env = {**os.environ, **{k: v for k, v in env.items() if v}}
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "ai_news_aggregator.py")],
        env=run_env,
    )
    if result.returncode != 0:
        print(err("Bir hata oluştu. Lütfen API key'lerinizi kontrol edin."))
    input(c(C.DIM, "\n  Enter'a basın..."))


# ── API Key ayarları ──────────────────────────────────────────────────────────
def menu_keys(env: dict):
    while True:
        clear()
        header()
        print(bold("  🔑  API KEY AYARLARI"))
        print(c(C.WHITE, "  ─────────────────────────────────────"))

        def status(key):
            v = env.get(key, "")
            if v:
                masked = v[:8] + "..." + v[-4:]
                return c(C.GREEN, f"✅ {masked}")
            return c(C.DIM, "— girilmemiş")

        print(f"  [1] Claude  (Anthropic)  {status('ANTHROPIC_API_KEY')}")
        print(f"       → console.anthropic.com  {c(C.DIM,'(ücretli, en kaliteli)')}")
        print()
        print(f"  [2] Groq    (Llama 3.3)  {status('GROQ_API_KEY')}")
        print(f"       → console.groq.com       {c(C.DIM,'(ÜCRETSİZ)')}")
        print()
        print(f"  [3] Gemini  (Google)     {status('GEMINI_API_KEY')}")
        print(f"       → aistudio.google.com    {c(C.DIM,'(ÜCRETSİZ)')}")
        print()
        print(f"  [4] GNews   (Haber API)  {status('GNEWS_KEY')}")
        print(f"       → gnews.io               {c(C.DIM,'(ÜCRETSİZ, 100 istek/gün)')}")
        print()
        print("  [0] ← Geri")
        print()
        choice = input(c(C.CYAN, "  Seçim: ")).strip()

        key_map = {
            "1": "ANTHROPIC_API_KEY",
            "2": "GROQ_API_KEY",
            "3": "GEMINI_API_KEY",
            "4": "GNEWS_KEY",
        }
        if choice in key_map:
            env_key = key_map[choice]
            mevcut = env.get(env_key, "")
            if mevcut:
                print(c(C.DIM, f"\n  Mevcut: {mevcut[:8]}...{mevcut[-4:]}"))
                print(c(C.DIM,  "  Boş bırakırsanız silinir."))
            val = input(c(C.CYAN, f"  Yeni değer: ")).strip()
            if val:
                env[env_key] = val
                save_env({env_key: val})
                print(ok("Kaydedildi!"))
            elif mevcut:
                konfirm = input(c(C.YELLOW, "  Silmek istiyor musunuz? (e/H): ")).strip().lower()
                if konfirm == "e":
                    env[env_key] = ""
                    save_env({env_key: ""})
                    print(warn("Silindi."))
            import time; time.sleep(1)
        elif choice == "0":
            break


# ── Zamanlayıcı ───────────────────────────────────────────────────────────────
def menu_cron():
    clear()
    header()
    print(bold("  ⏰  GÜNLÜK ZAMANLAYICI"))
    print(c(C.WHITE, "  ─────────────────────────────────────"))
    print(info("Her gün 08:00 Türkiye saatinde otomatik çalışır."))
    print()

    script = Path(__file__).parent / "ai_news_aggregator.py"
    log    = Path(__file__).parent / "ai_news_cron.log"
    python = sys.executable
    cron_line = f"0 5 * * * TZ=Europe/Istanbul {python} {script} >> {log} 2>&1"

    # Mevcut cron'u kontrol et
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    already = "ai_news_aggregator.py" in result.stdout

    if already:
        print(ok("Zamanlayıcı zaten aktif!"))
        print(c(C.DIM, f"\n  {cron_line}\n"))
        print("  [1] Kaldır")
        print("  [0] ← Geri")
        choice = input(c(C.CYAN, "  Seçim: ")).strip()
        if choice == "1":
            new_crontab = "\n".join(
                l for l in result.stdout.splitlines()
                if "ai_news_aggregator.py" not in l
            )
            subprocess.run(["crontab", "-"], input=new_crontab, text=True)
            print(warn("Zamanlayıcı kaldırıldı."))
    else:
        print(f"  Eklenecek kayıt:")
        print(c(C.DIM, f"  {cron_line}\n"))
        print("  [1] Ekle ve aktif et")
        print("  [0] ← Geri")
        choice = input(c(C.CYAN, "  Seçim: ")).strip()
        if choice == "1":
            existing = result.stdout.rstrip("\n")
            new_crontab = f"{existing}\n{cron_line}\n" if existing else f"{cron_line}\n"
            subprocess.run(["crontab", "-"], input=new_crontab, text=True)
            print(ok("Zamanlayıcı aktif edildi! Her gün 08:00'de çalışacak."))

    input(c(C.DIM, "\n  Enter'a basın..."))


# ── Kaydedilen özetler ────────────────────────────────────────────────────────
def menu_digests():
    clear()
    header()
    print(bold("  📂  KAYDEDİLEN ÖZETLER"))
    print(c(C.WHITE, "  ─────────────────────────────────────"))

    env = load_env()
    output_dir = Path(env.get("OUTPUT_DIR", "."))
    if not output_dir.is_absolute():
        output_dir = Path(__file__).parent / output_dir

    files = sorted(output_dir.glob("ai_news_*.txt"), reverse=True)

    if not files:
        print(warn("Henüz kaydedilmiş özet yok."))
        input(c(C.DIM, "\n  Enter'a basın..."))
        return

    print()
    for i, f in enumerate(files[:10], 1):
        size = f.stat().st_size
        print(f"  [{i}] {f.name}  {c(C.DIM, f'({size/1024:.1f} KB)')}")

    print("  [0] ← Geri")
    print()
    choice = input(c(C.CYAN, "  Görüntülemek istediğiniz numara: ")).strip()
    if choice.isdigit() and 1 <= int(choice) <= len(files[:10]):
        clear()
        print(files[int(choice) - 1].read_text())
        input(c(C.DIM, "\n  Enter'a basın..."))


# ── Demo ─────────────────────────────────────────────────────────────────────
def menu_demo():
    clear()
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "ai_news_aggregator.py"), "--demo"],
    )
    input(c(C.DIM, "\n  Enter'a basın..."))


# ── Giriş noktası ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print(c(C.DIM, "\n\n  Görüşürüz! 👋\n"))
        sys.exit(0)
