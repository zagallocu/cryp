#!/usr/bin/env bash
# Sunucuda cron ile 08:00 Türkiye saatinde (UTC+3 = UTC 05:00) çalıştırmak için
# Bu script venv oluşturur, bağımlılıkları kurar ve cron kaydını ekler.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
LOG_FILE="$SCRIPT_DIR/ai_news_cron.log"

echo "=== AI Haber Toplayıcı Kurulum ==="

# 1) venv yoksa oluştur
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/3] Sanal ortam oluşturuluyor: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
else
    echo "[1/3] Sanal ortam zaten mevcut: $VENV_DIR"
fi

# 2) Bağımlılıkları kur
echo "[2/3] Bağımlılıklar kuruluyor..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
echo "      Kurulum tamamlandı."

# 3) Cron kaydı ekle (venv içindeki python'u kullan)
PYTHON="$VENV_DIR/bin/python3"
CRON_LINE="0 5 * * * TZ=Europe/Istanbul $PYTHON $SCRIPT_DIR/ai_news_aggregator.py >> $LOG_FILE 2>&1"

if crontab -l 2>/dev/null | grep -qF "ai_news_aggregator.py"; then
    echo "[3/3] Cron kaydı zaten mevcut, güncelleniyor..."
    # Eskiyi sil, yeniyi ekle
    (crontab -l 2>/dev/null | grep -vF "ai_news_aggregator.py"; echo "$CRON_LINE") | crontab -
else
    echo "[3/3] Cron kaydı ekleniyor..."
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
fi

echo ""
echo "✅ Kurulum tamamlandı!"
echo "   Her gün 08:00 Türkiye saatiyle çalışacak."
echo "   Log dosyası: $LOG_FILE"
echo ""
echo "Mevcut cron listesi:"
crontab -l
echo ""
echo "Hemen test etmek için:"
echo "  source $VENV_DIR/bin/activate"
echo "  python3 $SCRIPT_DIR/ai_news_aggregator.py"
