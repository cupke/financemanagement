#!/usr/bin/env python3
"""seed_test_data.py — заполнение БД FinTrack тестовыми данными.

Что создаёт:
- Тестового юзера (по умолчанию seed@example.com / seedpass123).
- 4 счёта разных типов и валют (Сбер карта, Тинькофф накопит., Наличные, USD карта).
- Дерево категорий: 4 expense-категории с подкатегориями + 3 income.
- ~23 транзакции последних 2 месяцев: доходы, расходы, переводы.
  Часть из них — старше opening_date (30 дней назад), чтобы показать,
  как они попадают в историю с бейджем «не в балансе» и НЕ двигают balance.

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

        print(f"✅ Готово!")
        print(f"   {count_recent} операций после opening_date (двигают balance)")
        print(f"   {count_retro} операций до opening_date (бейдж «не в балансе»)")
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
        {"name": "Наличные",          "kind": "cash",    "opening_balance": 8000,   "currency_code": "RUB"},
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

# Описание транзакций в виде списка dict'ов. days_ago = сколько дней назад
# произошла операция (0 = сегодня; >30 = до opening_date → бейдж «не в балансе»).
# transfer_to — имя счёта-получателя (только для kind='transfer').
TRANSACTIONS = [
    # === Recent (within opening_date — двигают balance) ===
    # Income
    {"kind": "income",   "from": "Сбер карта",       "cat": "Зарплата",  "amount": 85000, "days_ago": 1,  "note": "Зарплата за май"},
    {"kind": "income",   "from": "Наличные",         "cat": "Подарки",   "amount": 5000,  "days_ago": 10, "note": "ДР"},
    {"kind": "income",   "from": "Сбер карта",       "cat": "Фриланс",   "amount": 22000, "days_ago": 14, "note": "Сайт для клиента"},
    # Expense — еда
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Продукты",  "amount": 3500,  "days_ago": 0,  "note": "Перекрёсток"},
    {"kind": "expense",  "from": "Наличные",         "cat": "Продукты",  "amount": 1200,  "days_ago": 2,  "note": "Магнит у дома"},
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Кафе",      "amount": 850,   "days_ago": 3,  "note": "Кофейня"},
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Доставка",  "amount": 1800,  "days_ago": 5,  "note": "Яндекс.Еда"},
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Кафе",      "amount": 2100,  "days_ago": 7,  "note": "Ужин с друзьями"},
    # Expense — транспорт
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Такси",     "amount": 450,   "days_ago": 1,  "note": None},
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Такси",     "amount": 380,   "days_ago": 4,  "note": None},
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Бензин",    "amount": 3200,  "days_ago": 12, "note": "Лукойл"},
    # Expense — жильё / подписки
    {"kind": "expense",  "from": "Сбер карта",       "cat": "ЖКХ",       "amount": 4800,  "days_ago": 15, "note": "Коммуналка"},
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Подписки",  "amount": 299,   "days_ago": 8,  "note": "Spotify"},
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Подписки",  "amount": 599,   "days_ago": 8,  "note": "YouTube Premium"},
    {"kind": "expense",  "from": "Наличные",         "cat": "Кино",      "amount": 800,   "days_ago": 11, "note": "Сеанс"},
    # USD-карта
    {"kind": "expense",  "from": "USD карта",        "cat": "Подписки",  "amount": 12,    "days_ago": 4,  "note": "Apple One"},
    {"kind": "expense",  "from": "USD карта",        "cat": "Доставка",  "amount": 35,    "days_ago": 18, "note": "Amazon"},
    # Переводы recent
    {"kind": "transfer", "from": "Тинькофф накопит.", "cat": None,        "amount": 20000, "days_ago": 2,  "note": "Снял с накопит.", "transfer_to": "Сбер карта"},
    {"kind": "transfer", "from": "Сбер карта",       "cat": None,        "amount": 5000,  "days_ago": 6,  "note": "Снятие наличных",  "transfer_to": "Наличные"},

    # === Retro (старее opening_date — НЕ двигают balance, бейдж «не в балансе») ===
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Продукты",  "amount": 2400,  "days_ago": 45, "note": "Закупка апрель"},
    {"kind": "expense",  "from": "Сбер карта",       "cat": "Аренда",    "amount": 35000, "days_ago": 50, "note": "Аренда апрель (ретро)"},
    {"kind": "income",   "from": "Сбер карта",       "cat": "Зарплата",  "amount": 80000, "days_ago": 55, "note": "Зарплата апрель (ретро)"},
    {"kind": "expense",  "from": "Наличные",         "cat": "Кафе",      "amount": 600,   "days_ago": 40, "note": "Старый кофе"},
    {"kind": "transfer", "from": "Тинькофф накопит.", "cat": None,        "amount": 50000, "days_ago": 60, "note": "Старый перевод (ретро)", "transfer_to": "Сбер карта"},
]


def create_transactions(client: httpx.Client, accounts: dict[str, dict],
                        categories: dict[str, dict]) -> tuple[int, int]:
    """Создаёт транзакции из TRANSACTIONS. Возвращает (recent_count, retro_count)."""
    recent = retro = 0
    now = datetime.now(timezone.utc)
    for tx in TRANSACTIONS:
        occurred = now - timedelta(days=tx["days_ago"])
        body = {
            "kind": tx["kind"],
            "account_id": accounts[tx["from"]]["id"],
            "amount": tx["amount"],
            "occurred_at": occurred.isoformat(),
            "note": tx.get("note"),
        }
        if tx["cat"] is not None:
            body["category_id"] = categories[tx["cat"]]["id"]
        if tx["kind"] == "transfer":
            body["transfer_account_id"] = accounts[tx["transfer_to"]]["id"]

        r = client.post("/api/v1/transactions", json=body)
        if r.status_code != 201:
            print(f"   ❌ {tx['kind']} {tx['amount']} ({tx.get('note', '')}): "
                  f"HTTP {r.status_code}: {r.text}")
            sys.exit(1)

        # Понять, retro или recent — по тому же критерию, что бэк.
        is_retro = tx["days_ago"] > OPENING_DATE_DAYS_AGO
        if is_retro:
            retro += 1
            tag = "ретро"
        else:
            recent += 1
            tag = "      "

        # Симметричное отображение: тип, тэг, сумма, заметка.
        note_str = f" — {tx['note']}" if tx.get("note") else ""
        print(f"   {tag} {tx['kind']:8s} {tx['amount']:>6} "
              f"{tx['from']:22s}{note_str}")

    return recent, retro


if __name__ == "__main__":
    sys.exit(main())
