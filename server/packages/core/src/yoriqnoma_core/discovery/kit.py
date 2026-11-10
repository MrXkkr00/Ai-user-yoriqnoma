"""The scout's browser kit, built from the same core pieces as the explorer.

One browser, one context per account (guest, the target role), every request through the
core firewall (SSRF host check, deny_paths, other domains, passive mode) and every JSON
answer through the privacy ledger (other people's data -> fakes) before the page sees it.
Screenshots for the Claude agent are taken with the core ``Capturer``, so they go through
the same replacement and OCR checks as the explorer's (TZ SEC-7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from yoriqnoma_core.explorer.capture import Capturer
from yoriqnoma_core.explorer.datagen import DataGen
from yoriqnoma_core.explorer.firewall import Firewall
from yoriqnoma_core.explorer.ocr import OcrEngine
from yoriqnoma_core.explorer.options import ExploreOptions
from yoriqnoma_core.explorer.pseudonymize import PrivacyLedger
from yoriqnoma_core.explorer.session import BrowserSession
from yoriqnoma_core.safety.policy_engine import PolicyEngine
from yoriqnoma_core.safety.url_guard import HostGuard
from yoriqnoma_schemas import BlockedRequest, Policy


@dataclass
class ScoutKit:
    opts: ExploreOptions
    run_dir: Path
    policy: Policy
    datagen: DataGen
    ledger: PrivacyLedger
    engine: PolicyEngine
    capturer: Capturer
    session: BrowserSession
    firewall_log: list[BlockedRequest] = field(default_factory=list)

    @classmethod
    def create(cls, opts: ExploreOptions, run_dir: Path, policy: Policy) -> ScoutKit:
        scout_dir = run_dir / "scout"
        scout_dir.mkdir(parents=True, exist_ok=True)
        datagen = DataGen(opts.seed, f"{opts.run_id}-scout", opts.pseudonym_key.get_secret_value())
        ledger = PrivacyLedger(
            datagen=datagen,
            base_url=opts.base_url,
            entities={},
            self_signup_roles=set(),
            org_domains=list(opts.org_domains),
        )
        engine = PolicyEngine(policy, opts.base_url, passive=opts.passive)
        capturer = Capturer(
            run_dir=scout_dir,
            ledger=ledger,
            forbidden_patterns=list(policy.deny_paths),
            max_height=opts.max_page_height,
            ocr=OcrEngine() if opts.ocr else None,
        )
        log: list[BlockedRequest] = []
        guard = HostGuard(allow_private=opts.allow_private)
        session = BrowserSession(
            opts, lambda: Firewall(engine, ledger, set(), log=log, guard=guard)
        )
        return cls(
            opts=opts,
            run_dir=scout_dir,
            policy=policy,
            datagen=datagen,
            ledger=ledger,
            engine=engine,
            capturer=capturer,
            session=session,
            firewall_log=log,
        )
