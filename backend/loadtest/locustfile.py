"""Нагрузочный тест FinTrack на Locust.

Сценарий моделирует типичную read-heavy нагрузку: каждый виртуальный пользователь
регистрируется, входит, создаёт счёт и несколько операций (чтобы списки и отчёты были
непустыми), после чего циклически читает основные эндпоинты — список операций,
дашборд, отчёты, счета, курсы. Веса задач отражают частоту обращений в реальном UI.

Запуск и снятие графиков — см. changes/loadtest-locust/INSTRUCTIONS.md.
"""
import uuid
from datetime import datetime, timezone

from locust import HttpUser, between, task


class FinTrackUser(HttpUser):
    # Пауза между запросами одного пользователя — имитация «думающего» человека.
    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Подготовка пользователя: регистрация, вход, посев данных."""
        email = f"load_{uuid.uuid4().hex[:12]}@example.com"
        password = "LoadTest123"  # удовлетворяет политике: буква + цифра, >= 8

        self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
            name="/auth/register",
        )
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            name="/auth/login",
        )
        token = resp.json().get("access_token") if resp.status_code == 200 else None
        if token:
            self.client.headers.update({"Authorization": f"Bearer {token}"})

        # Посев: один счёт и несколько расходов, чтобы read-эндпоинты возвращали данные.
        acc = self.client.post(
            "/api/v1/accounts",
            json={"name": "Карта", "opening_balance": "10000", "currency_code": "RUB"},
            name="/accounts [POST]",
        )
        self.account_id = acc.json().get("id") if acc.status_code == 201 else None
        if self.account_id is not None:
            now = datetime.now(timezone.utc).isoformat()
            for _ in range(5):
                self.client.post(
                    "/api/v1/transactions",
                    json={
                        "kind": "expense",
                        "account_id": self.account_id,
                        "amount": "100",
                        "occurred_at": now,
                    },
                    name="/transactions [POST]",
                )

    # --- Основная read-heavy нагрузка (веса = относительная частота) ---

    @task(5)
    def list_transactions(self) -> None:
        self.client.get("/api/v1/transactions", name="/transactions")

    @task(3)
    def dashboard(self) -> None:
        self.client.get("/api/v1/dashboard/summary", name="/dashboard/summary")

    @task(2)
    def reports(self) -> None:
        self.client.get("/api/v1/reports/overview", name="/reports/overview")

    @task(2)
    def accounts(self) -> None:
        self.client.get("/api/v1/accounts", name="/accounts")

    @task(1)
    def rates(self) -> None:
        self.client.get("/api/v1/rates", name="/rates")
