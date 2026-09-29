"""Explicit selection; a configured URL alone never enables an external Judge."""
from fastapi import HTTPException

from app.config import settings
from app.providers.judge_provider import JudgeProvider, Verdict
from app.providers.mock_judge_provider import MockJudgeProvider


def validate_judge_configuration():
    if settings.JUDGE_PROVIDER == "mock" and settings.APP_ENV not in {"development", "test"}:
        raise RuntimeError("Mock Judge is development/test only; production must not use mock")


def get_judge_provider() -> JudgeProvider:
    validate_judge_configuration()
    if settings.JUDGE_PROVIDER == "mock":
        return MockJudgeProvider(Verdict(settings.JUDGE_MOCK_VERDICT), settings.JUDGE_MOCK_DELAY_SECONDS)
    if settings.JUDGE_PROVIDER == "judge0" and settings.JUDGE0_URL:
        from app.providers.judge0_provider import Judge0Provider
        return Judge0Provider(settings)
    raise HTTPException(503, "Judge 尚未啟用；開發環境可設定 APP_ENV=development、JUDGE_PROVIDER=mock")
