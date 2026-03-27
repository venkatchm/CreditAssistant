-- Credit data tables (migrated from JSON files)

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    age INTEGER NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    occupation TEXT NOT NULL,
    annual_income INTEGER NOT NULL,
    persona TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_reports (
    report_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    bureau TEXT NOT NULL,
    score INTEGER NOT NULL,
    score_band TEXT NOT NULL,
    score_change_30d INTEGER NOT NULL DEFAULT 0,
    generated_at TEXT NOT NULL,
    oldest_account_age_months INTEGER NOT NULL DEFAULT 0,
    average_account_age_months INTEGER NOT NULL DEFAULT 0,
    total_open_accounts INTEGER NOT NULL DEFAULT 0,
    total_accounts INTEGER NOT NULL DEFAULT 0,
    derogatory_marks INTEGER NOT NULL DEFAULT 0,
    bankruptcies INTEGER NOT NULL DEFAULT 0,
    collections INTEGER NOT NULL DEFAULT 0,
    hard_inquiries_12m INTEGER NOT NULL DEFAULT 0,
    revolving_utilization REAL NOT NULL DEFAULT 0,
    payment_history_ratio REAL NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    score_factors JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_credit_reports_user_id ON credit_reports(user_id);

CREATE TABLE IF NOT EXISTS credit_accounts (
    account_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    issuer TEXT NOT NULL,
    product_name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    status TEXT NOT NULL,
    opened_date TEXT NOT NULL,
    closed_date TEXT,
    credit_limit INTEGER NOT NULL DEFAULT 0,
    current_balance INTEGER NOT NULL DEFAULT 0,
    apr REAL NOT NULL DEFAULT 0,
    autopay_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    utilization REAL NOT NULL DEFAULT 0,
    payment_status TEXT NOT NULL DEFAULT 'on_time'
);

CREATE INDEX IF NOT EXISTS idx_credit_accounts_user_id ON credit_accounts(user_id);

CREATE TABLE IF NOT EXISTS loan_accounts (
    account_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    lender TEXT NOT NULL,
    product_name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    status TEXT NOT NULL,
    opened_date TEXT NOT NULL,
    original_balance INTEGER NOT NULL DEFAULT 0,
    current_balance INTEGER NOT NULL DEFAULT 0,
    monthly_payment INTEGER NOT NULL DEFAULT 0,
    interest_rate REAL NOT NULL DEFAULT 0,
    payment_status TEXT NOT NULL DEFAULT 'on_time'
);

CREATE INDEX IF NOT EXISTS idx_loan_accounts_user_id ON loan_accounts(user_id);

CREATE TABLE IF NOT EXISTS inquiries (
    inquiry_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    creditor TEXT NOT NULL,
    inquiry_type TEXT NOT NULL,
    inquiry_date TEXT NOT NULL,
    bureau TEXT NOT NULL,
    is_hard BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_inquiries_user_id ON inquiries(user_id);

CREATE TABLE IF NOT EXISTS payment_history (
    payment_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    account_id TEXT NOT NULL,
    month TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'on_time',
    amount_due INTEGER NOT NULL DEFAULT 0,
    amount_paid INTEGER NOT NULL DEFAULT 0,
    days_late INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_payment_history_user_id ON payment_history(user_id);

CREATE TABLE IF NOT EXISTS credit_metrics (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    score_band TEXT NOT NULL,
    score_change_30d INTEGER NOT NULL DEFAULT 0,
    revolving_limit_total INTEGER NOT NULL DEFAULT 0,
    revolving_balance_total INTEGER NOT NULL DEFAULT 0,
    revolving_utilization REAL NOT NULL DEFAULT 0,
    installment_balance_total INTEGER NOT NULL DEFAULT 0,
    installment_original_total INTEGER NOT NULL DEFAULT 0,
    installment_utilization REAL NOT NULL DEFAULT 0,
    open_revolving_accounts INTEGER NOT NULL DEFAULT 0,
    open_installment_accounts INTEGER NOT NULL DEFAULT 0,
    total_hard_inquiries_12m INTEGER NOT NULL DEFAULT 0,
    recent_hard_inquiries_90d INTEGER NOT NULL DEFAULT 0,
    on_time_payment_ratio REAL NOT NULL DEFAULT 0,
    delinquent_accounts INTEGER NOT NULL DEFAULT 0,
    months_since_last_delinquency INTEGER,
    total_available_credit INTEGER NOT NULL DEFAULT 0,
    trends JSONB NOT NULL DEFAULT '[]'::jsonb,
    key_drivers JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    priority TEXT NOT NULL,
    category TEXT NOT NULL,
    rationale TEXT NOT NULL,
    action TEXT NOT NULL,
    expected_impact TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_recommendations_user_id ON recommendations(user_id);
