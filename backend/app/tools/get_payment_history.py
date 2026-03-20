from __future__ import annotations

from app.schemas.credit import PaymentHistoryResponse
from app.services.payment_history_service import PaymentHistoryService


def get_payment_history(service: PaymentHistoryService, user_id: str) -> PaymentHistoryResponse:
    return PaymentHistoryResponse(user_id=user_id, payment_history=service.get_payment_history(user_id))
