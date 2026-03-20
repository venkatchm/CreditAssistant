from __future__ import annotations

from typing import List

from pydantic import BaseModel

from app.schemas.users import UserDetail
from synthetic.models import CreditAccount, CreditMetrics, CreditReport, Inquiry, LoanAccount, PaymentHistoryEntry, Recommendation


class CreditProfileResponse(BaseModel):
    user: UserDetail
    credit_report: CreditReport
    credit_accounts: List[CreditAccount]
    loan_accounts: List[LoanAccount]
    metrics: CreditMetrics


class CreditMetricsResponse(BaseModel):
    metrics: CreditMetrics


class RecommendationsResponse(BaseModel):
    user_id: str
    recommendations: List[Recommendation]


class InquiriesResponse(BaseModel):
    user_id: str
    inquiries: List[Inquiry]


class PaymentHistoryResponse(BaseModel):
    user_id: str
    payment_history: List[PaymentHistoryEntry]
