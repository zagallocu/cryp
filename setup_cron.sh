#!/usr/bin/env bash
# Sunucuda cron ile 08:00 Türkiye saatinde (UTC+3 = UTC 05:00) çalıştırmak için
# Bu script cron kaydını otomatik ekler.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(which python3)"
LOG_FILE="$SCRIPT_DIR/ai_news_cron.log"

CRON_LINE="0 5 * * * TZ=Europe/Istanbul $PYTHON $SCRIPT_DIR/ai_news_aggregator.py >> $LOG_FILE 2>&1"

# Aynı satır zaten varsa tekrar ekleme
(crontab -l 2>/dev/null | grep -qF "ai_news_aggregator.py") && {
    echo "Cron kaydı zaten mevcut."
    exit 0
}

(crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
echo "Cron kaydı eklendi:"
echo "  $CRON_LINE"
echo ""
echo "Mevcut cron listesi:"
crontab -l
