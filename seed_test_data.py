#!/usr/bin/env python3
"""seed_test_data.py — заполнение БД FinTrack тестовыми данными.

Что создаёт (покрывает ВСЕ фичи приложения для smoke-теста):
- Тестового юзера (по умолчанию seed@example.com / seedpass123).
- 4 счёта разных типов и валют (Сбер карта, Тинькофф накопит., Наличные, USD карта).
- Дерево категорий: 4 expense-категории с подкатегориями + 3 income.
- ~300 транзакций за последние 6 месяцев: регулярная зарплата 10-го числа,
  аренда 5-го, ЖКХ 15-го, подписки + случайные продукты/кафе/такси/бензин
  с реалистичной плотностью + 8 одновалютных переводов + 3 КРОСС-ВАЛЮТНЫХ
  перевода (RUB↔USD, с разной суммой списания/зачисления). ~50 в текущем месяце
  (двигают балансы) + ~250 старше opening_date (бейдж «не в балансе»).
  Использует random.seed(42) — данные одинаковые при каждом запуске.
- 5 бюджетов на текущий месяц (разные статусы: ok / warning / превышение).
- 5 правил повторяющихся операций (зарплата, аренда, подписка, автонакопление —
  все на будущее; одно «назревшее» правило для проверки авто-генерации).

  ~310 POST-запросов через API ≈ 10-15 секунд работы скрипта.

Зачем: ручной ввод 4 счетов + 15 категорий + 25 транзакций — это полчаса
кликов. Скрипт делает то же за 3 секунды и даёт воспроизводимый набор
данных для smoke-теста любой фичи.

Как запустить (PowerShell, из активированного venv бэка):
    cd D:\\UNI\\Diploma\\financemanagement\\backend
    .\\.venv\\Scripts\\Activate.ps1
    py ..\\seed_test_data.py                 # обычный запуск
    py ..\\seed_test_data.py --reset         # сначала снести старого юзера
    py ..\\seed_test_data.py --help          # все опции

Зависимости: httpx (уже установлен как зависимость FastAPI).
Бэкенд должен быть запущен на --base-url (по умолчанию 127.0.0.1:60000).

После сидинга открой http://127.0.0.1:60001, залогинься как
seed@example.com / seedpass123.
"""
import argparse
import random
import sys
from datetime import datetime, timedelta, timezone

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:60000"
# .test / .invalid / .localhost / .example зарезервированы RFC 2606 как
# «not for real use», и email-validator (через Pydantic EmailStr) их
# блокирует. Используем example.com — он тоже формально reserved,
# но email-validator его пропускает, и это стандартный домен для тест-юзеров.
DEFAULT_EMAIL = "seed@example.com"
DEFAULT_PASSWORD = "seedpass123"

# opening_date = NOW - 30 дней. Транзакции последних 30 дней меняют balance,
# более старые — попадают в историю с бейджем «не в балансе». Это даёт
# нам сразу два сценария в одном наборе данных.
OPENING_DATE_DAYS_AGO = 30


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Заполнить БД FinTrack тестовыми данными.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"Адрес бэка (по умолчанию {DEFAULT_BASE_URL})")
    parser.add_argument("--email", default=DEFAULT_EMAIL,
                        help=f"Email тестового юзера (по умолчанию {DEFAULT_EMAIL})")
    parser.add_argument("--password", default=DEFAULT_PASSWORD,
                        help="Пароль")
    parser.add_argument("--reset", action="store_true",
                        help="Сначала удалить юзера и пересоздать (чистый старт)")
    args = parser.parse_args()

    print(f"🌱 Seed FinTrack")
    print(f"   API:   {args.base_url}")
    print(f"   user:  {args.email}")
    print()

    # timeout 10 сек — Argon2id-хэширование пароля при регистрации может
    # быть медленным на первом запросе (~300 мс), запас даёт стабильность.
    with httpx.Client(base_url=args.base_url, timeout=10.0) as client:
        # 0. Опционально — снести старого юзера.
        if args.reset:
            reset_user(client, args.email, args.password)

        # 1. Регистрация / логин — после этого client.headers["Authorization"] стоит.
        if not register_or_login(client, args.email, args.password):
            print("❌ Не удалось залогиниться. Проверь --email/--password.")
            return 1

        # opening_date один для всех счетов — упрощение.
        opening_date = datetime.now(timezone.utc) - timedelta(
            days=OPENING_DATE_DAYS_AGO
        )
        print(f"   opening_date счетов = {opening_date.strftime('%d.%m.%Y %H:%M')} "
              f"(30 дней назад)")
        print()

        # 2. Счета.
        print("📦 Счета")
        accounts = create_accounts(client, opening_date)
        print()

        # 3. Категории.
        print("📂 Категории")
        categories = create_categories(client)
        print()

        # 4. Транзакции.
        print("📝 Транзакции")
        count_recent, count_retro = create_transactions(client, accounts, categories)
        print()

        # 5. Бюджеты на текущий месяц.
        print("🎯 Бюджеты (текущий месяц)")
        budgets_count = create_budgets(client, categories)
        print()

        # 6. Повторяющиеся (регулярные) операции.
        print("🔄 Повторяющиеся операции")
        recurring_count = create_recurring(client, accounts, categories)
        print()

        print(f"✅ Готово!")
        print(f"   {count_recent} операций после opening_date (двигают balance)")
        print(f"   {count_retro} операций до opening_date (бейдж «не в балансе»)")
        print(f"   {budgets_count} бюджетов на текущий месяц")
        print(f"   {recurring_count} правил повторяющихся операций")
        print()
        print(f"   Открой фронт и залогинься: {args.email} / {args.password}")

    return 0


