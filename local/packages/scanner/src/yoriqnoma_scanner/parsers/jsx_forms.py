"""JSX forms, buttons and links of each component (TZ FR-S3).

For every component: its forms (fields with label, type and HTML validation rules), the
buttons/links that send API requests (with the button that opens their modal, if any)
and the API requests made when the page loads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from tree_sitter import Node

from yoriqnoma_scanner.ast_utils import (
    jsx_attributes,
    jsx_name,
    line,
    node_text,
    parse,
    string_value,
    unwrap_expression,
    walk,
)
from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import (
    ActionBinding,
    ComponentInfo,
    LinkInfo,
    ParseResult,
)
from yoriqnoma_scanner.parsers.jsx_utils import component_definitions, expr_text, label_of
from yoriqnoma_scanner.parsers.zod_yup import FieldRules, schema_used_in, schemas_in
from yoriqnoma_schemas import Form, FormField, Target

API_OBJECTS = {"api", "axios", "http", "client", "request", "$http", "apiClient", "ky"}
API_METHODS = {
    "get": "GET",
    "post": "POST",
    "put": "PUT",
    "patch": "PATCH",
    "delete": "DELETE",
    "del": "DELETE",
}
FIELD_TAGS = {"input", "select", "textarea"}


@dataclass
class FuncInfo:
    calls: list[tuple[str, str]] = field(default_factory=list)  # (method, path)
    sets: list[tuple[str, str]] = field(default_factory=list)  # (state var, value)
    invokes: list[str] = field(default_factory=list)  # inner functions it calls


def api_calls(node: Node) -> list[tuple[str, str]]:
    """API requests inside ``node``: api.post("/x"), axios.get(`/x/${id}`), fetch(...)."""
    found: list[tuple[str, str]] = []
    for call in walk(node):
        if call.type != "call_expression":
            continue
        func = call.child_by_field_name("function")
        args = call.child_by_field_name("arguments")
        first = args.named_children[0] if args and args.named_children else None
        path = string_value(first)
        if func is None or path is None:
            continue
        if func.type == "member_expression":
            obj = node_text(func.child_by_field_name("object"))
            prop = node_text(func.child_by_field_name("property"))
            if obj in API_OBJECTS and prop in API_METHODS:
                found.append((API_METHODS[prop], path))
        elif node_text(func) == "fetch":
            method = "GET"
            if args is not None and len(args.named_children) > 1:
                options = args.named_children[1]
                match = re.search(r"method\s*:\s*['\"](\w+)['\"]", node_text(options))
                if match:
                    method = match.group(1).upper()
            found.append((method, path))
    return found


class JsxFormsParser:
    name = "jsx-forms"

    def __init__(self, i18n: dict[str, str] | None = None) -> None:
        self.i18n = i18n or {}

    def applies(self, project: ProjectInfo) -> bool:
        return "react" in project.stacks

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        result = ParseResult()
        roots: list[tuple[str, Node]] = []
        self.schemas: dict[str, dict[str, FieldRules]] = {}
        for path in project.js_files:
            text = fs.read_text(path)
            if text is None:
                continue
            root = parse(text, path.suffix)
            if "object(" in text:
                self.schemas.update(schemas_in(root))
            if "<" in text:
                roots.append((fs.rel(path), root))
        for rel, root in roots:
            for name, body in component_definitions(root).items():
                info = self._component(name, body, rel)
                self._apply_schemas(info, body)
                result.components[name] = info
                result.forms.extend(info.forms)
        return result

    def _apply_schemas(self, info: ComponentInfo, body: Node) -> None:
        """zod / yup rules of the schema the component's form library validates with."""
        rules: dict[str, FieldRules] = {}
        for schema in schema_used_in(body):
            rules.update(self.schemas.get(schema, {}))
        if not rules:
            return
        for i, form in enumerate(info.forms):
            fields = []
            for ff in form.fields:
                found = rules.get(ff.name)
                if found is None:
                    fields.append(ff)
                    continue
                merged = merge_rule_lists(ff.rules, found.rules)
                fields.append(
                    ff.model_copy(
                        update={
                            "rules": merged,
                            "required": found.required
                            if found.required is not None
                            else ff.required,
                            "type": "email" if found.email and ff.type == "text" else ff.type,
                        }
                    )
                )
            info.forms[i] = form.model_copy(update={"fields": fields})

    # --- one component ------------------------------------------------------------

    def _component(self, name: str, body: Node, rel: str) -> ComponentInfo:
        info = ComponentInfo(name=name, file=rel)
        setters = self._state_setters(body)
        funcs = self._inner_functions(body, setters)
        info.loads = self._loads(body, funcs)
        openers: dict[tuple[str, str], str] = {}
        pending: list[tuple[ActionBinding, list[tuple[str, str]]]] = []
        self._walk_jsx(body, [], name, rel, funcs, setters, info, openers, pending)
        for binding, conditions in pending:
            for cond in conditions:
                if cond in openers:
                    binding.opener = openers[cond]
                    break
            info.actions.append(binding)
        return info

    @staticmethod
    def _state_setters(body: Node) -> dict[str, str]:
        """setX -> x for ``const [x, setX] = useState(...)``."""
        out: dict[str, str] = {}
        for node in walk(body):
            if node.type != "variable_declarator":
                continue
            pattern = node.child_by_field_name("name")
            value = node.child_by_field_name("value")
            if pattern is None or value is None or pattern.type != "array_pattern":
                continue
            if "useState" not in node_text(value.child_by_field_name("function")):
                continue
            names = [node_text(n) for n in pattern.named_children]
            if len(names) == 2:
                out[names[1]] = names[0]
        return out

    def _inner_functions(self, body: Node, setters: dict[str, str]) -> dict[str, FuncInfo]:
        funcs: dict[str, FuncInfo] = {}
        for node in walk(body):
            name: str | None = None
            fbody: Node | None = None
            if node.type == "function_declaration" and node is not body:
                name = node_text(node.child_by_field_name("name"))
                fbody = node.child_by_field_name("body")
            elif node.type == "variable_declarator":
                value = node.child_by_field_name("value")
                if value is not None and value.type in {"arrow_function", "function_expression"}:
                    name = node_text(node.child_by_field_name("name"))
                    fbody = value
            if name and fbody is not None:
                funcs[name] = self._func_info(fbody, setters)
        return funcs

    @staticmethod
    def _func_info(node: Node, setters: dict[str, str]) -> FuncInfo:
        info = FuncInfo(calls=api_calls(node))
        for call in walk(node):
            if call.type != "call_expression":
                continue
            fname = node_text(call.child_by_field_name("function"))
            args = call.child_by_field_name("arguments")
            first = args.named_children[0] if args and args.named_children else None
            if fname in setters and first is not None:
                value = string_value(first)
                if value is None and first.type in {"true", "false", "number"}:
                    value = node_text(first)
                if value is not None:
                    info.sets.append((setters[fname], value))
            elif re.fullmatch(r"[a-z]\w*", fname):
                info.invokes.append(fname)
        return info

    @staticmethod
    def _expand(fi: FuncInfo, funcs: dict[str, FuncInfo], depth: int = 0) -> list[tuple[str, str]]:
        calls = list(fi.calls)
        if depth < 3:
            for name in fi.invokes:
                if name in funcs and funcs[name] is not fi:
                    calls += JsxFormsParser._expand(funcs[name], funcs, depth + 1)
        return calls

    def _loads(self, body: Node, funcs: dict[str, FuncInfo]) -> list[str]:
        out: list[str] = []
        for call in walk(body):
            if call.type != "call_expression":
                continue
            if node_text(call.child_by_field_name("function")) not in {"useEffect", "onMounted"}:
                continue
            args = call.child_by_field_name("arguments")
            if not args or not args.named_children:
                continue
            fi = self._func_info(args.named_children[0], {})
            for method, path in self._expand(fi, funcs):
                if method == "GET" and f"GET {path}" not in out:
                    out.append(f"GET {path}")
        return out

    # --- JSX walk -----------------------------------------------------------------

    def _handler(
        self, value: Node | None, funcs: dict[str, FuncInfo], setters: dict[str, str]
    ) -> FuncInfo | None:
        value = unwrap_expression(value)
        if value is None:
            return None
        if value.type == "identifier":
            return funcs.get(node_text(value))
        if value.type in {"arrow_function", "function_expression"}:
            return self._func_info(value, setters)
        return None

    def _walk_jsx(
        self,
        node: Node,
        conditions: list[tuple[str, str]],
        component: str,
        rel: str,
        funcs: dict[str, FuncInfo],
        setters: dict[str, str],
        info: ComponentInfo,
        openers: dict[tuple[str, str], str],
        pending: list[tuple[ActionBinding, list[tuple[str, str]]]],
    ) -> None:
        if (
            node.type == "binary_expression"
            and node_text(node.child_by_field_name("operator")) == "&&"
        ):
            cond = self._condition(node.child_by_field_name("left"))
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None:
                self._walk_jsx(
                    left, conditions, component, rel, funcs, setters, info, openers, pending
                )
            if right is not None:
                extra = [cond] if cond else []
                self._walk_jsx(
                    right,
                    [*conditions, *extra],
                    component,
                    rel,
                    funcs,
                    setters,
                    info,
                    openers,
                    pending,
                )
            return
        if node.type in {"jsx_element", "jsx_self_closing_element"}:
            tag = jsx_name(node)
            src = f"{rel}:{line(node)}"
            attrs = jsx_attributes(node)
            if tag == "form":
                self._form(node, component, rel, funcs, setters, info, conditions, pending)
            elif (
                tag == "button"
                or attrs.get("role") is not None
                and expr_text(attrs.get("role"), {}) == "button"
            ):
                handler = self._handler(attrs.get("onClick"), funcs, setters)
                label = label_of(node, self.i18n)
                if handler is not None and label:
                    calls = [c for c in self._expand(handler, funcs) if c[0] != "GET"]
                    for method, path in calls[:1]:
                        pending.append(
                            (
                                ActionBinding(
                                    component,
                                    "button",
                                    method,
                                    path,
                                    label,
                                    src,
                                    in_modal=bool(conditions),
                                ),
                                list(conditions),
                            )
                        )
                    if not calls:
                        for cond in handler.sets:
                            openers.setdefault(cond, label)
            elif tag in {"a", "Link", "NavLink"}:
                target = unwrap_expression(attrs.get("href") or attrs.get("to"))
                to = string_value(target)
                label = label_of(node, self.i18n)
                if to and label:
                    if to.startswith("/api/") or "download" in attrs:
                        pending.append(
                            (
                                ActionBinding(
                                    component,
                                    "link",
                                    "GET",
                                    to,
                                    label,
                                    src,
                                    in_modal=bool(conditions),
                                ),
                                list(conditions),
                            )
                        )
                    elif to.startswith("/"):
                        info.links.append(LinkInfo(component, label, to.split("?")[0], src))
        for child in node.named_children:
            self._walk_jsx(
                child, conditions, component, rel, funcs, setters, info, openers, pending
            )

    @staticmethod
    def _condition(node: Node | None) -> tuple[str, str] | None:
        node = unwrap_expression(node)
        if node is None:
            return None
        if node.type == "binary_expression":
            op = node_text(node.child_by_field_name("operator"))
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if op in {"===", "=="} and left is not None and right is not None:
                value = string_value(right)
                if value is not None and left.type == "identifier":
                    return node_text(left), value
            if op == "&&":
                return JsxFormsParser._condition(node.child_by_field_name("right"))
        if node.type == "identifier":
            return node_text(node), "true"
        return None

    def _form(
        self,
        node: Node,
        component: str,
        rel: str,
        funcs: dict[str, FuncInfo],
        setters: dict[str, str],
        info: ComponentInfo,
        conditions: list[tuple[str, str]],
        pending: list[tuple[ActionBinding, list[tuple[str, str]]]],
    ) -> None:
        attrs = jsx_attributes(node)
        handler = self._handler(attrs.get("onSubmit"), funcs, setters)
        handler_name = node_text(unwrap_expression(attrs.get("onSubmit")))
        labels = self._labels(node)
        fields: list[FormField] = []
        submit = ""
        for el in walk(node):
            if el.type not in {"jsx_element", "jsx_self_closing_element"}:
                continue
            tag = jsx_name(el)
            if tag in FIELD_TAGS:
                ff = self._field(el, labels)
                if ff is not None:
                    fields.append(ff)
            elif tag == "button":
                battrs = jsx_attributes(el)
                btype = expr_text(battrs.get("type"), {}) if "type" in battrs else "submit"
                if btype == "submit" and not submit:
                    submit = label_of(el, self.i18n)
        calls = self._expand(handler, funcs) if handler else []
        writes = [c for c in calls if c[0] != "GET"] or calls
        api = f"{writes[0][0]} {writes[0][1]}" if writes else None
        form_id = f"{component}.{handler_name or 'form'}"
        if not fields and not submit:
            return
        form = Form(
            id=form_id,
            page_path="",  # filled in when the component is matched to a route
            fields=fields,
            submit=Target(role="button", name=submit)
            if submit
            else Target(css="form [type=submit]"),
            api=api,
        )
        info.forms.append(form)
        if writes:
            method, path = writes[0]
            pending.append(
                (
                    ActionBinding(
                        component,
                        "form",
                        method,
                        path,
                        submit or "submit",
                        f"{rel}:{line(node)}",
                        in_modal=bool(conditions),
                        form_id=form_id,
                    ),
                    list(conditions),
                )
            )

    def _labels(self, form: Node) -> dict[str, str]:
        """input id -> label text, from <label htmlFor> in the form."""
        out: dict[str, str] = {}
        for el in walk(form):
            if el.type in {"jsx_element", "jsx_self_closing_element"} and jsx_name(el) == "label":
                attrs = jsx_attributes(el)
                target = attrs.get("htmlFor") or attrs.get("for")
                key = string_value(unwrap_expression(target)) if target is not None else None
                text = label_of(el, self.i18n)
                if key and text:
                    out[key] = text
                elif text:
                    for inner in walk(el):
                        if (
                            inner.type in {"jsx_element", "jsx_self_closing_element"}
                            and jsx_name(inner) in FIELD_TAGS
                        ):
                            iattrs = jsx_attributes(inner)
                            name = string_value(unwrap_expression(iattrs.get("name")))
                            if name:
                                out[f"name:{name}"] = text
        return out

    def _field(self, el: Node, labels: dict[str, str]) -> FormField | None:
        attrs = jsx_attributes(el)
        tag = jsx_name(el)

        def attr(key: str) -> str | None:
            if key not in attrs:
                return None
            value = unwrap_expression(attrs[key])
            if value is None:
                return "true"
            text = string_value(value)
            if text is not None:
                return text
            if value.type in {"number", "true", "false"}:
                return node_text(value)
            return None

        name = attr("name")
        el_id = attr("id")
        registered = _registered(el)  # react-hook-form: {...register("email", {...})}
        if registered is not None:
            name = name or registered[0]
        if not name and not el_id:
            return None
        ftype = (
            "select"
            if tag == "select"
            else "textarea"
            if tag == "textarea"
            else (attr("type") or "text")
        )
        if ftype in {"hidden", "submit", "button"}:
            return None
        rules: list[str] = []
        for key, rule in (
            ("minLength", "min"),
            ("maxLength", "max"),
            ("min", "min"),
            ("max", "max"),
            ("pattern", "regex"),
        ):
            value = attr(key)
            if value is not None:
                rules.append(f"{rule}:{value}")
        required = attr("required") not in (None, "false")
        if registered is not None:
            rules += registered[1]
            required = required or registered[2]
        label = labels.get(el_id or "") or labels.get(f"name:{name}")
        options = self._options(el) if tag == "select" else None
        return FormField(
            name=name or el_id or "",
            label=label,
            type=ftype,
            required=required,
            rules="|".join(rules) or None,
            options=options,
        )

    @staticmethod
    def _options(select: Node) -> list[str] | None:
        values: list[str] = []
        for el in walk(select):
            if el.type in {"jsx_element", "jsx_self_closing_element"} and jsx_name(el) == "option":
                value = string_value(unwrap_expression(jsx_attributes(el).get("value")))
                if value is not None:
                    values.append(value)
            elif el.type == "call_expression":
                func = el.child_by_field_name("function")
                if func is not None and func.type == "member_expression":
                    obj = func.child_by_field_name("object")
                    if obj is not None and obj.type == "array":
                        values += [v for c in obj.named_children if (v := string_value(c))]
        return values or None


