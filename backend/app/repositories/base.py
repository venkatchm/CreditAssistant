from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from synthetic.models import CreditAccount, CreditMetrics, CreditReport, Inquiry, LoanAccount, PaymentHistoryEntry, Recommendation, User


class CreditRepository(ABC):
    @abstractmethod
    def list_users(self) -> List[User]:
        raise NotImplementedError

    @abstractmethod
    def get_user(self, user_id: str) -> Optional[User]:
        raise NotImplementedError

    @abstractmethod
    def get_credit_report(self, user_id: str) -> Optional[CreditReport]:
        raise NotImplementedError

    @abstractmethod
    def list_credit_accounts(self, user_id: str) -> List[CreditAccount]:
        raise NotImplementedError

    @abstractmethod
    def list_loan_accounts(self, user_id: str) -> List[LoanAccount]:
        raise NotImplementedError

    @abstractmethod
    def list_inquiries(self, user_id: str) -> List[Inquiry]:
        raise NotImplementedError

    @abstractmethod
    def list_payment_history(self, user_id: str) -> List[PaymentHistoryEntry]:
        raise NotImplementedError

    @abstractmethod
    def get_metrics(self, user_id: str) -> Optional[CreditMetrics]:
        raise NotImplementedError

    @abstractmethod
    def list_recommendations(self, user_id: str) -> List[Recommendation]:
        raise NotImplementedError
