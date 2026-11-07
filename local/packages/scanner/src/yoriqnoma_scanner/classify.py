"""Roles and route access (TZ FR-RL1, FR-RL2, FR-S4). Default-deny everywhere (SEC-1).

Roles: ``guest`` (not logged in), ``role`` (a manual can be written for it) or
``excluded`` (administrator, admin-like or unclear). Routes: which roles can open them;
admin-only, denied or unclear routes are ``excluded``.
"""

from __future__ import annotations

import fnmatch
import re

from yoriqnoma_scanner.parsers.base import GuardInfo, ParseResult, RouteCandidate
from yoriqnoma_schemas import RoleInfo, RouteInfo

ADMIN_ROLE_NAMES = {
    "admin",
    "administrator",
    "superadmin",
    "super_admin",
    "superuser",
    "root",
    "sysadmin",
    "staff",
    "owner_admin",
    "site_admin",
}
MANAGEMENT_SEGMENTS = {"users", "roles", "permissions", "groups", "site-settings", "site_settings"}

ROLE_LABELS = {
    "guest": "Mehmon",
    "customer": "Mijoz",
    "client": "Mijoz",
    "user": "Foydalanuvchi",
    "buyer": "Xaridor",
    "seller": "Sotuvchi",
    "vendor": "Sotuvchi",
    "manager": "Menejer",
    "sales_manager": "Sotuv menejeri",
    "operator": "Operator",
    "courier": "Kuryer",
    "driver": "Haydovchi",
    "teacher": "O'qituvchi",
    "student": "Talaba",
    "doctor": "Shifokor",
    "patient": "Bemor",
    "moderator": "Moderator",
    "editor": "Muharrir",
    "author": "Muallif",
    "accountant": "Buxgalter",
    "support": "Qo'llab-quvvatlash xodimi",
    "admin": "Administrator",
    "administrator": "Administrator",
    "superadmin": "Superadmin",
    "staff": "Xodim (staff)",
}


def role_label(role_id: str, labels: dict[str, str] | None = None) -> str:
    if labels and role_id in labels:
        return labels[role_id]
    return ROLE_LABELS.get(role_id.lower(), role_id.replace("_", " ").capitalize())


def deny_glob_match(path: str, globs: list[str]) -> bool:
    candidates = {path, path.rstrip("/") or "/", re.sub(r":[^/]+", "x", path)}
    return any(fnmatch.fnmatch(c, g) for c in candidates for g in globs)


def _role_guarded_routes(routes: list[RouteCandidate], role: str) -> list[RouteCandidate]:
    return [r for r in routes if any(g.kind == "role" and role in g.roles for g in r.guards)]


def classify_roles(result: ParseResult) -> list[RoleInfo]:
    """Every role found in the code, with its kind and the reason."""
    roles: dict[str, str] = dict(result.role_values)
    for route in result.routes:
        for guard in route.guards:
            if guard.kind == "role":
                for rid in guard.roles:
                    roles.setdefault(rid, guard.source)
    signup_roles = {r.creates_user_role for r in result.routes if r.creates_user_role}

    out: list[RoleInfo] = [
        RoleInfo(
            id="guest",
            label=role_label("guest"),
            kind="guest",
            reason="tizimga kirmagan foydalanuvchi: ochiq sahifalar",
            source="builtin",
        )
    ]
    for rid in sorted(roles, key=lambda r: (r not in signup_roles, r)):
        source = roles[rid]
        label = role_label(rid, result.role_labels)
        low = rid.lower()
        guarded = _role_guarded_routes(result.routes, rid)
        admin_guard = any(g.admin and rid in g.roles for r in guarded for g in r.guards)
        manages = sorted(
            {
                r.path
                for r in guarded
                if r.kind == "api"
                and set(r.methods) & {"POST", "PUT", "PATCH", "DELETE"}
                and MANAGEMENT_SEGMENTS & set(r.path.lower().split("/"))
            }
        )
        if low in ADMIN_ROLE_NAMES or admin_guard:
            kind, reason = "excluded", "administrator yoki adminga o'xshash rol (nomi yoki guard'i)"
        elif manages:
            kind = "excluded"
            reason = "foydalanuvchilar, rollar yoki huquqlarni boshqaradi: " + ", ".join(
                manages[:3]
            )
        else:
            kind = "role"
            if rid in signup_roles:
                reason = "ro'yxatdan o'tganda beriladigan rol; faqat o'z ma'lumotlariga kiradi"
            elif guarded:
                reason = f"o'z sahifalari bor ({len(guarded)} ta yo'l), boshqaruv huquqlari yo'q"
            else:
                reason = "kodda topildi, alohida sahifalari yo'q"
        out.append(
            RoleInfo(
                id=rid,
                label=label,
                kind=kind,  # type: ignore[arg-type]
                reason=reason,
                source=source,
                self_signup=rid in signup_roles and kind == "role",
                description=(
                    "Saytda o'zi ro'yxatdan o'tadigan foydalanuvchi"
                    if rid in signup_roles
                    else "Sayt egasi beradigan xodim akkaunti"
                    if kind == "role"
                    else None
                ),
            )
        )
    return out


