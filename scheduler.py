#!/usr/bin/env python3
"""
Günlük 08:00 Türkiye saatiyle (UTC+3) ai_news_aggregator çalıştıran zamanlayıcı.
Kullanım: python scheduler.py
"""

import logging
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import schedule

from ai_news_aggregator import run

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

TURKEY_TZ = ZoneInfo("Europe/Istanbul")
RUN_TIME = "08:00"  # Türkiye saati


def job():
    now = datetime.now(TURKEY_TZ).strftime("%Y-%m-%d %H:%M %Z")
    log.info("Günlük AI haber özeti başlatılıyor — %s", now)
    try:
        run()
    except Exception as exc:
        log.error("Haber özeti oluşturulurken hata: %s", exc, exc_info=True)


if __name__ == "__main__":
    log.info("Zamanlayıcı başlatıldı. Her gün %s Türkiye saatiyle çalışacak.", RUN_TIME)

    # schedule kütüphanesi yerel saati kullanır; sunucu TZ=Europe/Istanbul olmalı
    schedule.every().day.at(RUN_TIME).do(job)

    # İlk çalıştırma: --now argümanıyla hemen tetikle
    if "--now" in sys.argv:
        log.info("--now argümanı algılandı, hemen çalıştırılıyor...")
        job()

    while True:
        schedule.run_pending()
        time.sleep(30)
