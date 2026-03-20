from __future__ import annotations

from app.schemas.credit import CreditProfileResponse
from app.schemas.users import UserDetail
from app.services.credit_service import CreditService


def get_credit_profile(service: CreditService, user_id: str) -> CreditProfileResponse:
    profile = service.get_credit_profile(user_id)
    return CreditProfileResponse(
        user=UserDetail.from_user(profile.user),
        credit_report=profile.credit_report,
        credit_accounts=profile.credit_accounts,
        loan_accounts=profile.loan_accounts,
        metrics=profile.metrics,
    )