# ─── Юзер ─────────────────────────────────────────────────────────────────

def reset_user(client: httpx.Client, email: str, password: str) -> None:
    """Снести старого тестового юзера, если он есть. Все его счета/категории/
    транзакции улетят каскадно (ON DELETE CASCADE)."""
    r = client.post("/api/v1/auth/login",
                    json={"email": email, "password": password})
    if r.status_code != 200:
        print(f"   · юзера {email} нет — нечего сбрасывать")
        return
    token = r.json()["access_token"]
    r2 = client.delete("/api/v1/users/me",
                       headers={"Authorization": f"Bearer {token}"})
    if r2.status_code == 204:
        print(f"   ✗ старый юзер {email} удалён")
    else:
        print(f"   ⚠ не удалось снести юзера: HTTP {r2.status_code}")


def register_or_login(client: httpx.Client, email: str, password: str) -> bool:
    """Зарегистрировать или залогинить. Возвращает True при успехе.
    Сохраняет Authorization-заголовок в client для всех дальнейших запросов."""
    r = client.post("/api/v1/auth/register",
                    json={"email": email, "password": password})
    if r.status_code == 201:
        print(f"   + зарегистрирован {email}")
    elif r.status_code == 409:
        print(f"   · {email} уже есть, логинимся")
    else:
        print(f"   ❌ register вернул HTTP {r.status_code}: {r.text}")
        return False

    r = client.post("/api/v1/auth/login",
                    json={"email": email, "password": password})
    if r.status_code != 200:
        print(f"   ❌ login вернул HTTP {r.status_code}: {r.text}")
        return False
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return True


# ─── Счета ────────────────────────────────────────────────────────────────

def create_accounts(client: httpx.Client, opening_date: datetime) -> dict[str, dict]:
    """Создать 4 счёта. Возвращает dict {name: account_dict}.

    Если счёт с таким name уже есть (409 от UniqueConstraint), подтягиваем
    существующий — скрипт идемпотентен по счетам.
    """
    iso = opening_date.isoformat()
    data_list = [
        {"name": "Сбер карта",        "kind": "card",    "opening_balance": 150000, "currency_code": "RUB", "note": "Зарплатная"},
        {"name": "Тинькофф накопит.", "kind": "savings", "opening_balance": 500000, "currency_code": "RUB", "note": "Подушка безопасности"},
        {"name": "Наличные",          "kind": "cash",    "opening_balance": 30000,  "currency_code": "RUB"},
        {"name": "USD карта",         "kind": "card",    "opening_balance": 1200,   "currency_code": "USD", "note": "Travel"},
    ]
    created: dict[str, dict] = {}
    for data in data_list:
        payload = {**data, "opening_date": iso}
        r = client.post("/api/v1/accounts", json=payload)
        if r.status_code == 201:
            acc = r.json()
            created[data["name"]] = acc
            print(f"   + {data['name']:22s} {data['kind']:8s} "
                  f"{data['opening_balance']:>9} {data['currency_code']}")
        elif r.status_code == 409:
            # Подтянуть существующий из списка.
            existing = client.get("/api/v1/accounts").json()
            for acc in existing:
                if acc["name"] == data["name"]:
                    created[data["name"]] = acc
                    print(f"   · {data['name']:22s} уже есть")
                    break
        else:
            print(f"   ❌ {data['name']}: HTTP {r.status_code}: {r.text}")
            sys.exit(1)
    return created


