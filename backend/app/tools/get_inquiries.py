from __future__ import annotations

from app.schemas.credit import InquiriesResponse
from app.services.inquiry_service import InquiryService


def get_inquiries(service: InquiryService, user_id: str) -> InquiriesResponse:
    return InquiriesResponse(user_id=user_id, inquiries=service.get_inquiries(user_id))
