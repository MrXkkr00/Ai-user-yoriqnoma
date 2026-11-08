"""zod and yup validation schemas -> form field rules (TZ FR-S3).

``z.object({ password: z.string().min(8) })`` and ``yup.object({ phone:
yup.string().matches(/^\\+998\\d{9}$/).required() })`` give rules in the blueprint format
(``min:8|max:64|regex:...``) and whether the field is required. A form gets them when its
component uses ``zodResolver(Schema)``, ``yupResolver(Schema)`` or Formik's
``validationSchema={Schema}``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from tree_sitter import Node

from yoriqnoma_scanner.ast_utils import node_text, string_value, walk

_OBJECT = re.compile(r"^\s*(?:z|yup|Yup)\.object\(|^\s*object\(")
_RESOLVER = re.compile(
    r"(?:zodResolver|yupResolver)\(\s*(\w+)\s*\)|validationSchema\s*[=:]\s*\{?\s*(\w+)"
)


@dataclass
class FieldRules:
    rules: list[str] = field(default_factory=list)
    required: bool | None = None  # None: the schema does not say
    email: bool = False


def _chain_rules(text: str, yup: bool) -> FieldRules:
    out = FieldRules(required=None if yup else True)
    for name, arg in re.findall(r"\.(\w+)\(([^()]*(?:\([^()]*\)[^()]*)*)\)", text):
        number = re.match(r"\s*(-?\d+(?:\.\d+)?)", arg)
        if name in {"min", "minLength"} and number:
            out.rules.append(f"min:{number.group(1)}")
        elif name in {"max", "maxLength"} and number:
            out.rules.append(f"max:{number.group(1)}")
        elif name == "length" and number:
            out.rules += [f"min:{number.group(1)}", f"max:{number.group(1)}"]
        elif name in {"regex", "matches"}:
            regex = re.match(r"\s*/(.+)/[a-z]*", arg)
            if regex:
                out.rules.append(f"regex:{regex.group(1)}")
        elif name == "email":
            out.email = True
        elif name in {"required", "nonempty"}:
            out.required = True
        elif name in {"optional", "nullable", "nullish", "notRequired"}:
            out.required = False
    return out


def schemas_in(root: Node) -> dict[str, dict[str, FieldRules]]:
    """Schema variable name -> field name -> rules, for every zod/yup object in a file."""
    found: dict[str, dict[str, FieldRules]] = {}
    for node in walk(root):
        if node.type != "variable_declarator":
            continue
        value = node.child_by_field_name("value")
        text = node_text(value)
        if value is None or not _OBJECT.match(text):
            continue
        yup = "yup" in text.lower().split("(")[0] or text.lstrip().startswith("object(")
        obj = next((n for n in walk(value) if n.type == "object"), None)
        if obj is None:
            continue
        fields: dict[str, FieldRules] = {}
        for pair in obj.named_children:
            if pair.type != "pair":
                continue
            key = pair.child_by_field_name("key")
            name = string_value(key) or node_text(key)
            fields[name] = _chain_rules(node_text(pair.child_by_field_name("value")), yup)
        found[node_text(node.child_by_field_name("name"))] = fields
    return found


def schema_used_in(body: Node) -> list[str]:
    """Schema names a component passes to a form library."""
    return [a or b for a, b in _RESOLVER.findall(node_text(body))]
