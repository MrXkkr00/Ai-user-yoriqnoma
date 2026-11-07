"""Parser protocol and the intermediate results parsers produce (ARCHITECTURE §4.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_schemas import Flow, Form, FormField

GuardKind = Literal["role", "ownership", "auth", "unknown"]


@dataclass
class GuardInfo:
    kind: GuardKind
    expr: str
    source: str
    roles: list[str] = field(default_factory=list)  # for kind="role"
    admin: bool = False  # admin or admin-like (superuser, staff, ...)


@dataclass
class RouteCandidate:
    path: str  # "/api/orders/:id" (params always as :name)
    kind: Literal["page", "api"]
    methods: list[str]
    guards: list[GuardInfo]
    source: str
    handler: str | None = None
    component: str | None = None  # page routes: the rendered component
    request_model: str | None = None  # api routes: pydantic body model
    status_sets: list[tuple[str, str]] = field(default_factory=list)  # (field, value)
    status_requires: list[str] = field(default_factory=list)  # precondition values
    downloads: bool = False  # api route returns a file
    creates_user_role: str | None = None  # registration handler: role given to new users


@dataclass
class EntityCandidate:
    name: str  # "order"
    table: str  # "orders"
    source: str
    owner_field: str | None = None
    pii_fields: list[str] = field(default_factory=list)
    status_field: str | None = None
    statuses: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)


@dataclass
class NavItem:
    label: str
    path: str
    source: str


@dataclass
class ActionBinding:
    """A UI control that sends an API request (button, form submit or download link)."""

    component: str
    kind: Literal["button", "form", "link"]
    api_method: str
    api_path: str
    trigger: str  # visible label of the control
    source: str
    opener: str | None = None  # label of the button that opens the modal holding the control
    in_modal: bool = False
    form_id: str | None = None


@dataclass
class LinkInfo:
    component: str
    label: str
    to: str  # path template, "/catalog/:id"
    source: str


@dataclass
class ComponentInfo:
    name: str
    file: str
    forms: list[Form] = field(default_factory=list)
    actions: list[ActionBinding] = field(default_factory=list)
    links: list[LinkInfo] = field(default_factory=list)
    loads: list[str] = field(default_factory=list)  # "GET /api/orders/:id" on page load


@dataclass
class ParseResult:
    routes: list[RouteCandidate] = field(default_factory=list)
    forms: list[Form] = field(default_factory=list)
    entities: list[EntityCandidate] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)
    nav: list[NavItem] = field(default_factory=list)
    i18n: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    components: dict[str, ComponentInfo] = field(default_factory=dict)
    request_models: dict[str, list[FormField]] = field(default_factory=dict)
    role_values: dict[str, str] = field(default_factory=dict)  # role id -> source
    role_labels: dict[str, str] = field(default_factory=dict)

    def merge(self, other: ParseResult) -> None:
        self.routes += other.routes
        self.forms += other.forms
        self.entities += other.entities
        self.flows += other.flows
        self.nav += other.nav
        self.i18n.update(other.i18n)
        self.notes += other.notes
        self.components.update(other.components)
        self.request_models.update(other.request_models)
        for role, source in other.role_values.items():
            self.role_values.setdefault(role, source)
        self.role_labels.update(other.role_labels)


class Parser(Protocol):
    name: str

    def applies(self, project: ProjectInfo) -> bool: ...

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult: ...
