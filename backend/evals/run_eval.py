"""
RAG Evaluation using Ragas.

Evaluates retrieval quality and LLM response quality against ground truth.

Usage:
  PYTHONPATH=backend python3 backend/evals/run_eval.py
  PYTHONPATH=backend python3 backend/evals/run_eval.py --api http://localhost:8080
  PYTHONPATH=backend python3 backend/evals/run_eval.py --api https://credit-assistant.fly.dev
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx


def load_test_cases(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def collect_via_api(base_url: str, test_cases: list[dict]) -> list[dict]:
    """Collect answers + retrieved contexts by hitting the chat API."""
    results = []
    client = httpx.Client(base_url=base_url, timeout=60.0)

    for i, case in enumerate(test_cases, 1):
        print(f"[{i}/{len(test_cases)}] {case['question'][:60]}...", flush=True)
        t0 = time.perf_counter()

        response = client.post("/chat", json={
            "user_id": case["user_id"],
            "message": case["question"],
            "stream": False,
        })
        elapsed = time.perf_counter() - t0

        if response.status_code != 200:
            print(f"  ERROR: {response.status_code} — {response.text[:200]}", flush=True)
            results.append({
                "question": case["question"],
                "answer": "",
                "contexts": [],
                "ground_truth": case["ground_truth"],
                "latency_ms": int(elapsed * 1000),
                "error": response.text[:200],
            })
            continue

        data = response.json()
        answer = data.get("message", "")

        # Extract retrieval context from explanation evidence if available
        contexts = []
        explanation = data.get("explanation")
        if explanation and explanation.get("evidence"):
            contexts = explanation["evidence"]

        print(f"  OK  {int(elapsed * 1000)}ms  answer={len(answer)} chars  contexts={len(contexts)}", flush=True)
        results.append({
            "question": case["question"],
            "answer": answer,
            "contexts": contexts,
            "ground_truth": case["ground_truth"],
            "latency_ms": int(elapsed * 1000),
        })

    client.close()
    return results


def collect_via_local(test_cases: list[dict]) -> list[dict]:
    """Collect answers + retrieved contexts by calling services directly."""
    from app.core.dependencies import get_chat_orchestrator

    orchestrator = get_chat_orchestrator()
    results = []

    for i, case in enumerate(test_cases, 1):
        print(f"[{i}/{len(test_cases)}] {case['question'][:60]}...", flush=True)
        t0 = time.perf_counter()

        chat_response = orchestrator.respond(
            user_id=case["user_id"],
            message=case["question"],
        )
        elapsed = time.perf_counter() - t0

        answer = chat_response.message
        contexts = []
        if chat_response.explanation and chat_response.explanation.evidence:
            contexts = chat_response.explanation.evidence

        print(f"  OK  {int(elapsed * 1000)}ms  answer={len(answer)} chars  contexts={len(contexts)}", flush=True)
        results.append({
            "question": case["question"],
            "answer": answer,
            "contexts": contexts,
            "ground_truth": case["ground_truth"],
            "latency_ms": int(elapsed * 1000),
        })

    return results


def run_ragas_eval(results: list[dict]) -> dict:
    """Run Ragas evaluation on collected results. Requires Python 3.10+ and ragas package."""
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError as exc:
        print(f"Cannot import ragas: {exc}")
        print("Install with: pip install ragas datasets (requires Python 3.10+)")
        return {}

    # Filter out errored results
    valid = [r for r in results if r.get("answer")]
    if not valid:
        print("No valid results to evaluate.")
        return {}

    dataset = Dataset.from_dict({
        "question": [r["question"] for r in valid],
        "answer": [r["answer"] for r in valid],
        "contexts": [r["contexts"] if r["contexts"] else ["No context retrieved."] for r in valid],
        "ground_truth": [r["ground_truth"] for r in valid],
    })

    print(f"\nRunning Ragas evaluation on {len(valid)} samples...\n", flush=True)

    result = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
    )

    return result


def print_summary(results: list[dict], ragas_result) -> None:
    """Print evaluation summary."""
    valid = [r for r in results if r.get("answer")]
    errors = [r for r in results if not r.get("answer")]

    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)

    # Latency stats
    latencies = [r["latency_ms"] for r in valid]
    if latencies:
        print(f"\nLatency:")
        print(f"  Total requests:  {len(results)}")
        print(f"  Successful:      {len(valid)}")
        print(f"  Errors:          {len(errors)}")
        print(f"  Avg latency:     {sum(latencies) // len(latencies)}ms")
        print(f"  Min latency:     {min(latencies)}ms")
        print(f"  Max latency:     {max(latencies)}ms")
        print(f"  P50 latency:     {sorted(latencies)[len(latencies) // 2]}ms")

    # Ragas scores
    if ragas_result:
        print(f"\nRAG Quality Scores (Ragas):")
        for metric, score in ragas_result.items():
            if isinstance(score, (int, float)):
                bar = "#" * int(score * 20)
                print(f"  {metric:25s} {score:.4f}  [{bar:<20s}]")

    # Per-question breakdown
    print(f"\nPer-Question Results:")
    print(f"{'#':>3s}  {'Latency':>8s}  {'Contexts':>8s}  {'Question'}")
    print("-" * 70)
    for i, r in enumerate(results, 1):
        status = "OK" if r.get("answer") else "ERR"
        ctx_count = len(r.get("contexts", []))
        print(f"{i:3d}  {r['latency_ms']:>6d}ms  {ctx_count:>8d}  {r['question'][:45]}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Run RAG evaluation")
    parser.add_argument("--api", type=str, default=None, help="Base URL of the API (e.g., http://localhost:8080)")
    parser.add_argument("--test-cases", type=str, default=None, help="Path to test cases JSON")
    parser.add_argument("--output", type=str, default=None, help="Path to save raw results JSON")
    parser.add_argument("--skip-ragas", action="store_true", help="Skip Ragas evaluation, only collect results")
    args = parser.parse_args()

    test_cases_path = Path(args.test_cases) if args.test_cases else Path(__file__).parent / "test_cases.json"
    test_cases = load_test_cases(test_cases_path)
    print(f"Loaded {len(test_cases)} test cases from {test_cases_path}\n")

    # Collect results
    if args.api:
        print(f"Collecting via API: {args.api}\n")
        results = collect_via_api(args.api, test_cases)
    else:
        print("Collecting via local services\n")
        results = collect_via_local(test_cases)

    # Save raw results
    output_path = Path(args.output) if args.output else Path(__file__).parent / "results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nRaw results saved to {output_path}")

    # Run Ragas evaluation
    if args.skip_ragas:
        print("\nSkipping Ragas evaluation (--skip-ragas)")
        print_summary(results, None)
    else:
        try:
            ragas_result = run_ragas_eval(results)
            print_summary(results, ragas_result)
        except Exception as exc:
            print(f"\nRagas evaluation failed: {exc}")
            print("Try running with --skip-ragas or upgrade to Python 3.10+")
            print_summary(results, None)


if __name__ == "__main__":
    main()
