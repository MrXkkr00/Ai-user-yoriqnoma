"""SQLAlchemy / SQLModel models read as CODE only (AST): never imported, never connected.

Gives entities with the owner field (FK to users), the status enum and fields that may
hold other people's personal data (``pii_fields``, TZ FR-E10).
"""

from __future__ import annotations

import ast
import re

from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import EntityCandidate, ParseResult
from yoriqnoma_scanner.pyindex import PyIndex, PyModule, call_name, dotted_name, enum_members

OWNER_NAMES = ("user_id", "owner_id", "author_id", "created_by_id", "created_by", "creator_id")
PII_PATTERN = re.compile(
    r"(^|_)(name|full_name|first_name|last_name|middle_name|fio|email|phone|tel|mobile|"
    r"address|card|card_number|passport|pinfl|jshshir|birth_date|birthday|avatar|photo)($|_)"
)
NOT_PII = {"product_name", "username_hash", "file_name", "filename", "name_uz", "name_ru"}
STATUS_NAMES = ("status", "state")
TECH_TABLES = {"sessions", "session", "tokens", "migrations", "alembic_version"}


def singular(table: str) -> str:
    if table.endswith("ies"):
        return table[:-3] + "y"
    if table.endswith(("ses", "xes")):
        return table[:-2]
    if table.endswith("s") and not table.endswith("ss"):
        return table[:-1]
    return table


PERSON_TABLES = {
    "users",
    "user",
    "customers",
    "clients",
    "members",
    "employees",
    "staff",
    "profiles",
    "contacts",
    "people",
    "persons",
    "students",
    "patients",
    "accounts",
}


def is_pii_name(name: str, table: str = "users") -> bool:
    """Field names that may hold a person's data. A bare ``name`` counts only for people."""
    low = name.lower()
    if low in NOT_PII:
        return False
    if low in {"name", "title"}:
        return low == "name" and table.lower() in PERSON_TABLES
    return bool(PII_PATTERN.search(low))


class SQLAlchemyModelsParser:
    name = "sqlalchemy"

    def applies(self, project: ProjectInfo) -> bool:
        return bool({"sqlalchemy", "fastapi", "flask"} & project.stacks)

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        index = PyIndex(fs, project.python_files)
        result = ParseResult()
        for module in index.modules.values():
            for cname, cls in module.classes.items():
                entity = self._entity(index, module, cname, cls)
                if entity is not None:
                    result.entities.append(entity)
        return result

    def _entity(
        self, index: PyIndex, module: PyModule, cname: str, cls: ast.ClassDef
    ) -> EntityCandidate | None:
        table: str | None = None
        bases = index.class_bases(module, cls)
        is_sqlmodel_table = "SQLModel" in bases and any(kw.arg == "table" for kw in cls.keywords)
        for node in cls.body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "__tablename__"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                table = node.value.value
        # Flask-SQLAlchemy: ``class Order(db.Model)`` gets its table name from the class name
        is_flask_model = "Model" in bases and any(
            self._column(node)[0] is not None for node in cls.body
        )
        if table is None and not (is_sqlmodel_table or is_flask_model):
            return None
        table = table or re.sub(r"(?<!^)(?=[A-Z])", "_", cname).lower() + "s"
        if table in TECH_TABLES:
            return None
        entity = EntityCandidate(
            name=re.sub(r"(?<!^)(?=[A-Z])", "_", cname).lower(),
            table=table,
            source=module.src(cls),
        )
        owner_candidates: list[str] = []
        for node in cls.body:
            fname, annotation, value = self._column(node)
            if fname is None:
                continue
            entity.fields.append(fname)
            text = ast.unparse(value) if value is not None else ""
            if fname in OWNER_NAMES or ("ForeignKey(" in text and "user" in text.lower()):
                owner_candidates.append(fname)
            ann_text = ast.unparse(annotation) if annotation is not None else text
            if is_pii_name(fname, table) and "bool" not in ann_text.lower():
                entity.pii_fields.append(fname)
            if fname in STATUS_NAMES:
                enum_name = self._enum_name(annotation, value)
                found = index.is_enum(module, enum_name) if enum_name else None
                if found:
                    entity.status_field = fname
                    entity.statuses = _member_values(found[1])
        for preferred in OWNER_NAMES:
            if preferred in owner_candidates:
                entity.owner_field = preferred
                break
        else:
            if owner_candidates:
                entity.owner_field = owner_candidates[0]
        return entity

    @staticmethod
    def _column(node: ast.stmt) -> tuple[str | None, ast.expr | None, ast.expr | None]:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            if name.startswith("_"):
                return None, None, None
            if "relationship" in (call_name(node.value) if node.value else ""):
                return None, None, None
            return name, node.annotation, node.value
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if call_name(node.value).split(".")[-1] in {"Column", "mapped_column"}:
                return name, None, node.value
        return None, None, None

    @staticmethod
    def _enum_name(annotation: ast.expr | None, value: ast.expr | None) -> str | None:
        if isinstance(annotation, ast.Subscript):  # Mapped[OrderStatus]
            inner = annotation.slice
            name = dotted_name(inner)
            if name:
                return name.split(".")[-1]
        if isinstance(annotation, ast.Name):
            return annotation.id
        if isinstance(value, ast.Call):  # Column(Enum(OrderStatus))
            for arg in value.args:
                if isinstance(arg, ast.Call) and call_name(arg).endswith("Enum") and arg.args:
                    name = dotted_name(arg.args[0])
                    if name:
                        return name.split(".")[-1]
        return None


def _member_values(cls: ast.ClassDef) -> list[str]:
    return enum_members(cls)
