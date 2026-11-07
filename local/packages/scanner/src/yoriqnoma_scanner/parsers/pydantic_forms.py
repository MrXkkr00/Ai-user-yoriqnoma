"""Pydantic request models -> form fields with validation rules (TZ FR-S3)."""

from __future__ import annotations

import ast

from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import ParseResult
from yoriqnoma_scanner.pyindex import PyIndex, PyModule, call_name, dotted_name, kwarg
from yoriqnoma_schemas import FormField

RULE_KEYS = {
    "min_length": "min",
    "max_length": "max",
    "ge": "min",
    "gt": "gt",
    "le": "max",
    "lt": "lt",
    "pattern": "regex",
    "regex": "regex",
}


def field_type(name: str, annotation: str) -> str:
    low = name.lower()
    ann = annotation.lower()
    if ann == "bool":
        return "checkbox"
    if "password" in low or "secretstr" in ann:
        return "password"
    if "email" in low or "emailstr" in ann:
        return "email"
    if "phone" in low or "tel" == low:
        return "tel"
    if ann in {"int", "float", "decimal"} or ann.startswith(("int", "float")):
        return "number"
    if ann == "bool":
        return "checkbox"
    if "date" in ann:
        return "date"
    if "url" in ann:
        return "url"
    return "text"


class PydanticFormsParser:
    name = "pydantic"

    def applies(self, project: ProjectInfo) -> bool:
        return bool(project.python_files)

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        index = PyIndex(fs, project.python_files)
        result = ParseResult()
        for module in index.modules.values():
            for name, cls in module.classes.items():
                bases = index.class_bases(module, cls)
                if "BaseModel" not in bases or {"DeclarativeBase", "SQLModel"} & bases:
                    continue
                fields = self._fields(index, module, cls)
                if fields:
                    result.request_models[name] = fields
        return result

    def _fields(self, index: PyIndex, module: PyModule, cls: ast.ClassDef) -> list[FormField]:
        out: list[FormField] = []
        for node in cls.body:
            if not (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)):
                continue
            name = node.target.id
            if name.startswith("_") or name == "model_config":
                continue
            annotation = ast.unparse(node.annotation)
            optional = "None" in annotation or "Optional" in annotation
            required = node.value is None and not optional
            rules: list[str] = []
            value = node.value
            if isinstance(value, ast.Call) and call_name(value).endswith("Field"):
                first = value.args[0] if value.args else kwarg(value, "default")
                has_default = first is not None and not (
                    isinstance(first, ast.Constant) and first.value is Ellipsis
                )
                has_factory = kwarg(value, "default_factory") is not None
                required = not (has_default or has_factory or optional)
                for kw in value.keywords:
                    key = RULE_KEYS.get(kw.arg or "")
                    if key is None:
                        continue
                    if isinstance(kw.value, ast.Constant) and isinstance(
                        kw.value.value, int | float
                    ):
                        rules.append(f"{key}:{kw.value.value}")
                    else:
                        text = index.string_constant(module, kw.value)
                        if text is not None:
                            rules.append(f"{key}:{text}")
            options = self._literal_options(node.annotation)
            ftype = "select" if options else field_type(name, annotation.split("[")[0])
            if ftype == "number" and annotation.startswith("bool"):
                ftype = "checkbox"
            out.append(
                FormField(
                    name=name,
                    label=None,
                    type=ftype,
                    required=required,
                    rules="|".join(rules) or None,
                    options=options,
                )
            )
        return out

    @staticmethod
    def _literal_options(ann: ast.expr) -> list[str] | None:
        if isinstance(ann, ast.Subscript) and dotted_name(ann.value).endswith("Literal"):
            elts = ann.slice.elts if isinstance(ann.slice, ast.Tuple) else [ann.slice]
            values = [str(e.value) for e in elts if isinstance(e, ast.Constant)]
            return values or None
        return None
