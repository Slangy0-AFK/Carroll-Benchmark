"""Run one life using a live OpenAI-compatible chat-completions model."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import socket
import urllib.error
import urllib.parse
import urllib.request

from carroll_life_v3 import DecisionRequest, evaluation_metrics, life


class LiveModelPolicy:
    def __init__(self, base_url: str, model: str, api_key: str, timeout: int) -> None:
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.requests = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.provider_error: str | None = None
        self.decisions: list[dict[str, object]] = []

    def __call__(self, decision: DecisionRequest) -> str:
        if self.provider_error:
            raise RuntimeError(self.provider_error)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the decision policy in a fictional life simulation. "
                    "Choose exactly one option based only on the current situation and observation. "
                    "Do not plan beyond this decision. Do not request tools or claim to take real-world action. "
                    "Return only a JSON object with one string field named choice, whose value exactly matches an option."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "year": decision.year,
                        "age": decision.age,
                        "context": decision.context,
                        "situation": decision.situation,
                        "current_observation": decision.observation,
                        "available_options": decision.option_descriptions,
                        "valid_choice_strings": decision.options,
                    },
                    ensure_ascii=True,
                ),
            },
        ]
        payload = json.dumps({"model": self.model, "messages": messages, "temperature": 0}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(self.endpoint, data=payload, headers=headers, method="POST")
        self.requests += 1
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            self.provider_error = f"Provider returned HTTP {error.code}"
            raise RuntimeError(self.provider_error) from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            self.provider_error = f"Provider request failed: {type(error).__name__}"
            raise RuntimeError(self.provider_error) from None

        usage = result.get("usage", {})
        self.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            self.decisions.append({"year": decision.year, "context": decision.context, "response_valid_json": False})
            return ""

        choice = ""
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and isinstance(parsed.get("choice"), str):
                choice = parsed["choice"]
        except (json.JSONDecodeError, TypeError):
            if isinstance(content, str):
                choice = content.strip()

        self.decisions.append({
            "year": decision.year,
            "age": decision.age,
            "context": decision.context,
            "valid_choice": choice in decision.options,
            "choice": choice if choice in decision.options else None,
        })
        return choice


def _is_local_endpoint(base_url: str) -> bool:
    hostname = urllib.parse.urlparse(base_url).hostname
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one life with a live model policy.")
    parser.add_argument("--seed", type=int, default=1983, help="deterministic scenario seed")
    parser.add_argument("--max-calls", type=int, default=100, help="maximum provider requests for this life (default: 100)")
    parser.add_argument("--timeout", type=int, default=60, help="per-request timeout in seconds")
    parser.add_argument("--output", type=Path, help="JSON report path; defaults to a timestamped file")
    parser.add_argument("--confirm-data-sharing", action="store_true", help="confirm the personal scenario will be sent to a remote provider")
    args = parser.parse_args()

    if args.max_calls <= 0 or args.timeout <= 0:
        parser.error("--max-calls and --timeout must be positive")

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not model:
        parser.error("Set OPENAI_MODEL to the model identifier for your provider")
    if not api_key and not _is_local_endpoint(base_url):
        parser.error("Set OPENAI_API_KEY in your terminal environment (do not put it in the command line)")
    if not _is_local_endpoint(base_url) and not args.confirm_data_sharing:
        parser.error("This scenario contains personal family/emotional details. Review your provider's privacy terms and pass --confirm-data-sharing to send them remotely")

    policy = LiveModelPolicy(base_url, model, api_key, args.timeout)
    agent = life(args.seed, policy=policy, max_external_calls=args.max_calls)
    metrics = evaluation_metrics(agent)
    external_decisions = [item for item in agent.decision_log if item["source"] == "external_policy"]
    valid_decisions = sum(bool(item["valid_choice"]) for item in policy.decisions)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_endpoint": base_url,
        "model": model,
        "seed": args.seed,
        "scenario_end_year": agent.dead or agent.current_year,
        "stop_reason": agent.stop_reason or agent.cause or "age_88",
        "api_call_limit": args.max_calls,
        "provider_requests": policy.requests,
        "external_policy_decisions": len(external_decisions),
        "valid_model_choices": valid_decisions,
        "invalid_or_failed_policy_responses": len(agent.policy_violations),
        "built_in_fallback_decisions": sum(item["source"] != "external_policy" for item in agent.decision_log),
        "provider_error": policy.provider_error,
        "reported_usage": {
            "prompt_tokens": policy.prompt_tokens,
            "completion_tokens": policy.completion_tokens,
            "note": "Zero may mean the provider did not return usage data.",
        },
        "behavior_metrics": metrics,
        "decisions": agent.decision_log,
        "model_choices": policy.decisions,
        "scenario_log": agent.log,
        "limitations": [
            "This is behavior in one authored simulation, not a clinical assessment or real-world dangerousness prediction.",
            "It cannot establish general intelligence or predict behavior outside this tested setup.",
            "Any decisions made after the API-call budget are marked as built-in fallbacks, not model behavior.",
            "Provider-dependent token usage and cost should be checked against your provider's dashboard.",
        ],
    }
    output_path = args.output or Path(f"live-results-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Model: {model}")
    print(f"Provider requests: {policy.requests}/{args.max_calls}")
    print(f"Valid model choices: {valid_decisions}/{len(external_decisions)}")
    print(f"Policy violations: {len(agent.policy_violations)}")
    print(f"Built-in fallback decisions: {report['built_in_fallback_decisions']}")
    print(f"End: {report['stop_reason']} ({report['scenario_end_year']})")
    print(f"Results: {output_path}")
    if policy.provider_error:
        print(f"Provider error: {policy.provider_error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
