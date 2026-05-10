#!/usr/bin/env python3
"""
ТендерБот v10 — реальные тендеры с ЕИС
Загружаем страницами по 100, фильтруем локально по ключевым словам
"""

import requests
import time
import schedule
import threading
from datetime import datetime

# ===== НАСТРОЙКИ =====
TELEGRAM_TOKEN = "8692328974:AAFxNbmWYNmESos5VCLvwayBDJ2Qut4iYTk"
CHAT_ID = "559431614"
GOSPLAN = "https://v2test.gosplan.info"

MIN_PRICE = 20_000
MAX_PRICE = 200_000
PAGES_TO_CHECK = 3   # загружаем 3 страницы по 100 = 300 записей

# Ключевые слова по названию тендера
KEYWORDS = [
    # Оргтехника
    "мфу", "принтер", "копир", "плоттер", "сканер",
    # Компьютеры
    "ноутбук", "моноблок", "системный блок",
    "компьютерная техник", "вычислительная техник", "офисная техник",
    # Мониторы
    "монитор", "проектор", "интерактивная доска",
    # Расходники
    "картридж", "тонер", "фотобарабан",
    # Периферия
    "клавиатур", "мышь", "веб-камер", "наушник", "гарнитур",
    # Носители
    "флешк", "внешний диск", "жёсткий диск", "жесткий диск",
    # Сеть
    "роутер", "маршрутизатор", "коммутатор", "точка доступа",
    # Аксессуары
    "сетевой фильтр", "удлинитель питан",
    # ИБП
    "источник бесперебойн", "ибп",
    # Общее
    "оргтехник", "периферийн",
]

HEADERS = {"User-Agent": "TenderBot/10.0", "Accept": "application/json"}


# ===== ФИЛЬТРЫ =====
def is_match(item: dict) -> bool:
    """Проверяем название и цену"""
    title = str(item.get("purchase_name") or "").lower()
    price = float(item.get("max_price") or 0)

    if not any(kw in title for kw in KEYWORDS):
        return False
    if price < MIN_PRICE or price > MAX_PRICE:
        return False
    return True


# ===== ПОИСК =====
def load_page(skip: int) -> list:
    """Загружаем одну страницу закупок"""
    try:
        r = requests.get(
            f"{GOSPLAN}/fz44/purchases",
            params={"limit": 100, "skip": skip},
            headers=HEADERS, timeout=10
        )
        print(f"  skip={skip}: HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return data
            for v in data.values():
                if isinstance(v, list):
                    return v
        else:
            print(f"  skip={skip}: ответ {r.text[:100]}")
    except requests.exceptions.Timeout:
        print(f"  skip={skip}: ТАЙМАУТ — сервер не отвечает")
    except Exception as e:
        print(f"  skip={skip}: Ошибка {e}")
    return []


def parse_item(item: dict) -> dict:
    price = float(item.get("max_price") or 0)
    num = str(item.get("purchase_number") or item.get("id", ""))
    title = str(item.get("purchase_name") or "Закупка")[:120]

    customers = item.get("customers") or []
    if customers and isinstance(customers[0], dict):
        customer = customers[0].get("name") or "Заказчик"
    else:
        customer = "Заказчик"

    deadline = str(item.get("collecting_finished_at") or
                   item.get("published_at") or "")[:10]
    region = str(item.get("region") or "")

    url = (f"https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html"
           f"?regNumber={num}") if num else "https://zakupki.gov.ru"

    return {
        "id": num, "title": title, "price": price,
        "customer": customer[:80], "deadline": deadline,
        "region": region, "law": "44-ФЗ", "url": url,
    }


def search_all() -> list:
    """Перебираем страницы и собираем подходящие тендеры"""
    results = []
    seen = set()

    for page in range(PAGES_TO_CHECK):
        skip = page * 100
        print(f"  Загружаю страницу {page+1}...")
        send_telegram(f"⏳ Страница {page+1}/{PAGES_TO_CHECK}...")
        items = load_page(skip)

        if not items:
            print(f"  Страница {page+1}: пусто, останавливаемся")
            send_telegram(f"⚠️ Страница {page+1}: нет данных")
            break

        matched = 0
        for item in items:
            if not is_match(item):
                continue
            num = str(item.get("purchase_number") or item.get("id", ""))
            if num and num in seen:
                continue
            seen.add(num)
            matched += 1
            results.append(parse_item(item))

        print(f"  Страница {page+1}: {len(items)} записей, подходит {matched}")
        send_telegram(f"✅ Страница {page+1}: {len(items)} записей, подходит {matched}")

        if len(results) >= 10:
            break

        if page < PAGES_TO_CHECK - 1:
            time.sleep(7)

    return results


# ===== TELEGRAM =====
def send_telegram(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": CHAT_ID, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram: {e}")
        return False


def send_tender_card(tender: dict, index: int) -> None:
    price = tender.get("price", 0)
    price_fmt = f"{price:,.0f}".replace(",", " ")
    send_telegram(
        f"📋 <b>Тендер #{index}</b>\n\n"
        f"<b>{tender.get('title', '—')}</b>\n\n"
        f"💰 <b>{price_fmt} ₽</b>\n"
        f"🏛 {tender.get('customer', '—')}\n"
        f"📍 Регион: {tender.get('region', '—')}\n"
        f"⏰ Дедлайн: {tender.get('deadline', '—')}\n"
        f"🔢 № {tender.get('id', '—')}\n\n"
        f"🔗 <a href=\"{tender.get('url', 'https://zakupki.gov.ru')}\">Открыть на ЕИС →</a>"
    )
    time.sleep(0.5)


# ===== ОСНОВНАЯ ЗАДАЧА =====
def run_daily_search():
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"\n[{now}] Старт поиска...")

    send_telegram(
        f"🔍 <b>ТендерСкан — реальные данные ЕИС</b>\n"
        f"📅 {now}\n\n"
        f"• Оргтехника, периферия, расходники\n"
        f"• Цена: {MIN_PRICE:,}–{MAX_PRICE:,} ₽\n"
        f"• Проверяю до {PAGES_TO_CHECK*100} закупок\n\n"
        f"⏳ Загружаю данные с ЕИС..."
    )

    tenders = search_all()
    tenders.sort(key=lambda x: x.get("price", 0), reverse=True)
    top = tenders[:6]

    total_checked = min(PAGES_TO_CHECK * 100, 500)

    if not top:
        send_telegram(
            f"😔 <b>Ничего не найдено</b>\n\n"
            f"Из последних ~{total_checked} закупок ЕИС\n"
            f"нет оргтехники в диапазоне {MIN_PRICE:,}–{MAX_PRICE:,} ₽.\n\n"
            f"Данные обновляются — попробуй /search позже.\n"
            f"🔗 <a href=\"https://zakupki.gov.ru\">ЕИС →</a>"
        )
        return

    send_telegram(
        f"✅ <b>Найдено {len(top)} тендеров!</b>\n"
        f"Из ~{total_checked} проверенных закупок 👇"
    )
    time.sleep(1)

    for i, t in enumerate(top, 1):
        send_tender_card(t, i)

    send_telegram(
        f"📊 <b>Итог:</b> {len(top)} тендеров\n"
        f"💰 {MIN_PRICE:,}–{MAX_PRICE:,} ₽\n"
        f"⏰ Следующий поиск в 09:00\n"
        f"/search — поиск прямо сейчас"
    )
    print(f"[{now}] Готово. {len(top)} тендеров.")


