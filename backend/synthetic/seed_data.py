from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, List

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from synthetic.generators import (
    generate_credit_accounts,
    generate_credit_reports,
    generate_inquiries,
    generate_loan_accounts,
    generate_payment_history,
    generate_users,
)
from synthetic.metrics import compute_credit_metrics
from synthetic.recommendations import build_recommendations


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def write_json_file(file_name: str, rows: Iterable[object]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = [model_to_dict(row) for row in rows]
    with (DATA_DIR / file_name).open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def seed_data() -> None:
    users = generate_users()
    credit_accounts = generate_credit_accounts()
    loan_accounts = generate_loan_accounts()
    inquiries = generate_inquiries()
    payment_history = generate_payment_history(credit_accounts, loan_accounts)
    credit_reports = generate_credit_reports(users, credit_accounts, loan_accounts, inquiries, payment_history)

    metrics = []
    recommendations = []
    for user in users:
        report = next(item for item in credit_reports if item.user_id == user.user_id)
        user_credit_accounts = [item for item in credit_accounts if item.user_id == user.user_id]
        user_loan_accounts = [item for item in loan_accounts if item.user_id == user.user_id]
        user_inquiries = [item for item in inquiries if item.user_id == user.user_id]
        user_payments = [item for item in payment_history if item.user_id == user.user_id]
        metric = compute_credit_metrics(report, user_credit_accounts, user_loan_accounts, user_inquiries, user_payments)
        metrics.append(metric)
        recommendations.extend(build_recommendations(user, metric))

    write_json_file("users.json", users)
    write_json_file("credit_reports.json", credit_reports)
    write_json_file("credit_accounts.json", credit_accounts)
    write_json_file("loan_accounts.json", loan_accounts)
    write_json_file("inquiries.json", inquiries)
    write_json_file("payment_history.json", payment_history)
    write_json_file("credit_metrics.json", metrics)
    write_json_file("recommendations.json", recommendations)


if __name__ == "__main__":
    seed_data()
