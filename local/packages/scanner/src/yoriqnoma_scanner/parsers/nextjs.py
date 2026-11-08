"""Next.js: file-based routes, middleware and API handlers (TZ FR-S3, FR-S4, T29).

Pages router: ``pages/orders/[id].tsx`` -> ``/orders/:id``; ``pages/api/**`` are API routes
(methods from ``req.method === 'POST'`` checks). App router: ``app/(shop)/orders/page.tsx``
-> ``/orders``; ``route.ts`` exports ``GET`` / ``POST``... Route groups, parallel slots and
private folders are skipped. Guards: ``middleware.ts`` matchers, ``layout`` files, and in
pages and handlers: session checks with a redirect or 401, role comparisons, ``isAdmin``.
Page components (forms, buttons, links) come from the JSX parser by component name.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from tree_sitter import Node

from yoriqnoma_scanner.ast_utils import node_text, parse, walk
from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import (
    SIGNUP_DEFAULT,
    GuardInfo,
    ParseResult,
    RouteCandidate,
)
from yoriqnoma_scanner.parsers.express_routes import _role_values, _status_logic

PAGE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}
HTTP = ("GET", "POST", "PUT", "PATCH", "DELETE")
SESSION = re.compile(
    r"getServerSession\(|\bauth\(\)|useSession\(|currentUser\(\)|getSession\(|"
    r"cookies\(\)\.get\(|getToken\(|withAuth|clerk|supabase\.auth\.getUser\(",
    re.I,
)
REFUSES = re.compile(
    r"redirect\(|notFound\(|status\(\s*40[13]\s*\)|status\s*:\s*40[13]|required\s*:\s*true|"
    r"Unauthorized|Forbidden|signIn\(",
)
ADMIN_FLAG = re.compile(r"\b(isAdmin|is_admin|isSuperuser|isStaff)\b")
OWNER = re.compile(
    r"(userId|ownerId|authorId|user_id)\s*:\s*(session\.user|user|currentUser|token)\??\.(id|sub)\b"
    r"|\.(userId|ownerId|authorId)\s*!==?\s*(session\.user|user|token)\??\.(id|sub)\b"
)


def segment_path(segments: list[str]) -> str | None:
    """Folder/file names -> a route path; None for private folders (``_lib``)."""
    out: list[str] = []
    for seg in segments:
        if seg.startswith("_"):
            return None
        if (seg.startswith("(") and seg.endswith(")")) or seg.startswith("@"):
            continue  # route groups and parallel slots are not in the URL
        match = re.fullmatch(r"\[\[?(?:\.\.\.)?(\w+)\]?\]", seg)
        out.append(f":{match.group(1)}" if match else seg)
    return "/" + "/".join(out)


class NextParser:
    name = "next"

    def applies(self, project: ProjectInfo) -> bool:
        return "next" in project.stacks

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        self.fs = fs
        self.result = ParseResult()
        files = [p for p in project.js_files if p.suffix.lower() in PAGE_SUFFIXES]
        self.texts = {p: fs.read_text(p) or "" for p in files}
        self.matchers = self._middleware(files)
        for path in files:
            parts = PurePosixPath(fs.rel(path)).parts
            if "pages" in parts:
                self._pages_route(path, list(parts[parts.index("pages") + 1 :]))
            elif "app" in parts and path.stem in {"page", "route"}:
                self._app_route(path, list(parts[parts.index("app") + 1 : -1]))
        return self.result

    # --- routes ----------------------------------------------------------------------

    def _pages_route(self, path: Path, rest: list[str]) -> None:
        stem = Path(rest[-1]).stem
        if stem.startswith("_") or stem in {"404", "500"}:
            return
        segments = [*rest[:-1], *([] if stem == "index" else [stem])]
        route = segment_path(segments)
        if route is None:
            return
        text = self.texts[path]
        if segments and segments[0] == "api":
            methods = sorted(set(re.findall(r"req\.method\s*[!=]==?\s*['\"](\w+)['\"]", text)))
            self._api(path, route, [m.upper() for m in methods] or ["GET"], text)
        else:
            self._page(path, route, text, [])

    def _app_route(self, path: Path, folders: list[str]) -> None:
        route = segment_path(folders)
        if route is None:
            return
        text = self.texts[path]
        if path.stem == "route":
            methods = [
                m for m in HTTP if re.search(rf"export\s+(async\s+)?(function|const)\s+{m}\b", text)
            ]
            self._api(path, route, methods or ["GET"], text)
            return
        layouts = [
            self.texts[layout]
            for i in range(len(folders) + 1)
            for layout in self.texts
            if layout.stem == "layout" and self._is_app_dir(layout, folders[:i])
        ]
        self._page(path, route, text, layouts)

    def _is_app_dir(self, layout: Path, folders: list[str]) -> bool:
        parts = PurePosixPath(self.fs.rel(layout)).parts
        if "app" not in parts:
            return False
        return list(parts[parts.index("app") + 1 : -1]) == folders

    def _page(self, path: Path, route: str, text: str, layouts: list[str]) -> None:
        src = self.fs.rel(path)
        guards = self._matcher_guards(route, src)
        for source in (*layouts, text):
            guards += self._text_guards(source, src)
        self.result.routes.append(
            RouteCandidate(
                path=route,
                kind="page",
                methods=["GET"],
                guards=_dedupe(guards),
                source=src,
                component=_default_export(path, text),
            )
        )

    def _api(self, path: Path, route: str, methods: list[str], text: str) -> None:
        src = self.fs.rel(path)
        root = parse(text, path.suffix)
        for method in methods:
            handler = _handler(root, method) or root  # guards: the whole handler
            body = _method_block(handler, method) or handler  # status logic: its branch
            body_text = node_text(body)
            guards = self._matcher_guards(route, src) + self._text_guards(node_text(handler), src)
            if OWNER.search(body_text):
                guards.append(GuardInfo("ownership", "egalik tekshiruvi", src))
            sets, requires = _status_logic(body)
            created = None
            if method == "POST" and re.search(r"\buser\.create\(|\bUser\.create\(", body_text):
                role = re.search(r"role\s*:\s*['\"](\w+)['\"]", body_text)
                created = role.group(1) if role else SIGNUP_DEFAULT
            self.result.routes.append(
                RouteCandidate(
                    path=route,
                    kind="api",
                    methods=[method],
                    guards=_dedupe(guards),
                    source=src,
                    handler=method,
                    status_sets=sets,
                    status_requires=requires,
                    downloads="attachment" in body_text,
                    creates_user_role=created if not guards else None,
                )
            )

    # --- guards ------------------------------------------------------------------------

    def _middleware(self, files: list[Path]) -> list[tuple[str, str]]:
        """(path prefix, middleware text) for every ``config.matcher`` entry."""
        out: list[tuple[str, str]] = []
        for path in files:
            if path.stem != "middleware" or len(PurePosixPath(self.fs.rel(path)).parts) > 2:
                continue
            text = self.texts[path]
            block = re.search(r"matcher\s*:\s*(\[[^\]]*\]|['\"][^'\"]+['\"])", text)
            for pattern in re.findall(r"['\"]([^'\"]+)['\"]", block.group(1) if block else ""):
                prefix = re.split(r"/:|\(|\*", pattern)[0].rstrip("/") or "/"
                out.append((prefix, text))
        return out

    def _matcher_guards(self, route: str, src: str) -> list[GuardInfo]:
        guards: list[GuardInfo] = []
        for prefix, text in self.matchers:
            if prefix != "/" and not (route == prefix or route.startswith(prefix + "/")):
                continue
            expr = f"middleware matcher {prefix}"
            if "admin" in prefix.lower():
                guards.append(GuardInfo("role", expr, src, ["admin"], admin=True))
            elif SESSION.search(text) or "token" in text or "next-auth/middleware" in text:
                guards.append(GuardInfo("auth", expr, src))
        return guards

    @staticmethod
    def _text_guards(text: str, src: str) -> list[GuardInfo]:
        guards: list[GuardInfo] = []
        if not REFUSES.search(text):
            return guards
        if ADMIN_FLAG.search(text):
            guards.append(GuardInfo("role", "isAdmin", src, ["admin"], admin=True))
        root = parse(text, ".tsx")
        for node in walk(root):
            if node.type != "if_statement":
                continue
            cond = node.child_by_field_name("condition")
            cons = node_text(node.child_by_field_name("consequence"))
            if cond is None or not REFUSES.search(cons):
                continue
            roles = _role_values(cond)
            if roles:
                admin = any("admin" in r.lower() for r in roles)
                guards.append(GuardInfo("role", node_text(cond)[:80], src, roles, admin=admin))
        if SESSION.search(text):
            guards.append(GuardInfo("auth", "session check", src))
        return guards


def _dedupe(guards: list[GuardInfo]) -> list[GuardInfo]:
    seen: set[tuple[str, str]] = set()
    out: list[GuardInfo] = []
    for g in guards:
        key = (g.kind, ",".join(g.roles))
        if key not in seen:
            seen.add(key)
            out.append(g)
    return out


def _default_export(path: Path, text: str) -> str | None:
    match = re.search(r"export\s+default\s+(?:async\s+)?function\s+(\w+)", text) or re.search(
        r"export\s+default\s+(\w+)\s*;?\s*$", text, re.M
    )
    return match.group(1) if match else None


def _method_block(root: Node, method: str) -> Node | None:
    """``if (req.method === 'POST') { ... }`` in a pages-router API handler."""
    for node in walk(root):
        if node.type != "if_statement":
            continue
        cond = node_text(node.child_by_field_name("condition"))
        if re.search(rf"req\.method\s*===?\s*['\"]{method}['\"]", cond, re.I):
            return node.child_by_field_name("consequence")
    return None


def _handler(root: Node, method: str) -> Node | None:
    """The exported ``GET`` / ``POST`` function of an app-router ``route.ts``."""
    for node in walk(root):
        if (
            node.type == "function_declaration"
            and node_text(node.child_by_field_name("name")) == method
        ):
            return node
        if (
            node.type == "variable_declarator"
            and node_text(node.child_by_field_name("name")) == method
        ):
            return node.child_by_field_name("value")
    return None
