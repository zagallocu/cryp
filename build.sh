#!/usr/bin/env bash
# PyInstaller ile tek çalıştırılabilir dosya oluşturur: ./ai_news
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
DIST_DIR="$SCRIPT_DIR/dist"

echo "=== AI Haber Toplayıcı — Derleme ==="
echo ""

# 1) venv kur
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/4] Sanal ortam oluşturuluyor..."
    python3 -m venv "$VENV_DIR"
fi
echo "[1/4] Sanal ortam hazır."

# 2) Bağımlılıkları kur
echo "[2/4] Bağımlılıklar kuruluyor..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
"$VENV_DIR/bin/pip" install -q pyinstaller

# 3) Derle
echo "[3/4] Derleniyor (bu 1-2 dakika sürebilir)..."
"$VENV_DIR/bin/pyinstaller" \
    --onefile \
    --name ai_news \
    --distpath "$DIST_DIR" \
    --workpath "$SCRIPT_DIR/build_tmp" \
    --specpath "$SCRIPT_DIR/build_tmp" \
    --hidden-import zoneinfo \
    --hidden-import zoneinfo.tzdata \
    --collect-data tzdata \
    --noconfirm \
    --clean \
    "$SCRIPT_DIR/app.py" 2>&1 | grep -E "^(INFO|WARNING|ERROR|Building)" || true

# 4) Temizle ve taşı
echo "[4/4] Temizleniyor..."
rm -rf "$SCRIPT_DIR/build_tmp"

if [ -f "$DIST_DIR/ai_news" ]; then
    cp "$DIST_DIR/ai_news" "$SCRIPT_DIR/ai_news"
    chmod +x "$SCRIPT_DIR/ai_news"
    SIZE=$(du -sh "$SCRIPT_DIR/ai_news" | cut -f1)
    echo ""
    echo "✅ Derleme tamamlandı!"
    echo "   Dosya: $SCRIPT_DIR/ai_news ($SIZE)"
    echo ""
    echo "Kullanım:"
    echo "  ./ai_news"
else
    echo "❌ Derleme başarısız. Yukarıdaki hata mesajlarını kontrol edin."
    exit 1
fi
