from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.credit import router as credit_router
from app.api.routes.users import router as users_router
from synthetic.seed_data import seed_data


def ensure_seed_data() -> None:
    data_dir = Path(__file__).resolve().parent / "data"
    required_files = [
        "users.json",
        "credit_reports.json",
        "credit_accounts.json",
        "loan_accounts.json",
        "inquiries.json",
        "payment_history.json",
        "credit_metrics.json",
        "recommendations.json",
    ]
    if not all((data_dir / file_name).exists() for file_name in required_files):
        seed_data()


ensure_seed_data()

app = FastAPI(title="Credit Assistant Backend", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(credit_router)
app.include_router(chat_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
