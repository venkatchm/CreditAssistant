from __future__ import annotations

from datetime import date
from typing import Dict, List, Tuple

from synthetic.models import (
    CreditAccount,
    CreditReport,
    Inquiry,
    LoanAccount,
    PaymentHistoryEntry,
    Recommendation,
    User,
)
from synthetic.personas import PERSONA_ORDER, PERSONAS


REFERENCE_DATE = date(2026, 3, 20)


def months_between(start_date: str, end: date = REFERENCE_DATE) -> int:
    start = date.fromisoformat(start_date)
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def generate_users() -> List[User]:
    return [
        User(persona=persona_code, **PERSONAS[persona_code]["user"])
        for persona_code in PERSONA_ORDER
    ]


def generate_credit_accounts() -> List[CreditAccount]:
    accounts: List[CreditAccount] = []
    for persona_code in PERSONA_ORDER:
        user_id = PERSONAS[persona_code]["user"]["user_id"]
        for index, raw in enumerate(PERSONAS[persona_code]["credit_accounts"], start=1):
            utilization = raw["current_balance"] / raw["credit_limit"] if raw["credit_limit"] else 0.0
            accounts.append(
                CreditAccount(
                    account_id=f"ca_{user_id}_{index:02d}",
                    user_id=user_id,
                    utilization=round(utilization, 4),
                    **raw,
                )
            )
    return accounts


def generate_loan_accounts() -> List[LoanAccount]:
    loans: List[LoanAccount] = []
    for persona_code in PERSONA_ORDER:
        user_id = PERSONAS[persona_code]["user"]["user_id"]
        for index, raw in enumerate(PERSONAS[persona_code]["loan_accounts"], start=1):
            loans.append(
                LoanAccount(
                    account_id=f"la_{user_id}_{index:02d}",
                    user_id=user_id,
                    **raw,
                )
            )
    return loans


def generate_inquiries() -> List[Inquiry]:
    inquiries: List[Inquiry] = []
    for persona_code in PERSONA_ORDER:
        user_id = PERSONAS[persona_code]["user"]["user_id"]
        for index, raw in enumerate(PERSONAS[persona_code]["inquiries"], start=1):
            inquiries.append(
                Inquiry(
                    inquiry_id=f"iq_{user_id}_{index:02d}",
                    user_id=user_id,
                    **raw,
                )
            )
    return inquiries


def generate_payment_history(
    credit_accounts: List[CreditAccount],
    loan_accounts: List[LoanAccount],
) -> List[PaymentHistoryEntry]:
    accounts_by_user: Dict[str, List[Tuple[str, str]]] = {}
    for account in credit_accounts + loan_accounts:
        accounts_by_user.setdefault(account.user_id, []).append((account.account_id, account.payment_status))

    history: List[PaymentHistoryEntry] = []
    months = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
    for persona_code in PERSONA_ORDER:
        user_id = PERSONAS[persona_code]["user"]["user_id"]
        persona_statuses = PERSONAS[persona_code]["payment_history_statuses"]
        for account_index, (account_id, _) in enumerate(accounts_by_user[user_id], start=1):
            account_statuses = persona_statuses if accounts_by_user[user_id][account_index - 1][1] != "on_time" else ["on_time"] * len(months)
            for month_index, month in enumerate(months):
                status = account_statuses[month_index]
                amount_due = 120 + account_index * 40
                amount_paid = amount_due
                days_late = 0
                if status == "late_30":
                    amount_paid = int(amount_due * 0.5)
                    days_late = 30
                elif status == "late_60":
                    amount_paid = 0
                    days_late = 60
                elif status == "late_90":
                    amount_paid = 0
                    days_late = 90
                history.append(
                    PaymentHistoryEntry(
                        payment_id=f"ph_{user_id}_{account_index:02d}_{month.replace('-', '')}",
                        user_id=user_id,
                        account_id=account_id,
                        month=month,
                        status=status,
                        amount_due=amount_due,
                        amount_paid=amount_paid,
                        days_late=days_late,
                    )
                )
    return history


def generate_credit_reports(
    users: List[User],
    credit_accounts: List[CreditAccount],
    loan_accounts: List[LoanAccount],
    inquiries: List[Inquiry],
    payment_history: List[PaymentHistoryEntry],
) -> List[CreditReport]:
    credit_accounts_by_user: Dict[str, List[CreditAccount]] = {}
    loan_accounts_by_user: Dict[str, List[LoanAccount]] = {}
    inquiries_by_user: Dict[str, List[Inquiry]] = {}
    payments_by_user: Dict[str, List[PaymentHistoryEntry]] = {}

    for item in credit_accounts:
        credit_accounts_by_user.setdefault(item.user_id, []).append(item)
    for item in loan_accounts:
        loan_accounts_by_user.setdefault(item.user_id, []).append(item)
    for item in inquiries:
        inquiries_by_user.setdefault(item.user_id, []).append(item)
    for item in payment_history:
        payments_by_user.setdefault(item.user_id, []).append(item)

    reports: List[CreditReport] = []
    for user in users:
        persona = PERSONAS[user.persona]
        report_cfg = persona["report"]
        accounts = credit_accounts_by_user.get(user.user_id, []) + loan_accounts_by_user.get(user.user_id, [])
        ages = [months_between(account.opened_date) for account in accounts]
        revolving_limit = sum(account.credit_limit for account in credit_accounts_by_user.get(user.user_id, []))
        revolving_balance = sum(account.current_balance for account in credit_accounts_by_user.get(user.user_id, []))
        on_time_count = sum(1 for payment in payments_by_user.get(user.user_id, []) if payment.status == "on_time")
        payment_count = len(payments_by_user.get(user.user_id, [])) or 1
        score = report_cfg["score"]
        reports.append(
            CreditReport(
                report_id=f"cr_{user.user_id}",
                user_id=user.user_id,
                bureau=report_cfg["bureau"],
                score=score,
                score_band=score_band(score),
                score_change_30d=report_cfg["score_change_30d"],
                generated_at="2026-03-20",
                oldest_account_age_months=max(ages) if ages else 0,
                average_account_age_months=int(sum(ages) / len(ages)) if ages else 0,
                total_open_accounts=sum(1 for account in accounts if account.status == "open"),
                total_accounts=len(accounts),
                derogatory_marks=1 if any(payment.status != "on_time" for payment in payments_by_user.get(user.user_id, [])) else 0,
                bankruptcies=0,
                collections=0,
                hard_inquiries_12m=sum(
                    1
                    for inquiry in inquiries_by_user.get(user.user_id, [])
                    if inquiry.is_hard and months_between(inquiry.inquiry_date) <= 12
                ),
                revolving_utilization=round(revolving_balance / revolving_limit, 4) if revolving_limit else 0.0,
                payment_history_ratio=round(on_time_count / payment_count, 4),
                summary=report_cfg["summary"],
                score_factors=report_cfg["score_factors"],
            )
        )
    return reports


def score_band(score: int) -> str:
    if score >= 800:
        return "exceptional"
    if score >= 740:
        return "very_good"
    if score >= 670:
        return "good"
    if score >= 580:
        return "fair"
    return "poor"
