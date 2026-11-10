"""Mode B on the server: build a blueprint from the site itself (ARCHITECTURE §7.6).

The discovery itself is shared with the local app (``yoriqnoma_core.discovery``). The
server adds what is its own: preflight (robots.txt, sitemap) and the site's JS files
through ``safe_get`` (SSRF checks, DNS pinning), the per-domain rate limit in Redis and
Claude for form classification and the agent, with its share of the job budget.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from pydantic import SecretStr

from jobs.models import Job
from jobs.pipeline import JobFailed, explore_options
from scout.preflight import Preflight, preflight
from security.ratelimit import wait_turn
from security.robots import deny_globs
from security.ssrf import safe_get
from yoriqnoma_core.discovery.kit import ScoutKit
from yoriqnoma_core.discovery.run import DiscoveryFailed, DiscoveryInput, discover_site
from yoriqnoma_core.explorer.options import CancelToken, HumanInput, ProgressSink
from yoriqnoma_core.writer.providers.base import LLMProvider
from yoriqnoma_core.writer.providers.claude import ClaudeProvider, make_sanitizer, prices_from
from yoriqnoma_schemas import Blueprint, Policy
from yoriqnoma_schemas.policy import DEFAULT_DENY_PATHS


class ScoutFailed(JobFailed):
    """Mode B cannot go on; the reason is shown to the user."""


def claude_for_scout(job: Job, kit: ScoutKit, progress: ProgressSink) -> LLMProvider | None:
    """Claude for the agent and form classification, with its own share of the budget."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None
    share = float(job.budget_usd) * float(settings.YORIQNOMA_SCOUT_AGENT_SHARE)
    return ClaudeProvider(
        api_key=SecretStr(key),
        models=dict(settings.YORIQNOMA_MODELS),
        prices=prices_from(settings.YORIQNOMA_PRICES),
        budget_usd=share,
        on_cost=lambda payload: progress.event(str(payload.get("kind", "cost")), payload),
        sanitize=lambda text: make_sanitizer(kit.ledger.ignore())(text),
        image_roots=[kit.run_dir / "capture"],
    )


# Replaced in tests (no Claude in unit tests).
provider_factory: Any = claude_for_scout


def fetch_text(url: str) -> str | None:
    """A file of the site through the SSRF-checked client (JS bundles, source maps)."""
    try:
        answer = safe_get(url, max_bytes=16 * 1024 * 1024)
    except Exception:  # noqa: BLE001 - a file that cannot be read is skipped
        return None
    return answer.text if answer.status == 200 else None


async def discover(
    job: Job,
    run_dir: Path,
    human: HumanInput,
    progress: ProgressSink,
    cancel: CancelToken,
    base: Blueprint | None = None,
) -> Blueprint:
    opts = explore_options(job)
    progress.stage("scout", int(settings.YORIQNOMA_SCOUT_MAX_PAGES) * 2)
    pre: Preflight = await asyncio.to_thread(preflight, job.url, not job.passive)
    progress.log(
        "info",
        f"preflight: til «{pre.lang or '-'}», texnologiya: {', '.join(pre.tech) or '-'}, "
        f"sitemap'da {len(pre.sitemap_urls)} ta sahifa",
    )
    extra_deny = deny_globs(pre.robots) if job.passive else []
    policy = Policy(
        target_role=job.role, deny_paths=sorted(set(DEFAULT_DENY_PATHS) | set(extra_deny))
    )
    kit = ScoutKit.create(opts, run_dir, policy)
    provider = None if job.passive else provider_factory(job, kit, progress)
    if provider is None and not job.passive:
        progress.log("info", "razvedka: Claude kaliti yo'q, agent ishlatilmaydi")
    inp = DiscoveryInput(
        base_url=job.url,
        role=job.role,
        role_label=job.role_label or job.role,
        project=base.project if base else (urlsplit(job.url).hostname or "site"),
        accounts=opts.accounts.get(job.role, {}),
        passive=job.passive,
        allowed=pre.robots.allowed,
        sitemap_urls=pre.sitemap_urls,
        fetch_text=fetch_text,
        wait=wait_turn,
        classify=provider,
        agent=provider,
        max_pages=int(settings.YORIQNOMA_SCOUT_MAX_PAGES),
        agent_steps=int(settings.YORIQNOMA_SCOUT_AGENT_STEPS),
        extra_deny=extra_deny,
        generator=f"yoriqnoma-scout {settings.YORIQNOMA_VERSION}",
    )
    try:
        return await discover_site(kit, inp, human, progress, cancel)
    except DiscoveryFailed as exc:
        raise ScoutFailed(str(exc)) from exc
