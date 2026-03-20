from __future__ import annotations

from typing import List

from synthetic.models import CreditMetrics, Recommendation, User


def build_recommendations(user: User, metrics: CreditMetrics) -> List[Recommendation]:
    recommendations: List[Recommendation] = []

    if metrics.revolving_utilization >= 0.5:
        recommendations.append(
            make_recommendation(
                user.user_id,
                1,
                "Reduce card balances below 30% utilization",
                "high",
                "utilization",
                "High utilization is one of the strongest negative signals in this file.",
                "Direct upcoming payments toward the highest-balance cards first and avoid new card spend until total utilization drops below 30%.",
                "Can improve score within one or two reporting cycles if balances fall materially.",
            )
        )
    elif metrics.revolving_utilization <= 0.1:
        recommendations.append(
            make_recommendation(
                user.user_id,
                1,
                "Keep balances low before statement close",
                "low",
                "utilization",
                "Current utilization is already a strength worth preserving.",
                "Continue paying down statement balances early so reported utilization stays in the single digits.",
                "Helps preserve excellent score stability.",
            )
        )

    if metrics.months_since_last_delinquency is not None and metrics.months_since_last_delinquency <= 6:
        recommendations.append(
            make_recommendation(
                user.user_id,
                2,
                "Protect the next six months of payments",
                "high",
                "payment_history",
                "Recent delinquency damage will fade only if new payments stay perfect.",
                "Turn on autopay for at least the minimum due and add calendar reminders for each account until the late mark ages.",
                "Prevents additional score damage and supports gradual recovery.",
            )
        )
    elif metrics.on_time_payment_ratio >= 0.99:
        recommendations.append(
            make_recommendation(
                user.user_id,
                2,
                "Maintain perfect payment history",
                "medium",
                "payment_history",
                "Payment consistency is helping this profile.",
                "Keep autopay enabled and monitor for any due-date changes after account servicing updates.",
                "Preserves the strongest scoring factor.",
            )
        )

    if metrics.total_hard_inquiries_12m >= 3:
        recommendations.append(
            make_recommendation(
                user.user_id,
                3,
                "Pause new credit applications",
                "high",
                "inquiries",
                "Multiple recent hard inquiries suggest aggressive credit seeking.",
                "Avoid applying for additional cards or loans for the next six months unless there is a real financing need.",
                "Allows recent inquiries to age and average account age to stabilize.",
            )
        )
    elif metrics.total_hard_inquiries_12m == 0:
        recommendations.append(
            make_recommendation(
                user.user_id,
                3,
                "Apply selectively only when it improves your mix",
                "low",
                "inquiries",
                "There is no inquiry pressure on this file right now.",
                "Keep future applications limited to products that materially improve rewards, limits, or credit mix.",
                "Maintains inquiry profile strength.",
            )
        )

    if metrics.open_revolving_accounts + metrics.open_installment_accounts <= 2:
        recommendations.append(
            make_recommendation(
                user.user_id,
                4,
                "Add depth slowly as the file matures",
                "medium",
                "credit_mix",
                "A thin file can cap score upside even when everything is paid on time.",
                "Let current accounts age first, then consider one additional no-fee revolving account only after six months of stable history.",
                "Can improve scoring depth without creating unnecessary inquiry pressure.",
            )
        )
    else:
        recommendations.append(
            make_recommendation(
                user.user_id,
                4,
                "Monitor credit reports monthly",
                "low",
                "monitoring",
                "Ongoing monitoring helps catch balance spikes, late marks, and inquiry errors early.",
                "Review all three bureau reports and track balances before statement dates each month.",
                "Improves control over score changes and dispute response time.",
            )
        )

    return recommendations


def make_recommendation(
    user_id: str,
    index: int,
    title: str,
    priority: str,
    category: str,
    rationale: str,
    action: str,
    expected_impact: str,
) -> Recommendation:
    return Recommendation(
        recommendation_id=f"rec_{user_id}_{index:02d}",
        user_id=user_id,
        title=title,
        priority=priority,
        category=category,
        rationale=rationale,
        action=action,
        expected_impact=expected_impact,
    )
