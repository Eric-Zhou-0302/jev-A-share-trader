from __future__ import annotations

import json
import math
import os
from copy import deepcopy
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator

DEFAULT_WEIGHTS = {
    "short": {"trend": .20, "momentum": .20, "volume": .16, "structure": .18, "candles": .10, "multitimeframe": .06, "relative": .10},
    "swing": {"trend": .28, "momentum": .12, "volume": .13, "structure": .14, "candles": .04, "multitimeframe": .19, "relative": .10},
}


class Settings(BaseModel):
    provider: str = "akshare"
    provider_options: dict = Field(default_factory=dict)
    jev_api_key: SecretStr = SecretStr("")
    tushare_token: SecretStr = SecretStr("")
    model: str = "jev-latest"
    source_order: list[str] = Field(default_factory=lambda: ["eastmoney", "tencent"])
    request_timeout: int = Field(default=25, ge=5, le=120)
    request_interval: float = Field(default=.3, ge=.1, le=10)
    history_years: int = Field(default=10, ge=3, le=25)
    min_bars: int = Field(default=260, ge=120, le=1250)
    min_amount: float = Field(default=0, ge=0)
    exclude_special: bool = True
    markets: list[Literal["SH", "SZ", "BJ"]] = Field(default_factory=lambda: ["SH", "SZ", "BJ"], min_length=1)
    buy_threshold: float = Field(default=.30, ge=.05, le=.9)
    sell_threshold: float = Field(default=-.30, ge=-.9, le=-.05)
    risk_damping: float = Field(default=.50, ge=0, le=1)
    weights: dict[str, dict[str, float]] = Field(default_factory=lambda: deepcopy(DEFAULT_WEIGHTS))
    language: Literal["zh", "en"] = "zh"

    @field_validator("weights")
    @classmethod
    def valid_weights(cls, value):
        if set(value) != set(DEFAULT_WEIGHTS):
            raise ValueError("Weights require short and swing horizons.")
        for horizon, weights in value.items():
            if set(weights) != set(DEFAULT_WEIGHTS[horizon]):
                raise ValueError("Weights must cover all seven directional dimensions.")
            if any(not math.isfinite(weight) or weight < 0 for weight in weights.values()) or not math.isfinite(sum(weights.values())) or sum(weights.values()) <= 0:
                raise ValueError("Weights must be finite, nonnegative and have a positive sum.")
        return value


def data_directory() -> Path:
    directory = Path(os.environ.get("JEV_DATA_DIR", "~/.local/share/jev-a-share-trader")).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load_settings(directory: Path) -> Settings:
    file = directory / "settings.json"
    raw = json.loads(file.read_text()) if file.exists() else {}
    if os.environ.get("TYPESAFE_API_KEY"):
        raw["jev_api_key"] = os.environ["TYPESAFE_API_KEY"]
    if os.environ.get("TUSHARE_TOKEN"):
        raw["tushare_token"] = os.environ["TUSHARE_TOKEN"]
    return Settings.model_validate(raw)


def save_settings(directory: Path, settings: Settings) -> None:
    raw = settings.model_dump(mode="json")
    raw["jev_api_key"] = settings.jev_api_key.get_secret_value()
    raw["tushare_token"] = settings.tushare_token.get_secret_value()
    target = directory / "settings.json"
    temp = target.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(raw, handle, ensure_ascii=False, indent=2)
    temp.replace(target)


def public_settings(settings: Settings) -> dict:
    result = settings.model_dump(exclude={"jev_api_key", "tushare_token", "provider_options"})
    result["jev_configured"] = bool(settings.jev_api_key.get_secret_value())
    result["tushare_configured"] = bool(settings.tushare_token.get_secret_value())
    return result
