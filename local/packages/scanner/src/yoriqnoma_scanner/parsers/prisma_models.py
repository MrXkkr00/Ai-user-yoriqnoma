"""Prisma schema (``schema.prisma``): entities, owner fields, status and role enums (T29).

Read as text, never run. ``model Order { userId Int  user User @relation(...)  status
OrderStatus @default(NEW) }`` gives the entity ``order`` with owner ``userId`` and the
statuses of the ``OrderStatus`` enum; the ``User`` model's role enum gives the roles and
its default the role of self-registered users.
"""

from __future__ import annotations

import re

from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import EntityCandidate, ParseResult
from yoriqnoma_scanner.parsers.sqlalchemy_models import is_pii_name

_BLOCK = re.compile(r"^(model|enum)\s+(\w+)\s*\{(.*?)^\}", re.S | re.M)
ROLE_FIELDS = {"role", "roles", "userType", "type"}
STATUS_FIELDS = {"status", "state"}


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class PrismaParser:
    name = "prisma"

    def applies(self, project: ProjectInfo) -> bool:
        return bool(project.prisma_files)

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        result = ParseResult()
        text = "\n".join(fs.read_text(p) or "" for p in project.prisma_files)
        enums: dict[str, list[str]] = {}
        models: dict[str, list[list[str]]] = {}
        for kind, name, body in _BLOCK.findall(text):
            lines = [
                ln.split("//")[0].split() for ln in body.splitlines() if ln.split("//")[0].strip()
            ]
            if kind == "enum":
                enums[name] = [parts[0] for parts in lines if not parts[0].startswith("@")]
            else:
                models[name] = [parts for parts in lines if not parts[0].startswith("@")]
        rel = ", ".join(fs.rel(p) for p in project.prisma_files)
        for name, fields in models.items():
            entity = snake(name)
            cand = EntityCandidate(name=entity, table=snake(name) + "s", source=f"{rel}#{name}")
            relations = {
                parts[0]: parts[1].rstrip("?[]")
                for parts in fields
                if len(parts) > 1 and parts[1].rstrip("?[]") in models
            }
            for parts in fields:
                if len(parts) < 2:
                    continue
                fname, ftype = parts[0], parts[1].rstrip("?[]")
                if fname in relations:
                    continue
                cand.fields.append(fname)
                attrs = " ".join(parts[2:])
                if ftype in enums and fname in STATUS_FIELDS:
                    cand.status_field = fname
                    cand.statuses = enums[ftype]
                if is_pii_name(snake(fname), "users" if name == "User" else cand.table):
                    cand.pii_fields.append(fname)
                if name == "User" and fname in ROLE_FIELDS and ftype in enums:
                    for value in enums[ftype]:
                        result.role_values.setdefault(value, f"{rel}#{ftype}")
                    default = re.search(r"@default\((\w+)\)", attrs)
                    if default:
                        result.signup_role_default = default.group(1)
            owners = [rel_field for rel_field, target in relations.items() if target == "User"]
            for fname in [p[0] for p in fields]:
                if owners and fname == f"{owners[0]}Id":
                    cand.owner_field = fname
            if cand.owner_field is None and owners:
                cand.owner_field = owners[0]
            result.entities.append(cand)
        return result
