from __future__ import annotations

import json
from pathlib import Path
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
        self._users = self._load("users.json", User)
        self._reports = self._load("credit_reports.json", CreditReport)
        self._credit_accounts = self._load("credit_accounts.json", CreditAccount)
        self._loan_accounts = self._load("loan_accounts.json", LoanAccount)
        self._inquiries = self._load("inquiries.json", Inquiry)
        self._payment_history = self._load("payment_history.json", PaymentHistoryEntry)
        self._metrics = self._load("credit_metrics.json", CreditMetrics)
        self._recommendations = self._load("recommendations.json", Recommendation)

    def _load(self, file_name: str, model_cls: Type[ModelT]) -> List[ModelT]:
        with (self.data_dir / file_name).open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return [model_cls(**row) for row in payload]

    def list_users(self) -> List[User]:
        return list(self._users)

    def get_user(self, user_id: str) -> Optional[User]:
        return self._find_one(self._users, "user_id", user_id)

    def get_credit_report(self, user_id: str) -> Optional[CreditReport]:
        return self._find_one(self._reports, "user_id", user_id)

    def list_credit_accounts(self, user_id: str) -> List[CreditAccount]:
        return [item for item in self._credit_accounts if item.user_id == user_id]

    def list_loan_accounts(self, user_id: str) -> List[LoanAccount]:
        return [item for item in self._loan_accounts if item.user_id == user_id]

    def list_inquiries(self, user_id: str) -> List[Inquiry]:
        return [item for item in self._inquiries if item.user_id == user_id]

    def list_payment_history(self, user_id: str) -> List[PaymentHistoryEntry]:
        return [item for item in self._payment_history if item.user_id == user_id]

    def get_metrics(self, user_id: str) -> Optional[CreditMetrics]:
        return self._find_one(self._metrics, "user_id", user_id)

    def list_recommendations(self, user_id: str) -> List[Recommendation]:
        return [item for item in self._recommendations if item.user_id == user_id]

    @staticmethod
    def _find_one(items: List[ModelT], field: str, value: str) -> Optional[ModelT]:
        for item in items:
            if getattr(item, field) == value:
                return item
        return None
