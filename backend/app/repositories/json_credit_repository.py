from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import List, Optional, Type, TypeVar

from app.repositories.base import CreditRepository
from synthetic.models import (
    CreditAccount,
    CreditMetrics,
    CreditReport,
    Inquiry,
    LoanAccount,
    PaymentHistoryEntry,
    Recommendation,
    User,
)


ModelT = TypeVar("ModelT")


class JsonCreditRepository(CreditRepository):
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir or Path(__file__).resolve().parents[2] / "data"
        self._lock = RLock()
        self.reload()

    def reload(self) -> None:
        with self._lock:
            # Load and index once so repeated /chat calls do not hit the filesystem.
            self._users = self._load("users.json", User)
            self._reports = self._load("credit_reports.json", CreditReport)
            self._credit_accounts = self._load("credit_accounts.json", CreditAccount)
            self._loan_accounts = self._load("loan_accounts.json", LoanAccount)
            self._inquiries = self._load("inquiries.json", Inquiry)
            self._payment_history = self._load("payment_history.json", PaymentHistoryEntry)
            self._metrics = self._load("credit_metrics.json", CreditMetrics)
            self._recommendations = self._load("recommendations.json", Recommendation)
            self._users_by_id = {item.user_id: item for item in self._users}
            self._reports_by_user_id = {item.user_id: item for item in self._reports}
            self._metrics_by_user_id = {item.user_id: item for item in self._metrics}
            self._credit_accounts_by_user_id = self._group_by_user_id(self._credit_accounts)
            self._loan_accounts_by_user_id = self._group_by_user_id(self._loan_accounts)
            self._inquiries_by_user_id = self._group_by_user_id(self._inquiries)
            self._payment_history_by_user_id = self._group_by_user_id(self._payment_history)
            self._recommendations_by_user_id = self._group_by_user_id(self._recommendations)

    def _load(self, file_name: str, model_cls: Type[ModelT]) -> List[ModelT]:
        with (self.data_dir / file_name).open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return [model_cls(**row) for row in payload]

    def list_users(self) -> List[User]:
        with self._lock:
            return list(self._users)

    def get_user(self, user_id: str) -> Optional[User]:
        with self._lock:
            return self._users_by_id.get(user_id)

    def get_credit_report(self, user_id: str) -> Optional[CreditReport]:
        with self._lock:
            return self._reports_by_user_id.get(user_id)

    def list_credit_accounts(self, user_id: str) -> List[CreditAccount]:
        with self._lock:
            return list(self._credit_accounts_by_user_id.get(user_id, []))

    def list_loan_accounts(self, user_id: str) -> List[LoanAccount]:
        with self._lock:
            return list(self._loan_accounts_by_user_id.get(user_id, []))

    def list_inquiries(self, user_id: str) -> List[Inquiry]:
        with self._lock:
            return list(self._inquiries_by_user_id.get(user_id, []))

    def list_payment_history(self, user_id: str) -> List[PaymentHistoryEntry]:
        with self._lock:
            return list(self._payment_history_by_user_id.get(user_id, []))

    def get_metrics(self, user_id: str) -> Optional[CreditMetrics]:
        with self._lock:
            return self._metrics_by_user_id.get(user_id)

    def list_recommendations(self, user_id: str) -> List[Recommendation]:
        with self._lock:
            return list(self._recommendations_by_user_id.get(user_id, []))

    @staticmethod
    def _find_one(items: List[ModelT], field: str, value: str) -> Optional[ModelT]:
        for item in items:
            if getattr(item, field) == value:
                return item
        return None

    @staticmethod
    def _group_by_user_id(items: List[ModelT]) -> dict[str, List[ModelT]]:
        grouped: dict[str, List[ModelT]] = {}
        for item in items:
            grouped.setdefault(getattr(item, "user_id"), []).append(item)
        return grouped
