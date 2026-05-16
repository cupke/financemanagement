# FinTrack

> Self-hosted веб-приложение для учёта личных финансов с мультивалютностью по курсам ЦБ РФ, бюджетированием и автоматическими операциями.

Проект разрабатывается в рамках выпускной квалификационной работы по направлению **09.03.04 «Программная инженерия»** (СКФУ, Ставрополь, 2026).

---

## Что уже работает

- **Счета** четырёх типов (карта / наличные / накопит. / кредитка / e-кошелёк / прочее) в любой валюте.
- **Категории** с разделением «доход / расход» и древовидной иерархией (родитель → подкатегории).
- **Операции** трёх типов (доход / расход / перевод между своими счетами) с фильтрами по периоду, счёту, категории, типу + поиск по заметке.
- **Модель «opening_balance + движения»** — учитывает «снимок остатка» на дату создания счёта; ретро-операции «до этой даты» видны в истории, но не двигают баланс (как в бухгалтерских системах GnuCash, Beancount).
- **Атомарные изменения балансов** в одной БД-транзакции (защита от рассинхрона при параллельных операциях).
- **Курсы валют ЦБ РФ** через cache-aside-паттерн, общий капитал в RUB по живому курсу.
- **Регистрация и аутентификация** через JWT + Argon2id, защита от IDOR на всех ресурсах.
- **Право на забвение** (152-ФЗ ст. 19): пользователь может самостоятельно удалить аккаунт со всеми данными.
- **Self-hosted Swagger UI** на `/docs` (без внешних CDN).
- **Развёртывание одной командой** через `docker compose up -d` (после первичной настройки `.env`).

## В планах

- Автоматические повторяющиеся операции (зарплата каждое 10-е, подписки и т.п.).
- Бюджеты по категориям с уведомлением о превышении.
- Сводные отчёты и графики, экспорт в CSV.
- PWA с установкой на мобильный + быстрый ввод операции одним тапом.
- pytest, GitHub Actions CI/CD.

---

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0 (async + typed Mapped), Alembic, Pydantic v2 |
| База данных | PostgreSQL 15 |
| Frontend | TypeScript 5, React 18, Vite, Mantine 9, TanStack Query, Zod |
| Инфраструктура | Docker, docker-compose, GitHub Flow с `--no-ff` merge, Conventional Commits |

---

## Запуск локально

### Что нужно установить разово

| Инструмент | Зачем |
|---|---|
| [Git](https://git-scm.com) | Склонировать репозиторий |
| [Docker Desktop](https://www.docker.com/products/docker-desktop) | Запустить БД и бэкенд (должен быть запущен на момент `docker compose up`) |
| [Node.js 20+](https://nodejs.org) | Запустить frontend (Vite dev server) |
| [Python 3.11+](https://www.python.org) *(опционально)* | Только для seed-скрипта с тестовыми данными |

### Пошагово (Windows / PowerShell)

**1. Склонировать репозиторий**

```powershell
git clone https://github.com/cupke/financemanagement.git
cd financemanagement
```

**2. Создать `backend/.env` с JWT-секретом**

Бэкенд требует переменную `JWT_SECRET_KEY` — без неё не стартует. Сгенерировать случайную строку:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Скопировать вывод. Создать файл `backend\.env` со строкой:

```
JWT_SECRET_KEY=<вставить_сгенерированную_строку>
```

> `DATABASE_URL` уже задана в `docker-compose.yml` — повторять её в `.env` не нужно.

**3. Поднять БД и бэкенд**

```powershell
docker compose up -d --build
```

Первая сборка займёт 1-3 минуты (скачивание образов Python и Postgres). Проверить, что бэкенд жив:

```powershell
curl http://127.0.0.1:60000/health
```

Ожидаемый ответ: `{"status":"ok"}`.

**4. Применить миграции БД**

```powershell
docker compose exec backend alembic upgrade head
```

**5. Поднять frontend (в новом окне PowerShell)**

```powershell
cd D:\путь\к\financemanagement\frontend
npm install
npm run dev
```

После старта Vite напечатает `Local: http://127.0.0.1:60001/`.

**6. Открыть приложение**

[http://127.0.0.1:60001](http://127.0.0.1:60001) → зарегистрироваться (любой email + пароль).

### Опционально: наполнить тестовыми данными

Если есть Python — за 3 секунды получаешь готовый набор (4 счёта, ~15 категорий, ~25 транзакций) для проверки фич:

```powershell
py -m pip install httpx     # один раз
py seed_test_data.py
```

Залогиниться как `seed@example.com` / `seedpass123`.

### Остановить и почистить

```powershell
docker compose down         # остановить (данные сохраняются в volume)
docker compose down -v      # остановить + полностью снести БД (для чистого старта)
```

В окне с frontend — `Ctrl + C`.

---

## Известные особенности Windows-окружения

1. **PowerShell блокирует скрипты по умолчанию.** Перед первым `npm run dev` или `Activate.ps1` в новом окне:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   ```

2. **Hyper-V (включается с Docker Desktop) блокирует порты 1024–50000.** Поэтому в проекте используются порты выше: бэкенд 60000, frontend 60001, Postgres 55432. Если другие порты падают с `WinError 10013` — это оно.

3. **VS Code иногда автозахватывает свободные dev-порты.** Если `npm run dev` не стартует — закрыть VS Code, запустить, открыть обратно.

---

## Структура репозитория

```
financemanagement/
├── backend/                  ← FastAPI-приложение
│   ├── app/                  ← код приложения (api, db, schemas, security)
│   ├── alembic/              ← миграции БД
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 ← React SPA
│   ├── src/                  ← компоненты, страницы, api-клиент
│   └── package.json
├── docker-compose.yml        ← запуск БД + бэкенда
├── seed_test_data.py         ← скрипт для тестовых данных (опционально)
└── README.md
```

---

## Статус

В разработке. Ведётся в рамках ВКР, защита — лето 2026 г.

История фич — в `git log --graph --oneline`.

---

## Лицензия

[MIT](LICENSE)
