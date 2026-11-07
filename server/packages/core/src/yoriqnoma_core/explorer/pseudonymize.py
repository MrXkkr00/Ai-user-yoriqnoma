"""Replace other people's data with stable fakes before any screenshot (TZ FR-E10, SEC-7).

Two layers share one ``PrivacyLedger``:

* network: JSON answers of the site's own API are rewritten before the page sees them;
* DOM: what is still on the page (server-rendered text, structural names) is decided by
  zone — own and generated values stay; organization and published values stay and are
  recorded as public; user content and everything else is replaced. Unknown -> foreign.

Real foreign values exist only in memory while a page is processed; they are never
written to capture.json, images, logs or the bundle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from yoriqnoma_core.explorer.datagen import DataGen
from yoriqnoma_core.safety.pii import (
    NAME_HEADERS,
    find_pii,
    is_pii_field,
    is_site_email,
    normalize_value,
)
from yoriqnoma_schemas import Entity

TEXT_KEYS = {"text", "body", "comment", "content", "message", "review", "review_text", "note"}
NEUTRAL_AVATAR = (
    "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'>"
    "<circle cx='32' cy='32' r='32' fill='%23c9ced6'/><circle cx='32' cy='25' r='11' "
    "fill='%23f4f5f7'/><ellipse cx='32' cy='54' rx='19' ry='13' fill='%23f4f5f7'/></svg>"
)
PUBLIC_ZONES = {"org", "editorial"}
REPLACE_ZONES = {"user_content", "other"}


def kind_for_key(key: str) -> str:
    k = key.lower()
    if "email" in k:
        return "email"
    if any(x in k for x in ("phone", "tel", "mobile")):
        return "phone"
    if "address" in k:
        return "address"
    if "card" in k:
        return "card"
    if "passport" in k:
        return "passport"
    if "pinfl" in k or "jshshir" in k:
        return "pinfl"
    if "avatar" in k or "photo" in k:
        return "avatar"
    if "birth" in k:
        return "date"
    return "name"


@dataclass
class PrivacyLedger:
    datagen: DataGen
    base_url: str
    entities: dict[str, Entity]
    self_signup_roles: set[str]
    org_domains: list[str] = field(default_factory=list)
    test_values: set[str] = field(default_factory=set)
    public_values: set[str] = field(default_factory=set)
    own_ids: dict[str, set[str]] = field(default_factory=dict)
    editorial_is_ugc: bool = False
    pending: dict[str, int] = field(default_factory=dict)  # network counters since last state

    def ignore(self) -> set[str]:
        return self.test_values | self.public_values | self.datagen.generated

    def _own_norms(self) -> set[str]:
        out: set[str] = set()
        for value in self.test_values | self.datagen.generated:
            for kind in ("email", "phone", "name"):
                out.add(normalize_value(kind, value))
        return {v for v in out if v}

    def count(self, key: str, n: int = 1) -> None:
        self.pending[key] = self.pending.get(key, 0) + n

    def take_counts(self) -> dict[str, int]:
        counts, self.pending = self.pending, {}
        return counts

    def is_org_email(self, email: str) -> bool:
        if is_site_email(email, self.base_url):
            return True
        domain = email.rsplit("@", 1)[-1].lower()
        return any(domain == d or domain.endswith("." + d) for d in self.org_domains)

    # --- network layer --------------------------------------------------------------

    def entity_for_path(self, path: str) -> str | None:
        segments = [s for s in path.split("/") if s and not s.isdigit()]
        for seg in reversed(segments):
            for name in self.entities:
                plural = name[:-1] + "ies" if name.endswith("y") else name + "s"
                if seg in {name, plural}:
                    return name
        return None

    def _published(self, entity: str | None) -> bool:
        ent = self.entities.get(entity or "")
        if ent is None:
            return False
        return ent.owner_field is None and not set(ent.created_by) & self.self_signup_roles

    def _ugc(self, entity: str | None) -> bool:
        ent = self.entities.get(entity or "")
        return ent is not None and bool(set(ent.created_by) & self.self_signup_roles)

    def transform_json(self, data: Any, path: str) -> Any:
        """Rewrite foreign records in an API answer; learn the test accounts' own values."""
        entity = self.entity_for_path(path)
        own_norms = self._own_norms()
        return self._walk(data, entity, own_norms)

    def _walk(self, data: Any, entity: str | None, own: set[str]) -> Any:
        if isinstance(data, list):
            return [self._walk(item, entity, own) for item in data]
        if not isinstance(data, dict):
            return data
        record = {
            k: self._walk(v, entity, own) if isinstance(v, dict | list) else v
            for k, v in data.items()
        }
        pii_keys = [
            k for k, v in record.items() if isinstance(v, str) and v and self._is_pii_key(k, entity)
        ]
        if not pii_keys and not (self._ugc(entity) and set(record) & TEXT_KEYS):
            return record
        if self._is_own(record, entity, own, pii_keys):
            for key in pii_keys:
                self.test_values.add(str(record[key]))
            return record
        if self._published(entity):
            for key in pii_keys:
                self.public_values.add(str(record[key]))
            self.count("editorial:kept", len(pii_keys))
            return record
        record_key = self._record_key(record, pii_keys)
        for key in pii_keys:
            value = str(record[key])
            kind = kind_for_key(key)
            if kind == "email" and self.is_org_email(value):
                self.public_values.add(value)
                self.count("org:kept")
                continue
            if kind == "avatar":
                record[key] = NEUTRAL_AVATAR
            elif kind == "date":
                record[key] = "1990-01-01"
            else:
                record[key] = self.datagen.substitute(kind, value, record_key)
            self.count("other:substituted")
        if self._ugc(entity):
            for key in set(record) & TEXT_KEYS:
                value = record[key]
                if isinstance(value, str) and value.strip():
                    record[key] = self.datagen.substitute("text", value)
                    self.count("user_content:substituted")
        return record

    def _is_pii_key(self, key: str, entity: str | None) -> bool:
        ent = self.entities.get(entity or "")
        if ent is not None and key in ent.pii_fields:
            return True
        if key.lower() == "name":
            return entity in {"user", "customer", "client", "member", "profile", "person"}
        return is_pii_field(key)

    def _is_own(
        self, record: dict[str, Any], entity: str | None, own: set[str], pii_keys: list[str]
    ) -> bool:
        rid = record.get("id")
        if rid is not None and entity and str(rid) in self.own_ids.get(entity, set()):
            return True
        for key in pii_keys:
            value = str(record[key])
            kind = kind_for_key(key)
            if kind in {"email", "phone"} and normalize_value(kind, value) in own:
                return True
        return False

    @staticmethod
    def _record_key(record: dict[str, Any], pii_keys: list[str]) -> str:
        for wanted in ("email", "phone", "name"):
            for key in pii_keys:
                if kind_for_key(key) == wanted:
                    return str(record[key])
        return str(record.get("id", ""))

    # --- DOM layer ------------------------------------------------------------------

    def decide_dom(self, scan: dict[str, Any]) -> DomDecision:
        ignore = self.ignore()
        own = self._own_norms()
        decision = DomDecision()
        nodes: list[dict[str, Any]] = scan.get("nodes", [])
        blocks: dict[int, str] = {}
        # record key per block: the first personal value found in it
        for node in nodes:
            block = int(node.get("block", -1))
            if block < 0 or block in blocks:
                continue
            for m in find_pii(str(node["text"]), ignore):
                if m.kind in {"email", "phone", "name"}:
                    blocks[block] = m.value
                    break
            else:
                if node.get("structural") == "name" and str(node["text"]).strip():
                    blocks[block] = str(node["text"]).strip()
        for node in nodes:
            new = self._decide_node(node, ignore, own, blocks, decision)
            if new is not None and new != node["text"]:
                decision.nodes.append({"i": node["i"], "text": new})
        for item in scan.get("inputs", []):
            text = str(item["text"])
            matches = find_pii(text, ignore)
            new_text = text
            for m in sorted(matches, key=lambda x: x.start, reverse=True):
                if self._keep(m.kind, m.value, str(item["zone"]), decision):
                    continue
                fake = self.datagen.substitute(m.kind, m.value, blocks.get(int(item["block"])))
                new_text = new_text[: m.start] + fake + new_text[m.end :]
                decision.add(f"{item['zone']}:substituted")
            if new_text != text:
                decision.inputs.append({"i": item["i"], "text": new_text})
        decision.avatar = any(
            img.get("avatar") and img.get("zone") in REPLACE_ZONES for img in scan.get("images", [])
        )
        return decision

    def _keep(self, kind: str, value: str, zone: str, decision: DomDecision) -> bool:
        if kind == "email" and self.is_org_email(value):
            self.public_values.add(value)
            decision.add("org:kept")
            return True
        if zone in PUBLIC_ZONES:
            self.public_values.add(value)
            decision.add(f"{zone}:kept")
            return True
        return False

    def _decide_node(
        self,
        node: dict[str, Any],
        ignore: set[str],
        own: set[str],
        blocks: dict[int, str],
        decision: DomDecision,
    ) -> str | None:
        text = str(node["text"])
        zone = str(node["zone"])
        structural = node.get("structural")
        block_key = blocks.get(int(node.get("block", -1)))
        stripped = text.strip()
        if not stripped:
            return None
        if zone == "user_content":
            if stripped in ignore or normalize_value("name", stripped) in own:
                return None
            if block_key and (block_key in ignore or normalize_value("name", block_key) in own):
                return None  # this record was already replaced (API layer) or is our own
            if structural == "name":
                decision.add("user_content:substituted")
                return text.replace(stripped, self.datagen.substitute("name", stripped, block_key))
            if structural == "avatar" and len(stripped) <= 2 and block_key:
                fake = self.datagen.fake_person(block_key).first
                return text.replace(stripped, fake[:1])
            if structural == "body" or (
                not node.get("interactive")
                and len(stripped) >= 12
                and re.search(r"[a-zA-Z]", stripped)
            ):
                decision.add("user_content:substituted")
                return text.replace(stripped, self.datagen.substitute("text", stripped))
        new_text = text
        matches = find_pii(text, ignore)
        if structural == "name" and not matches and zone in REPLACE_ZONES:
            if (
                stripped not in ignore
                and normalize_value("name", stripped) not in own
                and stripped.casefold() not in NAME_HEADERS
            ):
                decision.add(f"{zone}:substituted")
                return text.replace(stripped, self.datagen.substitute("name", stripped, block_key))
        for m in sorted(matches, key=lambda x: x.start, reverse=True):
            if self._keep(m.kind, m.value, zone, decision):
                continue
            fake = self.datagen.substitute(m.kind, m.value, block_key)
            new_text = new_text[: m.start] + fake + new_text[m.end :]
            decision.add(f"{zone if zone in REPLACE_ZONES else 'other'}:substituted")
        return new_text


@dataclass
class DomDecision:
    nodes: list[dict[str, Any]] = field(default_factory=list)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    avatar: bool = False
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n
