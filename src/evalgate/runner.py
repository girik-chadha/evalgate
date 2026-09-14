import time
from collections.abc import Mapping
from datetime import UTC, datetime

import anyio

from evalgate.loader import SuiteError, render_prompt
from evalgate.models import CaseResult, RunReport, Suite, TestCase
from evalgate.providers.base import Provider, ProviderError
from evalgate.scorers.base import Scorer


async def run_suite(
    suite: Suite,
    templates: Mapping[str, str],
    provider: Provider,
    scorers: Mapping[str, Scorer],
    *,
    concurrency: int = 4,
    retries: int = 2,
    backoff_s: float = 0.5,
) -> RunReport:
    needed = {a.type for case in suite.cases for a in case.assertions}
    missing = needed - set(scorers)
    if missing:
        raise SuiteError(f"no scorer for assertion type: {', '.join(sorted(missing))}")

    started_at = datetime.now(UTC)
    run_start = time.perf_counter()
    semaphore = anyio.Semaphore(concurrency)
    results: dict[str, CaseResult] = {}

    async def run_one(case: TestCase) -> None:
        prompt = render_prompt(templates[case.prompt_template], case.input)
        async with semaphore:
            call_start = time.perf_counter()
            try:
                output = await _complete_with_retries(
                    provider, prompt, retries, backoff_s
                )
            except ProviderError as e:
                results[case.id] = CaseResult(
                    case_id=case.id,
                    output=None,
                    scores=[],
                    latency_ms=_elapsed_ms(call_start),
                    error=str(e),
                )
                return
            latency_ms = _elapsed_ms(call_start)
        scores = [await scorers[a.type].score(output, a) for a in case.assertions]
        results[case.id] = CaseResult(
            case_id=case.id, output=output, scores=scores, latency_ms=latency_ms
        )

    async with anyio.create_task_group() as tg:
        for case in suite.cases:
            tg.start_soon(run_one, case)

    return RunReport(
        suite=suite.name,
        model=provider.model,
        started_at=started_at,
        duration_ms=_elapsed_ms(run_start),
        results=[results[case.id] for case in suite.cases],
    )


async def _complete_with_retries(
    provider: Provider, prompt: str, retries: int, backoff_s: float
) -> str:
    for attempt in range(retries):
        try:
            return await provider.complete(prompt)
        except ProviderError:
            await anyio.sleep(backoff_s * 2**attempt)
    return await provider.complete(prompt)


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000