# ─── Категории ────────────────────────────────────────────────────────────

def create_categories(client: httpx.Client) -> dict[str, dict]:
    """Создать дерево expense + плоский список income.
    Возвращает {name: category_dict}."""
    expense_tree = {
        "Еда":           ["Продукты", "Кафе", "Доставка"],
        "Транспорт":     ["Такси", "Бензин"],
        "Жильё":         ["Аренда", "ЖКХ"],
        "Развлечения":   ["Кино", "Подписки"],
    }
    income_flat = ["Зарплата", "Фриланс", "Подарки"]

    created: dict[str, dict] = {}

    # Expense — двухуровневое.
    for parent_name, children in expense_tree.items():
        parent = _create_category(client, parent_name, "expense", None, created)
        for child_name in children:
            _create_category(client, child_name, "expense", parent["id"], created)

    # Income — без иерархии.
    for name in income_flat:
        _create_category(client, name, "income", None, created)

    return created


def _create_category(client: httpx.Client, name: str, kind: str,
                     parent_id: int | None, created: dict[str, dict]) -> dict:
    """Один POST /categories, с обработкой 409 (уже существует)."""
    body: dict = {"name": name, "kind": kind}
    if parent_id is not None:
        body["parent_id"] = parent_id
    r = client.post("/api/v1/categories", json=body)
    indent = "       " if parent_id is not None else "   "
    if r.status_code == 201:
        cat = r.json()
        created[name] = cat
        print(f"{indent}+ {name} ({kind})")
        return cat
    if r.status_code == 409:
        existing = client.get("/api/v1/categories").json()
        for c in existing:
            if c["name"] == name and c["kind"] == kind:
                created[name] = c
                print(f"{indent}· {name} уже есть")
                return c
    print(f"   ❌ category {name}: HTTP {r.status_code}: {r.text}")
    sys.exit(1)


# ─── Транзакции ───────────────────────────────────────────────────────────

# Период истории. 180 дней = ~6 месяцев. Покрывает opening_date (30 дней назад)
# и даёт значительный объём «ретро» (до opening_date) — хорошо тестирует
# логику бейджа «не в балансе» и фильтров по периоду.
HISTORY_DAYS = 180

# random.seed(42) — Hitchhiker's Guide reference + повторяемость данных.
# При каждом запуске скрипта получаешь одинаковый набор транзакций.
RANDOM_SEED = 42