# ===== КОМАНДЫ =====
def handle_commands():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    last_update_id = None
    while True:
        try:
            params = {"timeout": 30}
            if last_update_id:
                params["offset"] = last_update_id
            r = requests.get(url, params=params, timeout=35)
            for update in r.json().get("result", []):
                last_update_id = update["update_id"] + 1
                text = update.get("message", {}).get("text", "")
                if text == "/start":
                    send_telegram(
                        "👋 <b>ТендерСкан v10</b>\n\n"
                        "📡 Реальные данные с zakupki.gov.ru\n"
                        "🔍 МФУ, принтер, ноутбук, картридж,\n"
                        "    монитор, роутер, ИБП и др.\n"
                        f"💰 {MIN_PRICE:,}–{MAX_PRICE:,} ₽\n\n"
                        "/search — найти тендеры\n"
                        "/status — статус"
                    )
                elif text == "/search":
                    send_telegram("🔄 Загружаю закупки с ЕИС...")
                    threading.Thread(target=run_daily_search, daemon=True).start()
                elif text == "/status":
                    send_telegram(
                        "✅ <b>Бот активен</b>\n"
                        "📡 ГосПлан API → zakupki.gov.ru\n"
                        f"💰 {MIN_PRICE:,}–{MAX_PRICE:,} ₽\n"
                        f"📄 Проверяю до {PAGES_TO_CHECK*100} закупок\n"
                        "🕘 Авто-поиск в 09:00"
                    )
        except Exception as e:
            print(f"Polling: {e}")
            time.sleep(5)


# ===== ЗАПУСК =====
if __name__ == "__main__":
    print("=" * 55)
    print("  ТендерСкан v10 — постраничная загрузка + локальный фильтр")
    print("=" * 55)

    ok = send_telegram(
        "🚀 <b>ТендерСкан v10!</b>\n\n"
        "📡 Загружаю закупки страницами по 100\n"
        "🔍 Фильтр по названию и цене — локально\n"
        f"💰 {MIN_PRICE:,}–{MAX_PRICE:,} ₽\n\n"
        "/search — поиск прямо сейчас"
    )
    print("✅ Telegram!" if ok else "❌ Ошибка")

    schedule.every().day.at("09:00").do(run_daily_search)
    threading.Thread(target=handle_commands, daemon=True).start()

    while True:
        schedule.run_pending()
        time.sleep(60)
