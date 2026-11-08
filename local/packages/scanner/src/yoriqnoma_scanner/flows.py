"""Flow builder (TZ FR-S6): account flows, page visits, entity actions; E2E flows win.

Every flow belongs to one role of kind "guest" or "role". ``requires`` orders flows and
also says which objects a flow needs: a manager's "ship" flow requires the customer's
"pay" flow, so the explorer prepares that object with a helper account first (SEC-5).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from yoriqnoma_scanner.entities import EntityIndex, entity_words, paths_match
from yoriqnoma_scanner.parsers.base import ActionBinding, ComponentInfo, LinkInfo, RouteCandidate
from yoriqnoma_schemas import Flow, Form, FormField, RoleInfo, RouteInfo, Stage, Step, Target

DESTRUCTIVE = {"cancel", "delete", "remove", "destroy", "deactivate", "archive", "reject", "revoke"}
PAYMENT = {"pay", "checkout", "purchase", "buy", "topup", "top_up", "charge"}
SOCIAL_ENTITIES = {"message", "chat", "comment", "review", "post", "reply", "conversation"}
GENERIC_SUBMITS = {"saqlash", "yuborish", "submit", "save", "send", "ok", "сохранить"}


def slug(text: str) -> str:
    text = text.lower().replace("'", "").replace("ʻ", "")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:40] or "x"


def lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def target_for(field_: FormField) -> Target:
    if field_.label:
        return Target(label=field_.label)
    return Target(css=f"[name='{field_.name}']")


def data_for_field(field_: FormField) -> str:
    name = field_.name.lower()
    ftype = field_.type.lower()
    if ftype == "checkbox":
        return "literal:true"
    if ftype == "select":
        return f"literal:{field_.options[0]}" if field_.options else "fake:option"
    if ftype == "password" or "password" in name or "parol" in name:
        return "fake:password"
    if ftype == "email" or "email" in name:
        if any(w in name for w in ("to_", "recipient", "receiver", "peer", "friend")):
            return "peer:email"
        return "fake:email"
    if ftype == "tel" or "phone" in name or "tel" == name:
        return "fake:phone_uz"
    if name in {"username", "login", "user_name"}:
        return "fake:username"
    if name in {"first_name", "firstname", "ism"}:
        return "fake:first_name"
    if name in {"last_name", "lastname", "familiya", "surname"}:
        return "fake:last_name"
    if name in {"full_name", "name", "fio", "fullname"}:
        return "fake:full_name"
    if "address" in name or "manzil" in name:
        return "fake:address"
    if ftype == "number":
        match = re.search(r"min:(\d+)", field_.rules or "")
        return f"literal:{match.group(1) if match else 1}"
    if ftype == "date":
        return "fake:date"
    return "fake:text"


def fill_steps(form: Form) -> list[Step]:
    steps: list[Step] = []
    for field_ in form.fields:
        target = target_for(field_)
        data = data_for_field(field_)
        if field_.type == "checkbox":
            steps.append(Step(action="check", target=target, data=data))
        elif field_.type == "select":
            steps.append(Step(action="select", target=target, data=data, rules=field_.rules))
        elif field_.type == "file":
            steps.append(Step(action="upload", target=target, data="file:sample.png"))
        else:
            steps.append(Step(action="fill", target=target, data=data, rules=field_.rules))
    return steps


@dataclass
class Page:
    route: RouteInfo
    component: ComponentInfo | None


@dataclass
class FlowContext:
    roles: list[RoleInfo]
    pages: list[Page]
    api: list[tuple[RouteCandidate, RouteInfo]]
    entities: EntityIndex
    forms_by_id: dict[str, Form]
    nav_labels: dict[str, str]
    notes: list[str] = field(default_factory=list)

    def usable(self) -> list[str]:
        return [r.id for r in self.roles if r.kind == "role"]

    def self_signup(self) -> list[str]:
        return [r.id for r in self.roles if r.kind == "role" and r.self_signup]

    def page_roles(self, page: Page) -> list[str]:
        return ["guest"] if page.route.access == "guest" else list(page.route.roles)

    def api_route(self, method: str, path: str) -> tuple[RouteCandidate, RouteInfo] | None:
        for cand, info in self.api:
            if method in cand.methods and paths_match(cand.path, path):
                return cand, info
        return None

    def page_of(self, component: str) -> Page | None:
        return next((p for p in self.pages if p.component and p.component.name == component), None)


class FlowBuilder:
    def __init__(self, ctx: FlowContext, components: dict[str, ComponentInfo]) -> None:
        self.ctx = ctx
        self.components = components
        self.flows: dict[str, Flow] = {}
        self.route_of_flow: dict[str, RouteCandidate] = {}  # entity action flow -> api route
        self.account_pages: set[str] = set()  # pages used by register/login/... flows

    # --- helpers ------------------------------------------------------------------

    def _add(self, flow: Flow, api: RouteCandidate | None = None) -> None:
        fid = flow.id
        n = 2
        while fid in self.flows:
            fid = f"{flow.id}_{n}"
            n += 1
        self.flows[fid] = flow.model_copy(update={"id": fid})
        if api is not None:
            self.route_of_flow[fid] = api

    def _reach(self, page: Page, role: str) -> list[Step] | None:
        """Steps that open ``page`` for ``role``: goto, resolving :id params."""
        path = page.route.path
        if ":" not in path:
            return [Step(action="goto", path=path)]
        entity = self._page_entity(page)
        if entity and role != "guest" and self._role_has_objects(role, entity):
            resolved = re.sub(r":[A-Za-z_]+", "{own:" + entity + "_id}", path, count=1)
            return [Step(action="goto", path=resolved)]
        # Not an own object: open it from a list page through a link.
        for other in self.ctx.pages:
            if other.component is None or ":" in other.route.path:
                continue
            if role not in self.ctx.page_roles(other) and "guest" not in self.ctx.page_roles(other):
                continue
            link = self._link_to(other.component.links, path)
            if link:
                return [
                    Step(action="goto", path=other.route.path),
                    Step(action="click", target=Target(role="link", name=link.label)),
                ]
        return None

    @staticmethod
    def _link_to(links: list[LinkInfo], path: str) -> LinkInfo | None:
        return next((lk for lk in links if paths_match(lk.to, path)), None)

    def _page_entity(self, page: Page) -> str | None:
        if page.component is None:
            return None
        for load in page.component.loads:
            method, _, path = load.partition(" ")
            ea = self.ctx.entities.action_for(method, path)
            if ea and ea.action == "view":
                return ea.entity
        return None

    def _role_has_objects(self, role: str, entity: str) -> bool:
        """Can the role get objects of this entity: it creates them or others prepare them."""
        ent = self.ctx.entities.entities.get(entity)
        return ent is not None and bool(ent.created_by)

    def _stage_for(self, entity: str | None, action: str, role: str) -> Stage:
        if entity and entity in SOCIAL_ENTITIES:
            return "social"
        if action in PAYMENT:
            return "payment"
        ent = self.ctx.entities.entities.get(entity or "")
        own = ent is not None and role in ent.created_by
        if action == "create":
            return "core"
        if not own:
            return "core"
        return "manage"

    def _title(self, entity: str, action: str, binding: ActionBinding | None) -> str:
        noun, plural = entity_words(entity)
        if action == "create" and binding is not None and binding.trigger:
            if binding.trigger.lower() not in GENERIC_SUBMITS:
                return binding.trigger
            return f"{noun.capitalize()} yaratish"
        if action == "list":
            return f"{plural.capitalize()} ro'yxatini ko'rish"
        if action == "view":
            return f"{noun.capitalize()} tafsilotlarini ko'rish"
        if binding is not None and action.startswith("download_"):
            return binding.trigger
        label = (binding.opener or binding.trigger) if binding else action
        first = label.split(" ")[0].lower()
        if first.startswith(noun.lower()) or (" " in label and first.endswith("ni")):
            # "Murojaatni yopish", "Javobni yuborish": the label already names its object
            return label[:1].upper() + label[1:]
        return f"{noun.capitalize()}ni {lower_first(label)}"

    # --- account flows ------------------------------------------------------------

    def account_flows(self) -> None:
        register = self._form_page(lambda c, r: bool(c.creates_user_role))
        verify = self._form_page(lambda c, r: "verify" in c.path or "confirm" in c.path)
        login = self._form_page(lambda c, r: "login" in c.path or "signin" in c.path)
        forgot = self._form_page(lambda c, r: "forgot" in c.path or "reset" in c.path)
        for role in self.ctx.self_signup():
            if register is None:
                break
            page, form, api = register
            steps = [Step(action="goto", path=page.route.path), *fill_steps(form)]
            steps.append(Step(action="click", target=form.submit))
            if verify is not None:
                vpage, vform, _ = verify
                code = next(
                    (f for f in vform.fields if re.search(r"code|otp|kod", f.name, re.I)), None
                )
                if code is not None:
                    steps.append(Step(action="verify_email", target=target_for(code)))
                    steps.append(Step(action="click", target=vform.submit))
                else:
                    steps.append(Step(action="verify_email"))
            self._add(
                Flow(
                    id=f"{role}.register",
                    title=form.submit.name or "Ro'yxatdan o'tish",
                    stage="start",
                    role=role,
                    action="register",
                    source=api.source,
                    steps=steps,
                )
            )
        if login is not None:
            page, form, api = login
            for role in self.ctx.usable():
                steps = [Step(action="goto", path=page.route.path), *fill_steps(form)]
                steps.append(Step(action="click", target=form.submit))
                requires = [f"{role}.register"] if f"{role}.register" in self.flows else []
                self._add(
                    Flow(
                        id=f"{role}.login",
                        title="Tizimga kirish",
                        stage="start",
                        role=role,
                        action="login",
                        requires=requires,
                        source=api.source,
                        steps=steps,
                    )
                )
        if forgot is not None:
            page, form, api = forgot
            self._add(
                Flow(
                    id="guest.forgot_password",
                    title="Parolni tiklash",
                    stage="start",
                    role="guest",
                    action="forgot_password",
                    source=api.source,
                    steps=[
                        Step(action="goto", path=page.route.path),
                        *fill_steps(form),
                        Step(action="click", target=form.submit),
                    ],
                )
            )
        self._logout_flows()

    def _form_page(
        self, test: Callable[[RouteCandidate, RouteInfo], bool]
    ) -> tuple[Page, Form, RouteCandidate] | None:
        for page in self.ctx.pages:
            if page.component is None:
                continue
            for binding in page.component.actions:
                if binding.kind != "form" or binding.form_id not in self.ctx.forms_by_id:
                    continue
                found = self.ctx.api_route(binding.api_method, binding.api_path)
                if found and test(found[0], found[1]):
                    self.account_pages.add(page.route.path)
                    return page, self.ctx.forms_by_id[binding.form_id], found[0]
        return None

    def _logout_flows(self) -> None:
        for cand, _info in self.ctx.api:
            if "logout" not in cand.path and "signout" not in cand.path:
                continue
            label = self._logout_label()
            if label is None:
                return
            for role in self.ctx.usable():
                self._add(
                    Flow(
                        id=f"{role}.logout",
                        title="Tizimdan chiqish",
                        stage="settings",
                        role=role,
                        action="logout",
                        requires=[f"{role}.login"],
                        source=cand.source,
                        steps=[
                            Step(action="goto", path="/"),
                            Step(action="click", target=Target(role="button", name=label)),
                        ],
                    )
                )
            return

    def _logout_label(self) -> str | None:
        for component in self.components.values():
            for binding in component.actions:
                if "logout" in binding.api_path or "signout" in binding.api_path:
                    return binding.trigger
        return None

    # --- page and entity flows ----------------------------------------------------

    def page_flows(self) -> None:
        for page in self.ctx.pages:
            if page.component is None:
                continue
            roles = self.ctx.page_roles(page)
            for binding in page.component.actions:
                found = self.ctx.api_route(binding.api_method, binding.api_path)
                if found is None:
                    continue
                cand, api_info = found
                ea = self.ctx.entities.action_for(binding.api_method, binding.api_path)
                allowed = self._allowed(roles, api_info)
                for role in allowed:
                    if ea is not None:
                        self._entity_flow(page, binding, cand, ea.entity, ea.action, role)
                    elif binding.kind == "form" and not self._is_account_api(cand):
                        self._form_flow(page, binding, cand, role)
        account_actions = {"register", "login", "logout", "forgot_password"}
        starts = {
            s.path
            for f in self.flows.values()
            if f.action not in account_actions
            for s in f.steps[:1]
            if s.action == "goto"
        }
        for page in self.ctx.pages:
            if page.component is None or page.route.path in self.account_pages:
                continue
            entity_loads = self._entity_load(page) is not None
            opened = page.route.path in starts or any(
                paths_match(page.route.path, re.sub(r"\{own:[^}]+\}", ":x", s or ""))
                for s in starts
            )
            if opened and not entity_loads:
                continue  # an action flow already shows this page
            for role in self.ctx.page_roles(page):
                self._visit_flow(page, role)

    def _entity_load(self, page: Page) -> tuple[str, str] | None:
        """(entity, list|view) shown by the page, if its path is about that entity."""
        if page.component is None:
            return None
        form_entities = {
            ea.entity
            for b in page.component.actions
            if b.kind == "form" and (ea := self.ctx.entities.action_for(b.api_method, b.api_path))
        }
        for load in page.component.loads:
            method, _, path = load.partition(" ")
            ea = self.ctx.entities.action_for(method, path)
            if ea is None or ea.action not in {"list", "view"}:
                continue
            if page.component.forms and ea.action == "list" and ea.entity not in form_entities:
                continue  # data for a form's select box, not what the page is about
            noun, plural = entity_words(ea.entity)
            words = {ea.entity, ea.entity + "s", noun, plural}
            if words & set(page.route.path.lower().split("/")) or not self._better_page(
                page, ea.entity, ea.action
            ):
                return ea.entity, ea.action
        return None

    def _better_page(self, page: Page, entity: str, action: str) -> bool:
        """Another page with the same roles shows the same data and is named after it."""
        for other in self.ctx.pages:
            if other is page or other.component is None:
                continue
            other_roles = set(self.ctx.page_roles(other))
            if "guest" not in other_roles and not other_roles & set(self.ctx.page_roles(page)):
                continue
            for load in other.component.loads:
                method, _, path = load.partition(" ")
                ea = self.ctx.entities.action_for(method, path)
                if ea and ea.entity == entity and ea.action == action:
                    if entity in other.route.path or entity + "s" in other.route.path:
                        return True
        return False

    @staticmethod
    def _is_account_api(cand: RouteCandidate) -> bool:
        return bool(cand.creates_user_role) or any(
            w in cand.path for w in ("login", "logout", "verify", "forgot", "reset", "signin")
        )

    def _allowed(self, page_roles: list[str], api: RouteInfo) -> list[str]:
        if api.access == "excluded":
            return []
        if api.access == "guest":
            return page_roles
        if page_roles == ["guest"]:
            return [r for r in api.roles]  # public page with a logged-in action (review form)
        return [r for r in page_roles if r in api.roles]

    def _entity_flow(
        self,
        page: Page,
        binding: ActionBinding,
        cand: RouteCandidate,
        entity: str,
        action: str,
        role: str,
    ) -> None:
        reach = self._reach(page, role)
        if reach is None:
            self.ctx.notes.append(
                f"{page.route.path}: «{binding.trigger}» uchun sahifani ochish yo'li topilmadi"
            )
            return
        steps = list(reach)
        if binding.kind == "form" and binding.form_id in self.ctx.forms_by_id:
            form = self.ctx.forms_by_id[binding.form_id]
            if binding.opener:
                steps.append(
                    Step(action="click", target=Target(role="button", name=binding.opener))
                )
            steps += fill_steps(form)
            steps.append(
                Step(
                    action="click",
                    target=form.submit,
                    confirm=action in DESTRUCTIVE or action in PAYMENT,
                    destructive=action in DESTRUCTIVE,
                    payment=action in PAYMENT,
                )
            )
        else:
            if binding.opener:
                steps.append(
                    Step(action="click", target=Target(role="button", name=binding.opener))
                )
            role_name = "link" if binding.kind == "link" else "button"
            steps.append(
                Step(
                    action="click",
                    target=Target(role=role_name, name=binding.trigger),
                    confirm=binding.in_modal or action in DESTRUCTIVE or action in PAYMENT,
                    destructive=action in DESTRUCTIVE,
                    payment=action in PAYMENT,
                )
            )
        self._add(
            Flow(
                id=f"{role}.{entity}.{action}",
                title=self._title(entity, action, binding),
                stage=self._stage_for(entity, action, role),
                role=role,
                entity=entity,
                action=action,
                source=binding.source,
                creates=entity if action == "create" else None,
                steps=steps,
            ),
            cand,
        )

    def _form_flow(
        self, page: Page, binding: ActionBinding, cand: RouteCandidate, role: str
    ) -> None:
        form = self.ctx.forms_by_id.get(binding.form_id or "")
        if form is None or role == "guest":
            return
        reach = self._reach(page, role)
        if reach is None:
            return
        key = f"{page.route.path} {form.id}".lower()
        destructive = "delete" in key or "o'chir" in (form.submit.name or "").lower()
        if destructive and "account" in key:
            stage: Stage = "exit"
            action = "delete_account"
            title = form.submit.name or "Hisobni o'chirish"
        elif "profile" in key:
            stage, action, title = "manage", "profile_edit", "Profilni tahrirlash"
        elif any(w in key for w in ("password", "notif", "lang", "setting", "security")):
            stage, action = "settings", "settings"
            title = form.submit.name or "Sozlamalarni saqlash"
        elif any(w in key for w in ("message", "chat")):
            stage, action, title = "social", "send", form.submit.name or "Xabar yuborish"
        else:
            stage, action, title = "manage", "submit", form.submit.name or "Formani yuborish"
        if (title or "").lower() in GENERIC_SUBMITS:
            label = self.ctx.nav_labels.get(page.route.path, page.route.path)
            title = f"«{label}» formasi"
        flow_id = f"{role}.{action}"
        if action in {"settings", "send", "submit"}:
            flow_id = f"{role}.{action}.{slug(form.submit.name or form.id)}"
        self._add(
            Flow(
                id=flow_id,
                title=title,
                stage=stage,
                role=role,
                action=action,
                source=binding.source,
                steps=[
                    *reach,
                    *fill_steps(form),
                    Step(
                        action="click",
                        target=form.submit,
                        confirm=destructive,
                        destructive=destructive,
                    ),
                ],
            ),
            cand,
        )

    def _visit_flow(self, page: Page, role: str) -> None:
        if page.component is None:
            return
        found = self._entity_load(page)
        entity, action = found if found else (None, "visit")
        if role == "guest" and page.route.access != "guest":
            return
        page_slug = "home" if page.route.path == "/" else slug(page.route.path)
        flow_id = f"{role}.{entity}.{action}" if entity else f"{role}.page.{page_slug}"
        if flow_id in self.flows:
            flow_id = f"{role}.page.{page_slug}"
            if flow_id in self.flows:
                return
        reach = self._reach(page, role)
        if reach is None:
            self.ctx.notes.append(f"{page.route.path}: {role} uchun ochish yo'li topilmadi")
            return
        if entity:
            title = self._title(entity, action, None)
            stage = self._stage_for(entity, action, role)
        else:
            label = self.ctx.nav_labels.get(page.route.path) or page.component.name
            title = f"«{label}» sahifasi"
            stage = "core"
        self._add(
            Flow(
                id=flow_id,
                title=title,
                stage=stage,
                role=role,
                entity=entity,
                action=action,
                source=page.route.source,
                steps=reach,
            )
        )

    # --- requires -----------------------------------------------------------------

    def link_requires(self) -> None:
        sets_status: dict[str, list[str]] = {}  # status value -> flow ids that set it
        for fid, cand in self.route_of_flow.items():
            for _, value in cand.status_sets:
                sets_status.setdefault(value, []).append(fid)
        creators: dict[str, list[str]] = {}
        for fid, flow in self.flows.items():
            if flow.action == "create" and flow.entity:
                creators.setdefault(flow.entity, []).append(fid)

        for fid, flow in list(self.flows.items()):
            reqs: list[str] = list(flow.requires)
            needs: list[str] = []
            sets: str | None = None
            if flow.role != "guest" and flow.action not in {"register", "login"}:
                login = f"{flow.role}.login"
                if login in self.flows:
                    reqs.append(login)
            uses_own = any("{own:" in (s.path or "") for s in flow.steps)
            if flow.entity and (uses_own or flow.action not in {"create", "list"}):
                fcand = self.route_of_flow.get(fid)
                pre = fcand.status_requires if fcand else []
                ent = self.ctx.entities.entities.get(flow.entity)
                creator = ent is not None and flow.role in ent.created_by
                if not pre and flow.action == "view" and not creator:
                    pre = self._role_preconditions(flow.role, flow.entity)
                needs = list(dict.fromkeys(pre))
                if pre:
                    for value in pre:
                        reqs += [x for x in sets_status.get(value, []) if x != fid]
                elif flow.entity in creators:
                    own_creator = [
                        c for c in creators[flow.entity] if self.flows[c].role == flow.role
                    ]
                    reqs += own_creator or creators[flow.entity][:1]
            if flow.action == "list" and flow.entity in creators:
                own_creator = [c for c in creators[flow.entity] if self.flows[c].role == flow.role]
                reqs += own_creator
            route = self.route_of_flow.get(fid)
            if route is not None and flow.entity:
                status_field = self.ctx.entities.candidates[flow.entity].status_field
                sets = next((v for f, v in route.status_sets if f == status_field), None)
            self.flows[fid] = flow.model_copy(
                update={
                    "requires": list(dict.fromkeys(reqs)),
                    "needs_status": needs,
                    "sets_status": sets,
                }
            )

        for fid, flow in list(self.flows.items()):
            if flow.action in {"delete_account", "logout"}:
                others = [
                    o.id
                    for o in self.flows.values()
                    if o.role == flow.role
                    and o.id != fid
                    and o.action != "delete_account"
                    and (flow.action == "delete_account" or o.action != "logout")
                    and fid not in self._closure(o.id)
                ]
                self.flows[fid] = flow.model_copy(
                    update={"requires": list(dict.fromkeys([*flow.requires, *others]))}
                )

    def _role_preconditions(self, role: str, entity: str) -> list[str]:
        values: list[str] = []
        for fid, cand in self.route_of_flow.items():
            flow = self.flows[fid]
            if flow.role == role and flow.entity == entity:
                values += cand.status_requires
        return values

    def _closure(self, fid: str) -> set[str]:
        seen: set[str] = set()
        stack = [fid]
        while stack:
            cur = stack.pop()
            if cur in seen or cur not in self.flows:
                continue
            seen.add(cur)
            stack.extend(self.flows[cur].requires)
        return seen

    # --- E2E ----------------------------------------------------------------------

    def merge_e2e(self, e2e_flows: list[Flow]) -> None:
        for e2e in e2e_flows:
            start = next((s.path for s in e2e.steps if s.action == "goto"), None)
            match = next(
                (
                    f
                    for f in self.flows.values()
                    if f.steps
                    and f.steps[0].action == "goto"
                    and f.steps[0].path == start
                    and any(s.action in {"fill", "select"} for s in f.steps)
                ),
                None,
            )
            if match is None:
                self.ctx.notes.append(f"E2E «{e2e.title}» ({e2e.source}): mos flow topilmadi")
                continue
            merged = self._merge_steps(e2e.steps, match.steps)
            self.flows[match.id] = match.model_copy(
                update={
                    "steps": merged,
                    "source": f"{e2e.source} (E2E) + {match.source}",
                    "confidence": 1.0,
                }
            )
            self.ctx.notes.append(f"E2E «{e2e.title}» ({e2e.source}) -> {match.id}")

    @staticmethod
    def _merge_steps(e2e: list[Step], generated: list[Step]) -> list[Step]:
        def submit_index(steps: list[Step]) -> int | None:
            seen_fill = False
            for i, step in enumerate(steps):
                if step.action in {"fill", "select", "check"}:
                    seen_fill = True
                elif step.action == "click" and seen_fill:
                    return i
            return None

        ei, gi = submit_index(e2e), submit_index(generated)
        if ei is None or gi is None:
            return generated
        end = ei + 1
        while end < len(e2e) and e2e[end].action.startswith("expect"):
            end += 1
        head = list(e2e[:end])
        flags = generated[gi]
        head[ei] = head[ei].model_copy(
            update={
                "confirm": flags.confirm,
                "destructive": flags.destructive,
                "payment": flags.payment,
            }
        )
        return [*head, *generated[gi + 1 :]]


def build_flows(
    ctx: FlowContext, components: dict[str, ComponentInfo], e2e_flows: list[Flow]
) -> list[Flow]:
    builder = FlowBuilder(ctx, components)
    builder.account_flows()
    builder.page_flows()
    builder.merge_e2e(e2e_flows)
    builder.link_requires()
    return list(builder.flows.values())
