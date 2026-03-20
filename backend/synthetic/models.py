from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


PersonaCode = Literal[
    "EXCELLENT_PROFILE",
    "HIGH_UTILIZATION_USER",
    "RECENT_DELINQUENCY_USER",
    "THIN_FILE_USER",
    "CREDIT_HUNGRY_USER",
]

AccountType = Literal["credit_card", "charge_card", "auto_loan", "student_loan", "personal_loan", "mortgage"]
AccountStatus = Literal["open", "closed"]
InquiryType = Literal["credit_card", "auto", "personal_loan", "mortgage", "student_loan"]
PaymentStatus = Literal["on_time", "late_30", "late_60", "late_90"]


class User(BaseModel):
    user_id: str
    full_name: str
    age: int
    city: str
    state: str
    occupation: str
    annual_income: int
    persona: PersonaCode


class CreditReport(BaseModel):
    report_id: str
    user_id: str
    bureau: str
    score: int
    score_band: str
    score_change_30d: int
    generated_at: str
    oldest_account_age_months: int
    average_account_age_months: int
    total_open_accounts: int
    total_accounts: int
    derogatory_marks: int
    bankruptcies: int
    collections: int
    hard_inquiries_12m: int
    revolving_utilization: float
    payment_history_ratio: float
    summary: str
    score_factors: List[str]


class CreditAccount(BaseModel):
    account_id: str
    user_id: str
    issuer: str
    product_name: str
    account_type: Literal["credit_card", "charge_card"]
    status: AccountStatus
    opened_date: str
    closed_date: Optional[str] = None
    credit_limit: int
    current_balance: int
    apr: float
    autopay_enabled: bool
    utilization: float
    payment_status: PaymentStatus


class LoanAccount(BaseModel):
    account_id: str
    user_id: str
    lender: str
    product_name: str
    account_type: Literal["auto_loan", "student_loan", "personal_loan", "mortgage"]
    status: AccountStatus
    opened_date: str
    original_balance: int
    current_balance: int
    monthly_payment: int
    interest_rate: float
    payment_status: PaymentStatus


class Inquiry(BaseModel):
    inquiry_id: str
    user_id: str
    creditor: str
    inquiry_type: InquiryType
    inquiry_date: str
    bureau: str
    is_hard: bool


class PaymentHistoryEntry(BaseModel):
    payment_id: str
    user_id: str
    account_id: str
    month: str
    status: PaymentStatus
    amount_due: int
    amount_paid: int
    days_late: int


class MetricTrend(BaseModel):
    metric: str
    direction: Literal["improving", "stable", "worsening"]
    detail: str


class CreditMetrics(BaseModel):
    user_id: str
    score: int
    score_band: str
    score_change_30d: int
    revolving_limit_total: int
    revolving_balance_total: int
    revolving_utilization: float
    installment_balance_total: int
    installment_original_total: int
    installment_utilization: float
    open_revolving_accounts: int
    open_installment_accounts: int
    total_hard_inquiries_12m: int
    recent_hard_inquiries_90d: int
    on_time_payment_ratio: float
    delinquent_accounts: int
    months_since_last_delinquency: Optional[int] = None
    total_available_credit: int
    trends: List[MetricTrend] = Field(default_factory=list)
    key_drivers: List[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    recommendation_id: str
    user_id: str
    title: str
    priority: Literal["high", "medium", "low"]
    category: Literal["utilization", "payment_history", "inquiries", "credit_mix", "monitoring"]
    rationale: str
    action: str
    expected_impact: str


class CreditProfile(BaseModel):
    user: User
    credit_report: CreditReport
    credit_accounts: List[CreditAccount]
    loan_accounts: List[LoanAccount]
    inquiries: List[Inquiry]
    payment_history: List[PaymentHistoryEntry]
    metrics: CreditMetrics
    recommendations: List[Recommendation]
