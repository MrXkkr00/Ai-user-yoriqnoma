"""Explorer runner (TZ FR-E2..E12, SEC-5, SEC-6; ARCHITECTURE §4.3 "Runner tartibi").

1. accounts for the target role (and helper roles that prepare objects);
2. privilege check after every login;
3. flows in topological order: the target role's flows are captured, helper flows only
   prepare objects (a manager ships an order a test customer created and paid);
4. state graph (tabs, expanders, a foreign record's detail page) and patched statuses;
5. capture.json. Progress is saved after every flow, so a stopped run resumes.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import re
import time
from collections.abc import Awaitable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Response

from yoriqnoma_core.explorer import js
from yoriqnoma_core.explorer.accounts import AccountManager, AccountMissing
from yoriqnoma_core.explorer.capture import Capturer, normalize_for_hash
from yoriqnoma_core.explorer.datagen import DataGen, Identity
from yoriqnoma_core.explorer.firewall import Firewall, StatusPatch
from yoriqnoma_core.explorer.mailbox import Mailbox, make_mailbox
from yoriqnoma_core.explorer.ocr import OcrEngine
from yoriqnoma_core.explorer.options import (
    Cancelled,
    CancelToken,
    ExploreOptions,
    HumanInput,
    ProgressSink,
)
from yoriqnoma_core.explorer.privilege import PrivilegedAccountError, privilege_check
from yoriqnoma_core.explorer.pseudonymize import PrivacyLedger, ugc_text_headers
from yoriqnoma_core.explorer.session import AccountContext, BrowserSession, path_template
from yoriqnoma_core.explorer.steps import (
    StepContext,
    StepExecutor,
    StepFailed,
    StoppedAtConfirm,
    describe_step,
)
from yoriqnoma_core.safety.policy_engine import ClickContext, PolicyEngine
from yoriqnoma_core.safety.url_guard import HostGuard, check_url, same_origin
from yoriqnoma_schemas import (
    BlockedRequest,
    Blueprint,
    CaptureRun,
    Flow,
    FlowResult,
    State,
    load_json,
    save_json,
)

INTERACTIVE = {"click", "fill", "select", "check", "upload", "verify_email"}
PAGE_CHANGING = {"goto", "click", "verify_email"}
ACCOUNT_ACTIONS = {"register", "login"}
# steps a passive run may take (TZ SEC-9): reading and following links, nothing typed
PASSIVE_ACTIONS = {"goto", "click", "expect_url", "expect_text", "expect_visible", "wait_for"}


def passive_safe(flow: Flow) -> bool:
    """A guest flow that only reads: no form, no confirmation, no payment."""
    return flow.role == "guest" and all(
        s.action in PASSIVE_ACTIONS and not (s.confirm or s.destructive or s.payment)
        for s in flow.steps
    )


class RunAborted(Exception):
    """The run cannot continue (missing account, privileged account, wrong role)."""


def glob_to_regex(pattern: str) -> str:
    return fnmatch.translate(re.sub(r":[^/]+", "*", pattern)).replace(r"\Z", "$")


class Runner:
    def __init__(
        self,
        blueprint: Blueprint,
        run_dir: Path,
        opts: ExploreOptions,
        human: HumanInput,
        progress: ProgressSink,
        cancel: CancelToken,
    ) -> None:
        check_url(opts.base_url, allow_private=opts.allow_private)
        role = blueprint.role(opts.role)
        if role is None or role.kind != "role":
            raise RunAborted(
                f"«{opts.role}» rolini tanlab bo'lmaydi (yo'q yoki chiqarib tashlangan)"
            )
        self.bp = blueprint
        self.run_dir = run_dir
        self.opts = opts
        self.human = human
        self.progress = progress
        self.cancel = cancel
        self.role = opts.role
        self.run_id = opts.run_id or run_dir.name
        policy = blueprint.policy.model_copy(
            update={"target_role": opts.role, "environment": opts.environment}
        )
        self.policy = policy
        self.engine = PolicyEngine(
            policy, opts.base_url, passive=opts.passive, trusted_hosts=tuple(opts.trusted_hosts)
        )
        self.passive = opts.passive
        self.datagen = DataGen(
            opts.seed,
            self.run_id,
            opts.pseudonym_key.get_secret_value(),
            scope=opts.pseudonym_scope,
        )
        self.accounts = AccountManager(blueprint, opts, self.datagen)
        self.ledger = PrivacyLedger(
            datagen=self.datagen,
            base_url=opts.base_url,
            entities={e.name: e for e in blueprint.entities},
            self_signup_roles={r.id for r in blueprint.roles if r.self_signup},
            org_domains=list(opts.org_domains),
            editorial_is_ugc=False,
            ugc_headers=ugc_text_headers(blueprint),
        )
        self.mailbox: Mailbox | None = (
            make_mailbox(opts.mailbox_kind, opts.mailbox_target) if opts.mailbox_target else None
        )
        self.capturer = Capturer(
            run_dir=run_dir,
            ledger=self.ledger,
            forbidden_patterns=self._forbidden_patterns(),
            max_height=opts.max_page_height,
            ocr=OcrEngine() if opts.ocr else None,
        )
        collections = {
            e.name + "s" if not e.name.endswith("y") else e.name[:-1] + "ies"
            for e in blueprint.entities
        }
        self.firewall_log: list[BlockedRequest] = []
        guard = HostGuard(allow_private=opts.allow_private)  # shared DNS cache (SEC-10)
        self.session = BrowserSession(
            opts,
            lambda: Firewall(
                self.engine, self.ledger, collections, log=self.firewall_log, guard=guard
            ),
        )
        self.results: dict[str, FlowResult] = {}
        self.object_status: dict[str, dict[str, str]] = {}
        self.privilege_checked: set[str] = set()
        self.notes: list[str] = []
        self.started_at = datetime.now(UTC)
        self.target_ids: set[str] = set()

    # --- setup --------------------------------------------------------------------

    def _forbidden_patterns(self) -> list[str]:
        """Paths the target role must not see: excluded routes and other roles' pages."""
        patterns = [glob_to_regex(p) for p in self.bp.policy.deny_paths]
        patterns += [glob_to_regex(r.path) for r in self.bp.excluded if r.kind == "page"]
        for page in self.bp.pages:
            if page.kind == "page" and page.access == "roles" and self.role not in page.roles:
                patterns.append(glob_to_regex(page.path))
        return sorted(set(patterns))

    @property
    def progress_path(self) -> Path:
        return self.run_dir / "capture" / "progress.json"

    def _load_progress(self) -> None:
        if not self.progress_path.exists():
            return
        data = json.loads(self.progress_path.read_text(encoding="utf-8"))
        if data.get("run_id") != self.run_id or data.get("role") != self.role:
            return
        for raw in data.get("flows", []):
            fr = FlowResult.model_validate(raw)
            if fr.status == "verified":
                self.results[fr.flow_id] = fr
        self.capturer.states = [State.model_validate(s) for s in data.get("states", [])]
        kept = {sid for fr in self.results.values() for sid in fr.state_ids}
        self.capturer.states = [s for s in self.capturer.states if s.id in kept]
        for entity, ids in data.get("own_objects", {}).items():
            self.ledger.own_ids[entity] = set(ids)
        self.object_status = data.get("object_status", {})
        self.accounts.registered = {(str(x[0]), str(x[1])) for x in data.get("registered", [])}
        self.ledger.test_values |= set(data.get("test_values", []))
        self.ledger.public_values |= set(data.get("public_values", []))
        self.firewall_log.extend(
            BlockedRequest.model_validate(b) for b in data.get("firewall_log", [])
        )
        self.progress.log("info", f"davom ettirish: {len(self.results)} ta flow avval bajarilgan")

    def _save_progress(self) -> None:
        data = {
            "run_id": self.run_id,
            "role": self.role,
            "flows": [r.model_dump(mode="json") for r in self.results.values()],
            "states": [s.model_dump(mode="json") for s in self.capturer.states],
            "own_objects": {k: sorted(v) for k, v in self.ledger.own_ids.items()},
            "object_status": self.object_status,
            "registered": sorted(list(x) for x in self.accounts.registered),
            "test_values": sorted(self.ledger.test_values | self.datagen.generated),
            "public_values": sorted(self.ledger.public_values),
            "firewall_log": [b.model_dump(mode="json") for b in self.firewall_log],
        }
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.progress_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.progress_path)

    def _check_cancel(self) -> None:
        if self.cancel.is_cancelled():
            raise Cancelled("ish bekor qilindi")

    # --- main ---------------------------------------------------------------------

    async def run(self) -> CaptureRun:
        target = self.bp.flows_for_role(self.role)
        if self.passive:
            skipped = [f.id for f in target if not passive_safe(f)]
            target = [f for f in target if passive_safe(f)]
            if skipped:
                self.notes.append(
                    "passiv rejim (domen tasdiqlanmagan): "
                    f"{len(skipped)} ta flow bajarilmadi: {', '.join(skipped[:20])}"
                )
        self.target_ids = {f.id for f in target}
        order = self.bp.requirement_closure(sorted(self.target_ids))
        if self.passive:
            order = [f for f in order if passive_safe(f)]
        self._load_progress()
        if not self.passive:
            try:
                self.accounts.identity(self.role, "A")
            except AccountMissing as exc:
                raise RunAborted(str(exc)) from exc
        self.progress.stage("explore", len(order))
        await self.session.start()
        # logout and account deletion end the session: they run after everything else
        final = [f for f in order if f.action in {"logout", "delete_account"}]
        main = [f for f in order if f not in final]
        try:
            await self._run_all(main)
            self._check_cancel()
            if self.opts.patching and not self.passive:
                await self._patched_statuses()
            self._check_cancel()
            if self.opts.state_graph:
                await self._state_graph()
            await self._run_all(final)
        finally:
            await self.session.close()
        return self._write()

    async def _run_all(self, flows: list[Flow]) -> None:
        for flow in flows:
            self._check_cancel()
            if flow.id in self.results:
                self.progress.advance()
                continue
            result = await self._run_flow(flow, capture=flow.id in self.target_ids)
            self.results[flow.id] = result
            level = "info" if result.status == "verified" else "warning"
            self.progress.log(
                level,
                f"{flow.id}: {result.status}" + (f" — {result.reason}" if result.reason else ""),
            )
            self.progress.advance()
            self._save_progress()

    def _write(self) -> CaptureRun:
        flows = [self.results[f.id] for f in self.bp.topo_order() if f.id in self.results]
        role_info = self.bp.role(self.role)
        capture = CaptureRun(
            run_id=self.run_id,
            blueprint_hash=self.bp.content_hash(),
            role=self.role,
            role_label=role_info.label if role_info else self.role,
            project=self.bp.project,
            base_url=self.opts.base_url,  # type: ignore[arg-type]
            environment=self.opts.environment,
            started_at=self.started_at,
            finished_at=datetime.now(UTC),
            flows=flows,
            states=self.capturer.states,
            firewall_log=self.firewall_log,
            own_objects={k: sorted(v) for k, v in self.ledger.own_ids.items()},
            test_values=sorted(self.ledger.test_values | self.datagen.generated),
            public_values=sorted(self.ledger.public_values),
            privilege_ok=True if f"{self.role}:A" in self.privilege_checked else None,
            notes=self.notes,
            pseudonym_scope=self.datagen.scope,
        )
        save_json(self.run_dir / "capture" / "capture.json", capture)
        self._save_progress()
        return capture

    # --- accounts -----------------------------------------------------------------

    async def _ensure_login(self, role: str, alias: str) -> None:
        key = (role, alias)
        if key in self.accounts.logged_in:
            return
        if self.accounts.needs_register(role, alias):
            register = self.bp.flow(f"{role}.register")
            if register is None:
                raise StepFailed(f"«{role}» uchun ro'yxatdan o'tish flow'i yo'q")
            result = await self._run_flow(register, capture=False, alias=alias, nested=True)
            if result.status != "verified":
                raise StepFailed(f"{alias} akkauntni ro'yxatdan o'tkazib bo'lmadi: {result.reason}")
        login = self.bp.flow(f"{role}.login")
        if login is None:
            raise StepFailed(f"«{role}» uchun kirish flow'i yo'q")
        result = await self._run_flow(login, capture=False, alias=alias, nested=True)
        if result.status != "verified":
            raise StepFailed(f"{alias} akkaunt bilan kirib bo'lmadi: {result.reason}")

    async def _after_login(self, role: str, alias: str, acc: AccountContext) -> None:
        self.accounts.logged_in.add((role, alias))
        key = f"{role}:{alias}"
        if key in self.privilege_checked:
            return
        try:
            await privilege_check(acc.context, acc.firewall, self.bp, role, self.opts.base_url)
        except PrivilegedAccountError as exc:
            raise RunAborted(f"Imtiyoz tekshiruvi: {exc}. Ish to'xtatildi (SEC-6).") from exc
        self.privilege_checked.add(key)

    # --- objects ------------------------------------------------------------------

    def _pick_object(self, entity: str, needs: list[str]) -> str | None:
        statuses = self.object_status.get(entity, {})
        ids = sorted(self.ledger.own_ids.get(entity, set()), key=lambda x: (len(x), x))
        if needs:
            ids = [i for i in ids if statuses.get(i) in needs]
        return ids[-1] if ids else None

    async def _prepare(self, flow: Flow, depth: int) -> str | None:
        assert flow.entity is not None
        chain = [
            f
            for f in self.bp.requirement_closure([flow.id])
            if f.entity == flow.entity and f.id != flow.id
        ]
        self.progress.log(
            "info", f"{flow.id}: obyekt tayyorlanmoqda ({', '.join(f.id for f in chain)})"
        )
        for step_flow in chain:
            result = await self._run_flow(step_flow, capture=False, nested=True, depth=depth + 1)
            if result.status != "verified":
                return None
        return self._pick_object(flow.entity, flow.needs_status)

    # --- one flow -----------------------------------------------------------------

    async def _run_flow(
        self,
        flow: Flow,
        *,
        capture: bool,
        alias: str | None = None,
        nested: bool = False,
        depth: int = 0,
    ) -> FlowResult:
        started = time.monotonic()
        helper = not capture
        role = flow.role
        alias = alias or flow.account

        def result(
            status: str,
            reason: str | None = None,
            states: list[str] | None = None,
            stopped: bool = False,
        ) -> FlowResult:
            return FlowResult(
                flow_id=flow.id,
                status=status,  # type: ignore[arg-type]
                reason=reason,
                state_ids=states or [],
                duration_s=round(time.monotonic() - started, 2),
                role=role,
                helper=helper,
                stopped_at_confirm=stopped,
            )

        if not nested:
            failed = [
                r
                for r in flow.requires
                if r in self.results and self.results[r].status != "verified"
            ]
            if failed:
                return result("skipped", "bog'liq flow bajarilmadi: " + ", ".join(failed))
        if depth > 6:
            return result("failed", "obyekt tayyorlash zanjiri juda chuqur")

        key = "guest" if role == "guest" else f"{role}:{alias}"
        identity: Identity | None = None
        peer: Identity | None = None
        try:
            if role != "guest":
                identity = self.accounts.identity(role, alias)
                if flow.action not in ACCOUNT_ACTIONS:
                    await self._ensure_login(role, alias)
                elif flow.action == "login" and self.accounts.needs_register(role, alias):
                    register = self.bp.flow(f"{role}.register")
                    if register is not None and register.id not in self.results:
                        await self._run_flow(register, capture=False, alias=alias, nested=True)
                if any((s.data or "").startswith("peer:") for s in flow.steps):
                    other = "B" if alias == "A" else "A"
                    peer = self.accounts.identity(role, other)
                    await self._ensure_login(role, other)
        except AccountMissing as exc:
            return result("skipped", str(exc))
        except StepFailed as exc:
            return result("failed", str(exc))

        objects: dict[str, str] = {}
        uses_own = any("{own:" in (s.path or "") for s in flow.steps)
        if flow.entity and (flow.needs_status or uses_own) and flow.action != "create":
            obj = self._pick_object(flow.entity, flow.needs_status)
            if obj is None:
                obj = await self._prepare(flow, depth)
            if obj is None:
                return result("failed", f"«{flow.entity}» obyektini tayyorlab bo'lmadi")
            objects[flow.entity] = obj
        if uses_own:
            for entity in {
                m for s in flow.steps for m in re.findall(r"\{own:([a-z_]+)_id\}", s.path or "")
            }:
                if entity not in objects:
                    picked = self._pick_object(entity, [])
                    if picked is not None:
                        objects[entity] = picked

        acc = await self.session.account(key)
        page = acc.page
        start_responses = len(acc.responses)
        created: list[Awaitable[Any]] = []

        def on_response(response: Response) -> None:
            req = response.request
            if (
                flow.creates
                and req.method == "POST"
                and response.ok
                and same_origin(response.url, self.opts.base_url)
                and "json" in response.headers.get("content-type", "")
            ):
                created.append(response.json())

        def api_errors() -> list[str]:
            return [
                f"{m} {urlsplit(u).path} -> {s}"
                for m, u, s, _ in acc.responses[start_responses:]
                if m not in {"GET", "HEAD"} and s >= 400
            ]

        page.on("response", on_response)
        ctx = StepContext(
            identity=identity,
            peer=peer,
            current_objects=objects,
            datagen=self.datagen,
            mailbox=self.mailbox,
            human=self.human,
            environment=self.opts.environment,
            base_url=self.opts.base_url,
            timeout_ms=self.opts.step_timeout_ms,
        )
        executor = StepExecutor(page, ctx, api_errors)
        states: list[str] = []
        prev_action = "goto"
        acc.network.clear()

        async def snap(index: int) -> None:
            if not capture:
                return
            status = self.object_status.get(flow.entity or "", {}).get(
                objects.get(flow.entity or "", ""), None
            )
            if index == len(flow.steps) and flow.sets_status:
                status = flow.sets_status  # the final state shows the new status
            state = await self.capturer.snapshot(
                page,
                account=key,
                network=acc.network,
                flow_id=flow.id,
                step_index=index,
                entity=flow.entity,
                entity_status=status,
            )
            acc.network.clear()
            states.append(state.id)

        current = 0
        try:
            for i, step in enumerate(flow.steps):
                current = i
                self._check_cancel()
                if step.action in INTERACTIVE and (
                    prev_action in PAGE_CHANGING or step.action == "click"
                ):
                    await snap(i)
                if step.action == "click" and step.target is not None and step.destructive:
                    allowed, why = self.engine.allows_click(
                        step.target.name or "", ClickContext(own_object=True, flow_step=True)
                    )
                    if not allowed:
                        raise StepFailed(f"siyosat ruxsat bermadi: {why}")
                await executor.run(step)
                prev_action = step.action
                if self.opts.step_delay_ms:
                    await asyncio.sleep(self.opts.step_delay_ms / 1000)
            await snap(len(flow.steps))
        except StoppedAtConfirm as exc:
            await snap(len(flow.steps) - 1)
            page.remove_listener("response", on_response)
            return result(
                "verified",
                f"production: tasdiqlash oynasida to'xtatildi ({exc})",
                states,
                stopped=True,
            )
        except StepFailed as exc:
            page.remove_listener("response", on_response)
            try:
                await snap(current)
            except PlaywrightError:
                pass
            failed_step = describe_step(flow.steps[current]) if flow.steps else "-"
            return result("failed", f"{current + 1}-qadam ({failed_step}): {exc}", states)
        except PlaywrightError as exc:
            page.remove_listener("response", on_response)
            return result("failed", f"brauzer xatosi: {str(exc).splitlines()[0][:200]}", states)
        page.remove_listener("response", on_response)

        if flow.creates:
            new_id = None
            for pending in created:
                try:
                    body = await pending
                except Exception:  # noqa: BLE001 - not JSON after all
                    continue
                if isinstance(body, dict) and body.get("id") is not None:
                    new_id = str(body["id"])
            if new_id is None:
                match = re.search(r"/(\d+)(?:[/?#]|$)", page.url)
                new_id = match.group(1) if match else None
            if new_id is None:
                return result("failed", "yaratilgan obyekt id'sini aniqlab bo'lmadi", states)
            self.ledger.own_ids.setdefault(flow.creates, set()).add(new_id)
            self.object_status.setdefault(flow.creates, {})[new_id] = flow.sets_status or "new"
        elif flow.entity and flow.sets_status and flow.entity in objects:
            self.object_status.setdefault(flow.entity, {})[objects[flow.entity]] = flow.sets_status

        if flow.action == "register" and role != "guest":
            self.accounts.registered.add((role, alias))
        elif flow.action == "login" and role != "guest":
            await self._after_login(role, alias, acc)
        elif flow.action == "logout":
            self.accounts.logged_in.discard((role, alias))
        elif flow.action == "delete_account":
            self.accounts.logged_in.discard((role, alias))
            self.accounts.registered.discard((role, alias))
            await self.session.reset(key)
        return result("verified", None, states)

    # --- patched statuses (FR-E8) ---------------------------------------------------

    async def _patched_statuses(self) -> None:
        key = f"{self.role}:A"
        for entity in self.bp.entities:
            if not entity.status_field or not entity.statuses:
                continue
            view = next(
                (
                    f
                    for f in self.bp.flows
                    if f.role == self.role
                    and f.entity == entity.name
                    and f.action == "view"
                    and self.results.get(f.id, FlowResult(flow_id=f.id, status="failed")).status
                    == "verified"
                ),
                None,
            )
            if view is None or not view.steps or view.steps[0].action != "goto":
                continue
            obj = self._pick_object(entity.name, [])
            if obj is None:
                continue
            unreachable = [s.value for s in entity.statuses if self.role not in s.reachable_by]
            if not unreachable:
                continue
            try:
                await self._ensure_login(self.role, "A")
            except (StepFailed, RunAborted) as exc:
                self.notes.append(f"yamalgan statuslar olinmadi: {exc}")
                return
            acc = await self.session.account(key)
            path = (view.steps[0].path or "").replace(f"{{own:{entity.name}_id}}", obj)
            for value in unreachable:
                self._check_cancel()
                patch = StatusPatch(entity.name, obj, entity.status_field, value)
                acc.firewall.patches.append(patch)
                try:
                    await acc.page.goto(self.opts.base_url.rstrip("/") + path)
                    acc.network.clear()
                    await self.capturer.snapshot(
                        acc.page,
                        account=key,
                        network=acc.network,
                        entity=entity.name,
                        entity_status=value,
                        patched=True,
                        trigger=f"status={value}",
                    )
                except PlaywrightError as exc:
                    self.notes.append(f"yamalgan status {value} olinmadi: {exc}")
                finally:
                    acc.firewall.patches.remove(patch)

    # --- state graph (FR-E7) --------------------------------------------------------

    async def _state_graph(self) -> None:
        account = "guest" if self.passive else "A"
        key = "guest" if self.passive else f"{self.role}:A"
        limit = self.opts.max_states or self.policy.max_states
        seen = {s.hash for s in self.capturer.states}
        urls: list[tuple[str, str]] = []
        for state in self.capturer.states:
            if state.account != account or state.patched or state.flow_id is None:
                continue
            tpl = path_template(urlsplit(state.url).path)
            if tpl not in [t for t, _ in urls]:
                urls.append((tpl, state.url))
        if not self.passive:
            try:
                await self._ensure_login(self.role, "A")
            except (StepFailed, RunAborted):
                return
        acc = await self.session.account(key)
        page = acc.page
        own = {i for ids in self.ledger.own_ids.values() for i in ids}
        row_visits = 0
        for _tpl, url in urls[:15]:
            if len(self.capturer.states) >= limit:
                break
            self._check_cancel()
            if not self.engine.allows_path(urlsplit(url).path):
                continue
            parent = next((s.id for s in self.capturer.states if s.url == url), None)
            try:
                await page.goto(url)
                await self.capturer.settle(page)
                candidates: list[dict[str, Any]] = await page.evaluate(js.SAFE_CANDIDATES)
            except PlaywrightError:
                continue
            for index, cand in enumerate(candidates[:8]):
                name = str(cand.get("name") or "")
                if not name:
                    continue
                ok, _ = self.engine.allows_click(name, ClickContext())
                if not ok:
                    continue
                try:
                    await page.mouse.click(
                        float(cand["x"]) + float(cand["w"]) / 2 - await page.evaluate("scrollX"),
                        float(cand["y"]) + float(cand["h"]) / 2 - await page.evaluate("scrollY"),
                    )
                    await self.capturer.settle(page)
                    aria = await page.locator("body").aria_snapshot(timeout=4000)
                except PlaywrightError:
                    continue
                digest_probe = normalize_for_hash(aria)
                if digest_probe and not any(
                    s.aria and normalize_for_hash(s.aria) == digest_probe
                    for s in self.capturer.states
                ):
                    acc.network.clear()
                    state = await self.capturer.snapshot(
                        page,
                        account=key,
                        network=acc.network,
                        parent_id=parent,
                        trigger=name,
                    )
                    if state.hash in seen:
                        self.capturer.states.pop()
                    else:
                        seen.add(state.hash)
                try:
                    await page.keyboard.press("Escape")
                    if page.url != url:
                        await page.goto(url)
                    else:
                        await page.goto(url)
                    await self.capturer.settle(page)
                except PlaywrightError:
                    break
                if index >= 5 or len(self.capturer.states) >= limit:
                    break
            # a list page of the role: open one record that is not ours (data is replaced)
            role_page = any(
                p.kind == "page"
                and p.access == "roles"
                and self.role in p.roles
                and re.fullmatch(glob_to_regex(p.path), urlsplit(url).path)
                for p in self.bp.pages
            )
            if role_page and row_visits < 3 and ":id" not in path_template(urlsplit(url).path):
                opened = 0
                try:
                    links: list[dict[str, str]] = await page.evaluate(js.ROW_LINKS)
                except PlaywrightError:
                    links = []
                # Records of other people first: a row that shows a value our own test
                # accounts made (their names, emails) is the tool's leftover, not a real one.
                made = {v for v in self.datagen.own_values if len(v) >= 5}
                links.sort(key=lambda lk: any(v in lk.get("row", "") for v in made))
                for link in links:
                    ids = re.findall(r"/(\d+)(?:/|$)", link["href"])
                    if not ids or ids[-1] in own or not self.engine.allows_path(link["href"]):
                        continue
                    if any(re.fullmatch(p, link["href"]) for p in self.capturer.forbidden_patterns):
                        continue
                    entity = self.ledger.entity_for_path(urlsplit(link["href"]).path)
                    try:
                        acc.responses.clear()
                        await page.goto(self.opts.base_url.rstrip("/") + link["href"])
                        await self.capturer.settle(page)  # SPA data arrives after "load"
                        from_json = any(
                            "json" in ctype
                            for method, _u, _s, ctype in acc.responses
                            if method == "GET"
                        )
                        if self.ledger.is_ugc(entity) and not from_json:
                            # Server-rendered text someone else wrote cannot be told apart
                            # from the page's own text: default-deny, the page is not kept.
                            note = (
                                f"{path_template(urlsplit(link['href']).path)}: boshqa "
                                "foydalanuvchi yozgan matn server sahifasida ajratilmaydi — "
                                "bu yozuv sahifasi olinmadi (FR-E10)"
                            )
                            if note not in self.notes:
                                self.notes.append(note)
                            continue
                        acc.network.clear()
                        state = await self.capturer.snapshot(
                            page,
                            account=key,
                            network=acc.network,
                            parent_id=parent,
                            trigger=link["name"] or link["href"],
                        )
                        row_visits += 1
                        opened += 1
                        seen.add(state.hash)
                    except PlaywrightError:
                        pass
                    if opened >= 2:
                        break


async def run_explorer(
    blueprint: Blueprint,
    run_dir: Path,
    opts: ExploreOptions,
    human: HumanInput,
    progress: ProgressSink,
    cancel: CancelToken,
) -> CaptureRun:
    runner = Runner(blueprint, run_dir, opts, human, progress, cancel)
    return await runner.run()


def load_capture(run_dir: Path) -> CaptureRun:
    return load_json(run_dir / "capture" / "capture.json", CaptureRun)
