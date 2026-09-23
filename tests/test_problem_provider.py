import pytest
from app.providers.problem_provider import CpeProblemProvider, ProblemData


@pytest.mark.asyncio
async def test_cpe_provider_load_dataset():
    provider = CpeProblemProvider()
    assert len(provider._dataset) > 0

    prob = await provider.get_problem(100)
    assert prob is not None
    assert prob.problem_number == 100
    assert prob.title == "The 3n + 1 problem"
    assert prob.difficulty == "⭐"
    assert prob.uhunt_pid == 36
    assert "100.pdf" in prob.external_url


@pytest.mark.asyncio
async def test_cpe_provider_filter_difficulty():
    provider = CpeProblemProvider()
    one_star = await provider.get_problems(difficulty="⭐")
    assert len(one_star) > 0
    for p in one_star:
        assert p.difficulty == "⭐"

    two_star = await provider.get_problems(difficulty="⭐⭐")
    assert len(two_star) > 0
    for p in two_star:
        assert p.difficulty == "⭐⭐"


@pytest.mark.asyncio
async def test_cpe_provider_random_problem():
    provider = CpeProblemProvider()
    rand_prob = await provider.get_random_problem(difficulty="⭐")
    assert rand_prob is not None
    assert rand_prob.difficulty == "⭐"
