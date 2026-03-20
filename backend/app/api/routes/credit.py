from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_credit_service, get_inquiry_service, get_metrics_service, get_payment_history_service, get_recommendation_service
from app.schemas.credit import CreditMetricsResponse, CreditProfileResponse, InquiriesResponse, PaymentHistoryResponse, RecommendationsResponse
from app.services.credit_service import CreditService
from app.services.inquiry_service import InquiryService
from app.services.metrics_service import MetricsService
from app.services.payment_history_service import PaymentHistoryService
from app.services.recommendation_service import RecommendationService
from app.tools.get_credit_metrics import get_credit_metrics as get_credit_metrics_tool
from app.tools.get_credit_profile import get_credit_profile as get_credit_profile_tool
from app.tools.get_inquiries import get_inquiries as get_inquiries_tool
from app.tools.get_payment_history import get_payment_history as get_payment_history_tool
from app.tools.get_recommendations import get_recommendations as get_recommendations_tool


router = APIRouter(prefix="/credit", tags=["credit"])


@router.get("/profile/{user_id}", response_model=CreditProfileResponse)
def get_credit_profile(user_id: str, credit_service: CreditService = Depends(get_credit_service)) -> CreditProfileResponse:
    return get_credit_profile_tool(credit_service, user_id)


@router.get("/metrics/{user_id}", response_model=CreditMetricsResponse)
def get_credit_metrics(user_id: str, metrics_service: MetricsService = Depends(get_metrics_service)) -> CreditMetricsResponse:
    return get_credit_metrics_tool(metrics_service, user_id)


@router.get("/recommendations/{user_id}", response_model=RecommendationsResponse)
def get_credit_recommendations(
    user_id: str,
    recommendation_service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationsResponse:
    return get_recommendations_tool(recommendation_service, user_id)


@router.get("/inquiries/{user_id}", response_model=InquiriesResponse)
def get_credit_inquiries(user_id: str, inquiry_service: InquiryService = Depends(get_inquiry_service)) -> InquiriesResponse:
    return get_inquiries_tool(inquiry_service, user_id)


@router.get("/payment-history/{user_id}", response_model=PaymentHistoryResponse)
def get_credit_payment_history(
    user_id: str,
    payment_history_service: PaymentHistoryService = Depends(get_payment_history_service),
) -> PaymentHistoryResponse:
    return get_payment_history_tool(payment_history_service, user_id)
