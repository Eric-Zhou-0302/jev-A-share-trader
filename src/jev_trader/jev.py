from __future__ import annotations

import math
import time

import httpx

from .models import AnalysisError, Evidence

PROMPT_VERSION = "atomic-v1"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DIRECTIONAL = ("trend", "momentum", "volume", "structure", "candles", "multitimeframe", "relative")
HORIZONS = {"short": "2-5", "swing": "5-20"}


def questions(groups: list[str]) -> dict:
    result = {}
    for horizon, days in HORIZONS.items():
        for group in DIRECTIONAL:
            if group not in groups:
                continue
            result[f"{horizon}_{group}"] = {
                "type": "choice",
                "instructions": f"Using only the supplied completed-session state, classify the directional implication of the {group} evidence for the next {days} trading sessions. Evaluate this dimension only. Missing or conflicting evidence is neutral. Do not use external knowledge about this security, imagine later prices, or count repeated indicators as independent confirmation. This is an assessment of the technical state, not an empirically calibrated return forecast.",
                "criteria": {"bullish": "The supplied dimension supports upward continuation or recovery over this horizon.", "neutral": "The supplied dimension is mixed, non-directional, insufficient, or does not favor either direction.", "bearish": "The supplied dimension supports downward continuation or deterioration over this horizon."},
            }
        result[f"{horizon}_risk"] = {
            "type": "noul",
            "instructions": f"Using only the supplied volatility evidence, is volatility unusually elevated or unstable for interpreting the technical state over the next {days} trading sessions? Evaluate volatility risk, not price direction. Do not infer unavailable news or future prices.",
            "criteria": {"true": "Volatility is elevated versus this security's own recent history, or abrupt expansion weakens the stability of the technical interpretation.", "false": "Volatility is contained relative to this security's recent history; no clear instability is shown."},
        }
    return result


def validate_response(payload: dict, expected: dict) -> dict[str, dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict) or not isinstance(payload.get("model"), str):
        raise ValueError("missing answer envelope")
    validated = {}
    for name, question in expected.items():
        answer = payload["answers"].get(name)
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise ValueError("missing or mismatched answer")
        if question["type"] == "noul":
            probability = answer.get("noul")
            if isinstance(probability, bool) or not isinstance(probability, (float, int)) or not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("invalid noul")
            validated[name] = {"risk": float(probability)}
        else:
            distribution = answer.get("probabilities")
            if not isinstance(distribution, dict) or set(distribution) != set(question["criteria"]):
                raise ValueError("invalid choice space")
            if any(isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1 for value in distribution.values()):
                raise ValueError("invalid probability")
            if not math.isclose(sum(distribution.values()), 1, abs_tol=.001):
                raise ValueError("probabilities do not sum to one")
            choice = answer.get("choice")
            if choice not in distribution or distribution[choice] + .001 < max(distribution.values()):
                raise ValueError("choice is not a maximum")
            confidence = answer.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, (float, int)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("invalid confidence")
            validated[name] = {"direction": distribution["bullish"] - distribution["bearish"], "probabilities": distribution}
    return validated


class JevClient:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def evaluate(self, state: dict, groups: list[str]) -> tuple[dict, dict]:
        key = self.settings.jev_api_key.get_secret_value()
        if not key:
            raise AnalysisError("needs_key", "请配置自己的 Jev API key 后生成总判断。", "Configure your Jev API key to generate a decision.")
        expected = questions(groups)
        body = {"model": self.settings.model, "state": state, "questions": expected}
        try:
            client = httpx.Client(timeout=self.settings.request_timeout, transport=self.transport)
        except (ImportError, ValueError, OSError) as exc:
            # 初始化也会读取代理和证书配置；原异常可能含代理凭据，不回传给界面。
            raise AnalysisError("model_configuration", "Jev 网络客户端初始化失败，请检查项目依赖、代理及证书配置；技术分析已保留。", "Jev network client initialization failed. Check dependencies, proxy and certificate settings; technical analysis is preserved.") from exc
        with client:
            for attempt in range(3):
                try:
                    response = client.post(ENDPOINT, json=body, headers={"Authorization": f"Bearer {key}"})
                except httpx.HTTPError as exc:
                    raise AnalysisError("model_unavailable", "Jev 连接失败，保留技术分析但不形成总判断。", "Jev connection failed; technical evidence is available without a decision.") from exc
                if response.status_code in (429, 503, 529) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                if response.status_code in (401, 403):
                    raise AnalysisError("model_auth", "Jev 凭据或访问权限无效。", "Jev credentials or access permissions were rejected.")
                if response.status_code >= 400:
                    raise AnalysisError("model_unavailable", f"Jev 返回 HTTP {response.status_code}，未形成总判断。", f"Jev returned HTTP {response.status_code}; no decision was produced.")
                try:
                    payload = response.json()
                    result = validate_response(payload, expected)
                except (ValueError, TypeError) as exc:
                    raise AnalysisError("model_invalid", "Jev 响应未通过结构或概率校验。", "Jev response failed schema or probability validation.") from exc
                return result, {"model": payload["model"], "usage": payload.get("usage", {}), "answers": payload["answers"]}
        raise AnalysisError("model_unavailable", "Jev 暂不可用。", "Jev is unavailable.")


def aggregate(answers: dict, evidence: list[Evidence], settings) -> tuple[str, str, list[Evidence], dict]:
    details = {}
    for horizon in HORIZONS:
        weights = settings.weights[horizon]
        present = [(group, weight, answers[f"{horizon}_{group}"]["direction"]) for group, weight in weights.items() if f"{horizon}_{group}" in answers]
        denominator = sum(weight for _, weight, _ in present)
        if denominator <= 0:
            raise AnalysisError("invalid_weights", "有效分维权重总和必须大于零。", "Available dimension weights must sum to a positive value.")
        direction = sum(weight * value for _, weight, value in present) / denominator
        risk = answers[f"{horizon}_risk"]["risk"]
        score = direction * (1 - settings.risk_damping * risk)
        disagreement = sum(weight * abs(value - direction) for _, weight, value in present) / denominator
        details[horizon] = {"score": score, "direction": direction, "risk": risk, "conviction": abs(score) - .1 * disagreement, "dimensions": {group: value for group, _, value in present}}
    # 比较两个窗口的分维一致性，最终只返回一个窗口与一个判断；平局使用较长窗口。
    selected = max(("swing", "short"), key=lambda horizon: details[horizon]["conviction"])
    score = details[selected]["score"]
    action = "buy" if score >= settings.buy_threshold else "sell" if score <= settings.sell_threshold else "hold"
    polarity = 1 if action == "buy" else -1
    matching_groups = {item.group for item in evidence if item.polarity == polarity}
    if action != "hold" and len(matching_groups) < 2:
        action = "hold"
        details["guard"] = "insufficient_independent_support"
    output = []
    for item in evidence:
        if action == "hold":
            side = "oppose" if item.polarity != 0 and item.strength >= .8 else "context"
        else:
            side = "context" if item.polarity == 0 else "support" if item.polarity == (1 if action == "buy" else -1) else "oppose"
        output.append(item.model_copy(update={"side": side}))
    if action == "hold":
        output.insert(0, Evidence(id="aggregate_hold", group="summary", polarity=0, date=max(item.date for item in evidence),
            zh="分维判断汇总未达到方向阈值，或缺少至少两个维度的同向事实支持。",
            en="The aggregate did not reach a directional threshold, or lacked aligned factual support from at least two dimensions.", side="support"))
    return action, HORIZONS[selected], output, details
