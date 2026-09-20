import copy
import json

import httpx
import pytest

from jev_trader.config import Settings
from jev_trader.jev import DIRECTIONAL, JevClient, aggregate, questions, validate_response
from jev_trader.models import AnalysisError, Evidence


def response_for(expected):
    return {"model": "jev-test-fixture", "answers": {
        name: {"type": "noul", "noul": .1} if value["type"] == "noul" else
        {"type": "choice", "choice": "bullish", "confidence": .8,
         "probabilities": {"bullish": .8, "neutral": .1, "bearish": .1}}
        for name, value in expected.items()}}


def test_payload_and_response_contract():
    expected = questions(["trend", "volume", "volatility"])
    assert len(expected) == 6

    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-only"
        payload = json.loads(request.content)
        assert payload["state"] == {"as_of": "2026-09-18"}
        assert payload["questions"] == expected
        return httpx.Response(200, json=response_for(expected))

    client = JevClient(Settings(jev_api_key="test-only"), transport=httpx.MockTransport(handler))
    answers, metadata = client.evaluate({"as_of": "2026-09-18"}, ["trend", "volume", "volatility"])
    assert answers["short_trend"]["direction"] == pytest.approx(.7)
    assert metadata["model"] == "jev-test-fixture"


@pytest.mark.parametrize("mutation", ["missing", "space", "sum", "nan", "boolean", "wrong_choice", "wrong_type", "confidence", "risk"])
def test_malformed_probabilities_fail_closed(mutation):
    expected = questions(["trend"])
    payload = response_for(expected)
    answer = payload["answers"]["short_trend"]
    if mutation == "missing":
        payload["answers"].pop("short_trend")
    elif mutation == "space":
        answer["probabilities"]["buy"] = 0
    elif mutation == "sum":
        answer["probabilities"]["bullish"] = .7
    elif mutation == "nan":
        answer["probabilities"]["bullish"] = float("nan")
    elif mutation == "boolean":
        answer["probabilities"]["bullish"] = True
    elif mutation == "wrong_choice":
        answer["choice"] = "bearish"
    elif mutation == "wrong_type":
        answer["type"] = "score"
    elif mutation == "confidence":
        answer["confidence"] = 2
    else:
        payload["answers"]["short_risk"]["noul"] = -1
    with pytest.raises(ValueError):
        validate_response(payload, expected)


@pytest.mark.parametrize("status,code", [(401, "model_auth"), (500, "model_unavailable"), (200, "model_invalid")])
def test_errors_do_not_become_neutral_decisions(status, code):
    client = JevClient(Settings(jev_api_key="test-only"), transport=httpx.MockTransport(lambda request: httpx.Response(status, json={})))
    with pytest.raises(AnalysisError) as exc:
        client.evaluate({}, ["trend"])
    assert exc.value.code == code


def test_no_key_never_makes_request():
    def unexpected(request):
        pytest.fail("No request should be made without a key")
    client = JevClient(Settings(), transport=httpx.MockTransport(unexpected))
    with pytest.raises(AnalysisError) as exc:
        client.evaluate({}, ["trend"])
    assert exc.value.code == "needs_key"


@pytest.mark.parametrize("scheme", ["socks5", "socks5h"])
def test_real_client_initializes_with_socks_environment(monkeypatch, scheme):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ALL_PROXY", f"{scheme}://127.0.0.1:1080")

    def post(client, url, **kwargs):
        # 保留真实网络客户端初始化，仅替换实际请求，避免测试访问代理或模型。
        return httpx.Response(200, json=response_for(kwargs["json"]["questions"]))

    monkeypatch.setattr(httpx.Client, "post", post)
    answers, _ = JevClient(Settings(jev_api_key="test-only")).evaluate({}, ["trend"])
    assert answers["short_trend"]["direction"] == pytest.approx(.7)


@pytest.mark.parametrize("failure", [ImportError, ValueError, OSError])
def test_client_initialization_errors_are_redacted(monkeypatch, failure):
    def broken_client(**kwargs):
        raise failure("socks5://user:secret-proxy-password@localhost:1080")

    monkeypatch.setattr(httpx, "Client", broken_client)
    with pytest.raises(AnalysisError) as exc:
        JevClient(Settings(jev_api_key="test-only")).evaluate({}, ["trend"])
    assert exc.value.code == "model_configuration"
    assert "secret-proxy-password" not in exc.value.en + exc.value.zh


def directional_answers(short, swing, risk=.1):
    return {**{f"{horizon}_{group}": {"direction": value} for horizon, value in (("short", short), ("swing", swing)) for group in DIRECTIONAL},
            "short_risk": {"risk": risk}, "swing_risk": {"risk": risk}}


def facts(polarity=1):
    return [Evidence(id=group, group=group, polarity=polarity, date="2026-09-18", zh="测试", en="Test") for group in ("trend", "volume")]


def test_one_horizon_and_evidence_both_sides():
    evidence = facts() + [Evidence(id="risk", group="momentum", polarity=-1, date="2026-09-18", zh="反对", en="Opposition")]
    action, horizon, output, details = aggregate(directional_answers(.8, .4), evidence, Settings())
    assert (action, horizon) == ("buy", "2-5")
    assert [item.side for item in output] == ["support", "support", "oppose"]


def test_volatility_damps_conviction_without_forcing_sell():
    low_risk = aggregate(directional_answers(.5, .5, 0), facts(), Settings())
    high_risk = aggregate(directional_answers(.5, .5, 1), facts(), Settings())
    assert low_risk[0] == "buy" and high_risk[0] == "hold"
    assert high_risk[3]["swing"]["score"] == pytest.approx(.25)


def test_neutral_buy_sell_and_support_guard():
    assert aggregate(directional_answers(-.8, -.7), facts(-1), Settings())[0] == "sell"
    assert aggregate(directional_answers(0, 0), facts(), Settings())[0:2] == ("hold", "5-20")
    result = aggregate(directional_answers(.9, .9), facts()[:1], Settings())
    assert result[0] == "hold" and result[3]["guard"] == "insufficient_independent_support"


def test_weight_validation_and_instance_isolation():
    defaults = Settings()
    modified = Settings()
    modified.weights["short"]["trend"] = 10
    assert defaults.weights["short"]["trend"] == .2
    for value in (float("nan"), -1):
        weights = copy.deepcopy(defaults.weights)
        weights["short"]["trend"] = value
        with pytest.raises(ValueError):
            Settings(weights=weights)