# Названия магазинов/мест для разнообразия заметок.
GROCERY_STORES = ["Перекрёсток", "Магнит", "Пятёрочка", "Лента", "Вкусвилл", "Метро", None]
CAFE_NOTES = ["Кофейня", "Бизнес-ланч", "Кофе на бегу", "Завтрак", "Ужин с друзьями", "Обед", None]
TAXI_NOTES = [None, "Домой", "На работу", "В аэропорт", None, None]
GAS_STATIONS = ["Лукойл", "Газпром", "Роснефть", "Shell"]
DELIVERY_NOTES = ["Яндекс.Еда", "Самокат", "Озон Свежее", "Delivery Club", "Купер"]
CINEMA_NOTES = ["Сеанс", "Премьера", "Фильм с друзьями"]
FREELANCE_NOTES = ["Сайт для клиента", "Дизайн логотипа", "Консультация", "Доработка фичи", "Аудит кода"]
GIFT_NOTES = ["ДР", "На праздник", "От родителей", "Юбилей"]
RUS_MONTH_GEN = [None, "январь", "февраль", "март", "апрель", "май", "июнь",
                 "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def generate_transactions(now: datetime) -> list[dict]:
    """Сгенерировать ~120-150 транзакций за последние HISTORY_DAYS дней.

    Состав:
    - Регулярные ежемесячные: зарплата (10-е), аренда (5-е), ЖКХ (15-е),
      Spotify + YouTube + Apple One (1-е и 3-е). Итого ~36 за 6 месяцев.
    - Случайные ежедневные: продукты (3/неделю), кафе (2/неделю),
      такси (3/неделю), бензин (1/неделю), доставка (1/неделю), кино
      (раз в 2 недели). Вероятностно. Итого ~100 за 6 месяцев.
    - Разовые: фриланс (5 за период), подарки (3), переводы (8).

    Использует random.seed для воспроизводимости.
    """
    random.seed(RANDOM_SEED)
    txs: list[dict] = []

    # Идём от старой даты к новой — так транзакции в итоге будут в порядке
    # возрастания времени (бэк сортирует по occurred_at, но человеку легче
    # читать вывод в хронологии).
    for d in range(HISTORY_DAYS, -1, -1):
        date = now - timedelta(days=d)
        is_today = (d == 0)

        # === Регулярные ежемесячные операции ===
        if date.day == 10 and not is_today:
            # Зарплата 10-го, ±3000 для жизненности
            txs.append({
                "kind": "income", "from": "Сбер карта", "cat": "Зарплата",
                "amount": random.randint(82000, 88000),
                "occurred": date.replace(hour=11, minute=random.randint(0, 30)),
                "note": f"Зарплата за {RUS_MONTH_GEN[date.month]}",
            })
        if date.day == 5 and not is_today:
            txs.append({
                "kind": "expense", "from": "Сбер карта", "cat": "Аренда",
                "amount": 35000,
                "occurred": date.replace(hour=14, minute=0),
                "note": f"Аренда {RUS_MONTH_GEN[date.month]}",
            })
        if date.day == 15 and not is_today:
            txs.append({
                "kind": "expense", "from": "Сбер карта", "cat": "ЖКХ",
                "amount": random.randint(4500, 5400),
                "occurred": date.replace(hour=18, minute=random.randint(0, 59)),
                "note": "Коммуналка",
            })
        if date.day == 1 and not is_today:
            txs.append({
                "kind": "expense", "from": "Сбер карта", "cat": "Подписки",
                "amount": 299,
                "occurred": date.replace(hour=9, minute=0),
                "note": "Spotify",
            })
            txs.append({
                "kind": "expense", "from": "Сбер карта", "cat": "Подписки",
                "amount": 599,
                "occurred": date.replace(hour=9, minute=1),
                "note": "YouTube Premium",
            })
        if date.day == 3 and not is_today:
            txs.append({
                "kind": "expense", "from": "USD карта", "cat": "Подписки",
                "amount": 12,
                "occurred": date.replace(hour=10, minute=0),
                "note": "Apple One",
            })

        # === Случайные дневные паттерны ===
        # Продукты: вероятность ~0.43 в день → ~3 раза/нед → ~75 за 6 мес
        if random.random() < 0.43:
            txs.append({
                "kind": "expense",
                "from": random.choice(["Сбер карта", "Сбер карта", "Наличные"]),
                "cat": "Продукты",
                "amount": random.randint(500, 4500),
                "occurred": _random_time(date, 9, 22),
                "note": random.choice(GROCERY_STORES),
            })

        # Кафе: ~0.28 в день → ~2/нед
        if random.random() < 0.28:
            txs.append({
                "kind": "expense", "from": "Сбер карта", "cat": "Кафе",
                "amount": random.randint(350, 2500),
                "occurred": _random_time(date, 8, 22),
                "note": random.choice(CAFE_NOTES),
            })

        # Такси: ~0.4 в день → ~2.8/нед
        if random.random() < 0.4:
            txs.append({
                "kind": "expense", "from": "Сбер карта", "cat": "Такси",
                "amount": random.randint(250, 800),
                "occurred": _random_time(date, 7, 23),
                "note": random.choice(TAXI_NOTES),
            })

        # Бензин: ~0.15 в день → ~1/нед
        if random.random() < 0.15:
            txs.append({
                "kind": "expense", "from": "Сбер карта", "cat": "Бензин",
                "amount": random.randint(2800, 4200),
                "occurred": _random_time(date, 8, 21),
                "note": random.choice(GAS_STATIONS),
            })

        # Доставка еды: ~0.14 → ~1/нед
        if random.random() < 0.14:
            txs.append({
                "kind": "expense", "from": "Сбер карта", "cat": "Доставка",
                "amount": random.randint(800, 3500),
                "occurred": _random_time(date, 12, 22),
                "note": random.choice(DELIVERY_NOTES),
            })

        # Кино: ~0.07 → ~0.5/нед = 2 раза/мес
        if random.random() < 0.07:
            txs.append({
                "kind": "expense",
                "from": random.choice(["Сбер карта", "Наличные"]),
                "cat": "Кино",
                "amount": random.randint(600, 1500),
                "occurred": _random_time(date, 17, 22),
                "note": random.choice(CINEMA_NOTES),
            })

        # Фриланс-доход: ~0.025 → ~4-5 за полгода
        if random.random() < 0.025:
            txs.append({
                "kind": "income", "from": "Сбер карта", "cat": "Фриланс",
                "amount": random.randint(12000, 45000),
                "occurred": _random_time(date, 14, 20),
                "note": random.choice(FREELANCE_NOTES),
            })

        # Подарки/возвраты: ~0.015 → ~2-3 за полгода
        if random.random() < 0.015:
            txs.append({
                "kind": "income",
                "from": random.choice(["Сбер карта", "Наличные"]),
                "cat": "Подарки",
                "amount": random.randint(2000, 20000),
                "occurred": _random_time(date, 12, 20),
                "note": random.choice(GIFT_NOTES),
            })

        # USD-карта: иногда расходы за рубежом ~0.04 → ~1/нед
        if random.random() < 0.04:
            usd_cats = ["Подписки", "Доставка"]
            txs.append({
                "kind": "expense", "from": "USD карта",
                "cat": random.choice(usd_cats),
                "amount": random.randint(5, 80),
                "occurred": _random_time(date, 10, 22),
                "note": random.choice(["Amazon", "Steam", "GitHub", "AWS", None]),
            })

    # === Разовые: переводы между счетами (одновалютные, RUB ↔ RUB) ===
    # 8 переводов на случайные дни в диапазоне 5..170 дней назад
    transfer_days = sorted(random.sample(range(5, 170), 8))
    for day_ago in transfer_days:
        date = now - timedelta(days=day_ago)
        # Большинство переводов с накопит. на карту (типичный сценарий),
        # пару раз в обратную (откладываем)
        if random.random() < 0.7:
            src, dst, note = "Тинькофф накопит.", "Сбер карта", "Снял с накопит."
        else:
            src, dst, note = "Сбер карта", "Тинькофф накопит.", "Отложил"
        txs.append({
            "kind": "transfer", "from": src, "cat": None,
            "amount": random.randint(5, 50) * 1000,  # 5000..50000, круглые
            "occurred": _random_time(date, 10, 20),
            "note": note,
            "transfer_to": dst,
        })

    # === Кросс-валютные переводы (RUB ↔ USD) ===
    # Демонстрируют фичу: со счёта-источника списывается amount в его валюте,
    # на счёт-получатель зачисляется target_amount в его валюте (сумму ввёл бы
    # пользователь по факту банковской операции — курс отличается от ЦБ).
    # Кладём в последние ~30 дней, чтобы двигали текущие балансы и были видны.
    # Поля: (дней назад, источник, получатель, списание, зачисление, заметка)
    cross_currency_specs = [
        (22, "Сбер карта", "USD карта", 9300, 100, "Купил $ на поездку"),
        (12, "Сбер карта", "USD карта", 19000, 200, "Пополнил долларовую"),
        (5,  "USD карта", "Сбер карта", 150, 13800, "Вернул часть в рубли"),
    ]
    for day_ago, src, dst, amount, target_amount, note in cross_currency_specs:
        date = now - timedelta(days=day_ago)
        txs.append({
            "kind": "transfer", "from": src, "cat": None,
            "amount": amount,
            "target_amount": target_amount,  # ← отличает кросс-валютный перевод
            "occurred": _random_time(date, 10, 19),
            "note": note,
            "transfer_to": dst,
        })

    return txs


def _random_time(date: datetime, hour_from: int, hour_to: int) -> datetime:
    """Заменить время в datetime на случайное в диапазоне часов.

    Берём UTC-момент, заменяем h/m/s — таймзону не трогаем (бэк хранит TIMESTAMPTZ).
    """
    return date.replace(
        hour=random.randint(hour_from, hour_to),
        minute=random.randint(0, 59),
        second=random.randint(0, 59),
        microsecond=0,
    )


def create_transactions(client: httpx.Client, accounts: dict[str, dict],
                        categories: dict[str, dict]) -> tuple[int, int]:
    """POST'нуть все сгенерированные транзакции. Возвращает (recent, retro)."""
    now = datetime.now(timezone.utc)
    txs = generate_transactions(now)
    recent = retro = 0
    print(f"   Сгенерировано {len(txs)} транзакций за {HISTORY_DAYS} дней. Отправляю...")

    for i, tx in enumerate(txs, start=1):
        body = {
            "kind": tx["kind"],
            "account_id": accounts[tx["from"]]["id"],
            "amount": tx["amount"],
            "occurred_at": tx["occurred"].isoformat(),
            "note": tx.get("note"),
        }
        if tx["cat"] is not None:
            body["category_id"] = categories[tx["cat"]]["id"]
        if tx["kind"] == "transfer":
            body["transfer_account_id"] = accounts[tx["transfer_to"]]["id"]
            # Кросс-валютный перевод: сумма зачисления в валюте получателя.
            if tx.get("target_amount") is not None:
                body["target_amount"] = tx["target_amount"]

        r = client.post("/api/v1/transactions", json=body)
        if r.status_code != 201:
            print(f"   ❌ {tx['kind']} {tx['amount']} ({tx.get('note', '')}): "
                  f"HTTP {r.status_code}: {r.text}")
            sys.exit(1)

        # Retro = до opening_date.
        days_ago = (now - tx["occurred"]).days
        if days_ago > OPENING_DATE_DAYS_AGO:
            retro += 1
        else:
            recent += 1

        # Прогресс каждые 25 транзакций, чтобы не спамить вывод.
        if i % 25 == 0:
            print(f"   ... {i}/{len(txs)}")

    return recent, retro


# ─── Бюджеты ────────────────────────────────────────────────────────────────

def create_budgets(client: httpx.Client, categories: dict[str, dict]) -> int:
    """Создать бюджеты на ТЕКУЩИЙ месяц для нескольких expense-категорий.

    Лимиты подобраны под плотность сид-расходов так, чтобы получить разные
    статусы прогресс-бара (ok / warning / exceeded) — наглядно для проверки.
    Бюджет на родительскую категорию (Жильё, Развлечения) суммирует расходы
    по всем её подкатегориям (BFS по дереву на бэке).

    Идемпотентность: если бюджет на категорию+месяц уже есть (409 от
    UniqueConstraint), просто пропускаем.
    """
    now = datetime.now(timezone.utc)
    # (имя категории, месячный лимит в RUB)
    specs = [
        ("Продукты", 28000),      # обычно близко к лимиту / превышение
        ("Кафе", 12000),
        ("Такси", 6000),
        ("Жильё", 45000),         # родитель: Аренда (35k) + ЖКХ (~5k)
        ("Развлечения", 3000),    # родитель: Кино + Подписки — часто превышение
    ]
    created = 0
    for cat_name, amount in specs:
        cat = categories.get(cat_name)
        if cat is None:
            print(f"   ⚠ категория «{cat_name}» не найдена — пропуск бюджета")
            continue
        body = {
            "category_id": cat["id"],
            "amount": amount,
            "period_year": now.year,
            "period_month": now.month,
        }
        r = client.post("/api/v1/budgets", json=body)
        if r.status_code == 201:
            created += 1
            print(f"   + {cat_name:14s} лимит {amount:>7} ₽/мес")
        elif r.status_code == 409:
            print(f"   · {cat_name:14s} бюджет на этот месяц уже есть")
        else:
            print(f"   ⚠ {cat_name}: HTTP {r.status_code}: {r.text}")
    return created


# ─── Повторяющиеся операции ──────────────────────────────────────────────────

def _next_month_day(now: datetime, day: int, hour: int = 12) -> datetime:
    """Ближайшая БУДУЩАЯ дата с заданным числом месяца.

    Если это число в текущем месяце уже прошло (или сегодня) — берём следующий
    месяц. Так созданные правила «ждут» первого срабатывания в будущем и не
    генерируют операции задним числом (catch-up) при заходе в приложение.
    """
    candidate = now.replace(
        day=min(day, 28), hour=hour, minute=0, second=0, microsecond=0
    )
    if candidate <= now:
        # перейти на следующий месяц
        year, month = now.year, now.month
        month += 1
        if month == 13:
            month, year = 1, year + 1
        candidate = candidate.replace(year=year, month=month)
    return candidate


def create_recurring(client: httpx.Client, accounts: dict[str, dict],
                     categories: dict[str, dict]) -> int:
    """Создать несколько правил повторяющихся операций.

    Все правила стартуют в БУДУЩЕМ (start_at), кроме одного «прошлого» —
    оно станет назревшим, и при заходе в приложение авто-/run (или кнопка
    «Выполнить запланированные») сгенерирует по нему одну операцию: так можно
    наглядно проверить и список правил, и сам движок catch-up.

    Идемпотентность грубая: при повторном запуске создадутся дубли правил с
    тем же именем (UniqueConstraint на правила не навешен) — для чистого набора
    запускай скрипт с --reset.
    """
    now = datetime.now(timezone.utc)

    def acc(name: str) -> int:
        return accounts[name]["id"]

    def cat(name: str) -> int:
        return categories[name]["id"]

    # (name, kind, from, cat|None, amount, freq, start_at, transfer_to|None, note)
    rules = [
        {
            "name": "Зарплата", "kind": "income", "account": "Сбер карта",
            "category_id": cat("Зарплата"), "amount": 85000, "frequency": "monthly",
            "start_at": _next_month_day(now, 10, 11),
            "note": "Ежемесячная зарплата",
        },
        {
            "name": "Аренда квартиры", "kind": "expense", "account": "Сбер карта",
            "category_id": cat("Аренда"), "amount": 35000, "frequency": "monthly",
            "start_at": _next_month_day(now, 5, 14),
            "note": "Аренда",
        },
        {
            "name": "Подписка Spotify", "kind": "expense", "account": "Сбер карта",
            "category_id": cat("Подписки"), "amount": 299, "frequency": "monthly",
            "start_at": _next_month_day(now, 1, 9),
            "note": "Spotify",
        },
        {
            "name": "Откладываю на накопительный", "kind": "transfer",
            "account": "Сбер карта", "category_id": None, "amount": 20000,
            "frequency": "monthly", "start_at": _next_month_day(now, 10, 12),
            "transfer_to": "Тинькофф накопит.", "note": "Автонакопление",
        },
        # Прошлое правило — назревшее: даст 1 операцию при первом /run.
        {
            "name": "Абонемент в зал", "kind": "expense", "account": "Сбер карта",
            "category_id": cat("Подписки"), "amount": 1990, "frequency": "monthly",
            "start_at": now - timedelta(days=2),
            "note": "Фитнес (тест авто-генерации)",
        },
    ]

    created = 0
    for rule in rules:
        body: dict = {
            "name": rule["name"],
            "kind": rule["kind"],
            "account_id": acc(rule["account"]),
            "amount": rule["amount"],
            "frequency": rule["frequency"],
            "interval": 1,
            "start_at": rule["start_at"].isoformat(),
            "note": rule["note"],
        }
        if rule.get("category_id") is not None:
            body["category_id"] = rule["category_id"]
        if rule["kind"] == "transfer":
            body["transfer_account_id"] = acc(rule["transfer_to"])

        r = client.post("/api/v1/recurring-transactions", json=body)
        if r.status_code == 201:
            created += 1
            when = rule["start_at"].strftime("%d.%m.%Y")
            print(f"   + {rule['name']:30s} {rule['frequency']:8s} с {when}")
        else:
            print(f"   ⚠ {rule['name']}: HTTP {r.status_code}: {r.text}")
    if created:
        print("   ℹ Одно правило («Абонемент в зал») назревшее — при заходе в")
        print("     приложение авто-/run создаст по нему 1 операцию.")
    return created


if __name__ == "__main__":
    sys.exit(main())