def _registered(el: Node) -> tuple[str, list[str], bool] | None:
    """``{...register("email", { required: true, minLength: 8 })}`` -> name, rules, required."""
    target = el.child_by_field_name("open_tag") if el.type == "jsx_element" else el
    if target is None:
        return None
    for child in target.named_children:
        text = node_text(child)
        match = re.match(
            r"\{\s*\.\.\.\s*register\(\s*['\"]([\w.]+)['\"]\s*(?:,(.*))?\)\s*\}$", text, re.S
        )
        if child.type != "jsx_expression" or not match:
            continue
        options = match.group(2) or ""
        rules: list[str] = []
        for key, rule in (
            ("minLength", "min"),
            ("maxLength", "max"),
            ("min", "min"),
            ("max", "max"),
        ):
            found = re.search(rf"\b{key}\s*:\s*(?:\{{\s*value\s*:\s*)?(\d+)", options)
            if found:
                rules.append(f"{rule}:{found.group(1)}")
        pattern = re.search(r"pattern\s*:\s*(?:\{\s*value\s*:\s*)?/(.+?)/[a-z]*", options)
        if pattern:
            rules.append(f"regex:{pattern.group(1)}")
        required = bool(re.search(r"required\s*:\s*(true|['\"])", options))
        return match.group(1).split(".")[-1], rules, required
    return None


def merge_rule_lists(front: str | None, schema: list[str]) -> str | None:
    """HTML attribute rules overridden by the schema's (``min:8|regex:...``)."""
    merged: dict[str, str] = {}
    for rule in [*(front or "").split("|"), *schema]:
        key, _, value = rule.partition(":")
        if key:
            merged[key] = value
    return "|".join(f"{k}:{v}" for k, v in merged.items()) or None
