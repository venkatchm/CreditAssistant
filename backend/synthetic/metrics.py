from __future__ import annotations

from datetime import date
from typing import List, Optional

from synthetic.generators import REFERENCE_DATE
from synthetic.models import (
    CreditAccount,
    CreditMetrics,
    CreditReport,
    Inquiry,
    LoanAccount,
    MetricTrend,
    PaymentHistoryEntry,
)


def compute_credit_metrics(
    report: CreditReport,
    credit_accounts: List[CreditAccount],
    loan_accounts: List[LoanAccount],
    inquiries: List[Inquiry],
    payment_history: List[PaymentHistoryEntry],
) -> CreditMetrics:
    revolving_limit_total = sum(account.credit_limit for account in credit_accounts if account.status == "open")
    revolving_balance_total = sum(account.current_balance for account in credit_accounts if account.status == "open")
    installment_original_total = sum(account.original_balance for account in loan_accounts if account.status == "open")
    installment_balance_total = sum(account.current_balance for account in loan_accounts if account.status == "open")
    on_time_count = sum(1 for payment in payment_history if payment.status == "on_time")
    payment_count = len(payment_history) or 1
    delinquent_entries = [payment for payment in payment_history if payment.status != "on_time"]
    recent_hard_inquiries_90d = sum(
        1 for inquiry in inquiries if inquiry.is_hard and months_since(inquiry.inquiry_date) <= 3
    )
    total_hard_inquiries_12m = sum(
        1 for inquiry in inquiries if inquiry.is_hard and months_since(inquiry.inquiry_date) <= 12
    )
    months_since_last_delinquency = latest_delinquency_months(delinquent_entries)

    revolving_utilization = round(revolving_balance_total / revolving_limit_total, 4) if revolving_limit_total else 0.0
    installment_utilization = (
        round(installment_balance_total / installment_original_total, 4)
        if installment_original_total
        else 0.0
    )

    trends = build_trends(report.score_change_30d, revolving_utilization, recent_hard_inquiries_90d, months_since_last_delinquency)
    key_drivers = build_key_drivers(revolving_utilization, total_hard_inquiries_12m, months_since_last_delinquency, report)

    return CreditMetrics(
        user_id=report.user_id,
        score=report.score,
        score_band=report.score_band,
        score_change_30d=report.score_change_30d,
        revolving_limit_total=revolving_limit_total,
        revolving_balance_total=revolving_balance_total,
        revolving_utilization=revolving_utilization,
        installment_balance_total=installment_balance_total,
        installment_original_total=installment_original_total,
        installment_utilization=installment_utilization,
        open_revolving_accounts=sum(1 for account in credit_accounts if account.status == "open"),
        open_installment_accounts=sum(1 for account in loan_accounts if account.status == "open"),
        total_hard_inquiries_12m=total_hard_inquiries_12m,
        recent_hard_inquiries_90d=recent_hard_inquiries_90d,
        on_time_payment_ratio=round(on_time_count / payment_count, 4),
        delinquent_accounts=len({payment.account_id for payment in delinquent_entries}),
        months_since_last_delinquency=months_since_last_delinquency,
        total_available_credit=max(revolving_limit_total - revolving_balance_total, 0),
        trends=trends,
        key_drivers=key_drivers,
    )


def months_since(iso_date: str) -> int:
    start = date.fromisoformat(iso_date)
    months = (REFERENCE_DATE.year - start.year) * 12 + (REFERENCE_DATE.month - start.month)
    if REFERENCE_DATE.day < start.day:
        months -= 1
    return max(months, 0)


def latest_delinquency_months(entries: List[PaymentHistoryEntry]) -> Optional[int]:
    if not entries:
        return None
    latest = max(entries, key=lambda item: item.month)
    return months_since(f"{latest.month}-01")


def build_trends(
    score_change_30d: int,
    utilization: float,
    recent_hard_inquiries_90d: int,
    months_since_last_delinquency: Optional[int],
) -> List[MetricTrend]:
    score_direction = "improving" if score_change_30d > 0 else "worsening" if score_change_30d < 0 else "stable"
    utilization_direction = "worsening" if utilization >= 0.5 else "stable" if utilization >= 0.1 else "improving"
    inquiry_direction = "worsening" if recent_hard_inquiries_90d >= 2 else "stable"
    payment_direction = "worsening" if months_since_last_delinquency == 2 else "stable" if months_since_last_delinquency else "improving"
    return [
        MetricTrend(metric="score", direction=score_direction, detail=f"Score moved {score_change_30d} points in the last 30 days."),
        MetricTrend(metric="utilization", direction=utilization_direction, detail=f"Revolving utilization is {utilization:.1%}."),
        MetricTrend(metric="inquiries", direction=inquiry_direction, detail=f"{recent_hard_inquiries_90d} hard inquiries posted in the last 90 days."),
        MetricTrend(metric="payment_history", direction=payment_direction, detail=payment_detail(months_since_last_delinquency)),
    ]


def payment_detail(months_since_last_delinquency: Optional[int]) -> str:
    if months_since_last_delinquency is None:
        return "No delinquencies were found in recent payment history."
    return f"Last delinquency was {months_since_last_delinquency} months ago."


def build_key_drivers(
    utilization: float,
    total_hard_inquiries_12m: int,
    months_since_last_delinquency: Optional[int],
    report: CreditReport,
) -> List[str]:
    drivers: List[str] = []
    if utilization >= 0.5:
        drivers.append("High revolving utilization is suppressing the score.")
    elif utilization <= 0.1:
        drivers.append("Low card utilization is helping the score.")
    if total_hard_inquiries_12m >= 3:
        drivers.append("Several recent hard inquiries are adding risk.")
    if months_since_last_delinquency is not None and months_since_last_delinquency <= 6:
        drivers.append("A recent delinquency remains a major negative factor.")
    drivers.extend(report.score_factors[:2])
    return drivers[:4]