def classify_route(
    route: RouteCandidate, roles: list[RoleInfo], deny_globs: list[str]
) -> RouteInfo:
    usable = [r.id for r in roles if r.kind == "role"]
    excluded_ids = {r.id for r in roles if r.kind == "excluded"}

    def info(access: str, reason: str, allowed: list[str] | None = None) -> RouteInfo:
        return RouteInfo(
            path=route.path,
            kind=route.kind,
            methods=list(route.methods),
            access=access,  # type: ignore[arg-type]
            roles=allowed or [],
            reason=reason,
            source=route.source,
        )

    if deny_glob_match(route.path, deny_globs):
        return info("excluded", "deny_paths ro'yxatida (admin yo'li)")
    guards: list[GuardInfo] = route.guards
    if any(g.admin for g in guards):
        return info("excluded", "faqat administrator uchun: " + _exprs(guards, admin=True))
    if any(g.kind == "unknown" for g in guards):
        return info("excluded", "noaniq guard, default-deny: " + _exprs(guards))
    role_guards = [g for g in guards if g.kind == "role"]
    if role_guards:
        allowed = set(usable)
        for guard in role_guards:
            allowed &= set(guard.roles)
        if not allowed:
            named = {r for g in role_guards for r in g.roles}
            if named and named <= excluded_ids:
                return info(
                    "excluded",
                    "faqat chiqarib tashlangan rollar uchun: " + ", ".join(sorted(named)),
                )
            return info("excluded", "rol guard'i ma'lum rolga mos kelmadi: " + _exprs(guards))
        ordered = [r for r in usable if r in allowed]
        return info("roles", "rol tekshiruvi: " + _exprs(role_guards), ordered)
    if any(g.kind in {"auth", "ownership"} for g in guards):
        kinds = sorted({g.kind for g in guards})
        reason = "faqat kirish" if kinds == ["auth"] else "kirish va egalik tekshiruvi"
        return info("roles", reason + ": " + _exprs(guards), list(usable))
    return info("guest", "guard yo'q: ochiq yo'l")


def _exprs(guards: list[GuardInfo], admin: bool = False) -> str:
    chosen = [g for g in guards if g.admin] if admin else guards
    return ", ".join(dict.fromkeys(g.expr for g in chosen)) or "-"


def page_needs_auth_from_api(
    page: RouteInfo, api_routes: dict[str, RouteInfo], loads: list[str]
) -> RouteInfo:
    """An unguarded SPA page whose every load request needs a login is not a guest page."""
    if page.access != "guest" or not loads:
        return page
    infos = [api_routes.get(load) for load in loads]
    if infos and all(i is not None and i.access == "roles" for i in infos):
        roles: set[str] = set.intersection(*(set(i.roles) for i in infos if i is not None))
        if roles:
            return page.model_copy(
                update={
                    "access": "roles",
                    "roles": sorted(roles),
                    "reason": "sahifa so'rovlari kirishni talab qiladi (frontend guard'i yo'q)",
                }
            )
    return page
