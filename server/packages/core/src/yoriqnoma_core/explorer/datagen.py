"""Test data generator (TZ FR-E4) and stable fakes for other people's data (FR-E10).

* Account identities and form values: deterministic from the seed, valid for the rules
  (``min:8|max:64|regex:...``).
* ``substitute``: a fake value for a real foreign value, computed with HMAC from the
  secret key, the run id and the real value. No table is kept; the same real value
  always maps to the same fake within a run (also after a restart), and values of one
  record come from one fake person. The real value is never stored.
"""

from __future__ import annotations

import hashlib
import hmac
import random
import re
import string
from dataclasses import dataclass

FIRST_NAMES_M = [
    "Aziz",
    "Bekzod",
    "Doniyor",
    "Elyor",
    "Farrux",
    "G'ayrat",
    "Husan",
    "Ilhom",
    "Jamshid",
    "Komil",
    "Laziz",
    "Mansur",
    "Nodir",
    "Otabek",
    "Rustam",
    "Sanjar",
    "Temur",
    "Ulug'bek",
    "Xurshid",
    "Zafar",
]
FIRST_NAMES_F = [
    "Aziza",
    "Barno",
    "Dildora",
    "Feruza",
    "Gulnora",
    "Hilola",
    "Iroda",
    "Kamola",
    "Lola",
    "Madina",
    "Nigora",
    "Oydin",
    "Rayhona",
    "Sevara",
    "Shahnoza",
    "Umida",
    "Yulduz",
    "Zarina",
    "Nilufar",
    "Mohira",
]
LAST_NAMES = [
    "Abdullayev",
    "Bakirov",
    "Ergashev",
    "Fayzullayev",
    "G'aniyev",
    "Hamidov",
    "Ismoilov",
    "Jo'rayev",
    "Karimov",
    "Latipov",
    "Mirzayev",
    "Nazarov",
    "Olimov",
    "Qodirov",
    "Rahimov",
    "Saidov",
    "Tursunov",
    "Usmonov",
    "Xolmatov",
    "Yo'ldoshev",
]
STREETS = [
    "Navoiy",
    "Bobur",
    "Mustaqillik",
    "Amir Temur",
    "Shota Rustaveli",
    "Qatortol",
    "Bunyodkor",
    "Farg'ona yo'li",
    "Chilonzor",
    "Beruniy",
]
DISTRICTS = [
    "Yunusobod",
    "Mirzo Ulug'bek",
    "Chilonzor",
    "Yakkasaroy",
    "Shayxontohur",
    "Olmazor",
    "Sergeli",
    "Uchtepa",
]
SENTENCES = [
    "Sinov uchun yozilgan matn.",
    "Bu namuna xabar: haqiqiy ma'lumot emas.",
    "Mahsulot sifati yaxshi, yetkazish tez bo'ldi.",
    "Iltimos, buyurtmani tezroq jo'nating.",
    "Rahmat, hammasi joyida.",
    "Savolim bor: yetkazish qancha vaqt oladi?",
]
OPERATORS = ["90", "91", "93", "94", "95", "97", "98", "99", "33", "88"]
FAKE_DOMAIN = "example.com"  # reserved (RFC 2606): fakes never point at real mailboxes


@dataclass(frozen=True)
class Person:
    first: str
    last: str
    email: str
    phone: str
    address: str

    @property
    def full_name(self) -> str:
        return f"{self.first} {self.last}"


@dataclass
class Identity:
    role: str
    alias: str
    email: str
    password: str
    full_name: str
    phone: str
    provided: bool = False  # given by the site owner (not generated)


def _translit(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower().replace("'", ""))


def _person(rng: random.Random) -> Person:
    female = rng.random() < 0.5
    first = rng.choice(FIRST_NAMES_F if female else FIRST_NAMES_M)
    last = rng.choice(LAST_NAMES)
    if female:
        last = last + "a" if last.endswith(("ov", "ev")) else last
    email = f"{_translit(first)}.{_translit(last)}{rng.randint(1, 99)}@{FAKE_DOMAIN}"
    phone = "+998" + rng.choice(OPERATORS) + "".join(rng.choice(string.digits) for _ in range(7))
    address = (
        f"Toshkent sh., {rng.choice(DISTRICTS)} tumani, {rng.choice(STREETS)} ko'chasi, "
        f"{rng.randint(1, 120)}-uy"
    )
    return Person(first, last, email, phone, address)


def normalize_real(kind: str, value: str) -> str:
    if kind == "email":
        return value.strip().lower()
    if kind == "phone":
        return re.sub(r"\D", "", value)[-9:]
    return re.sub(r"\s+", " ", value).strip().casefold()


def _format_phone_like(fake: str, real: str) -> str:
    """Keep the real value's layout (spaces, dashes, +998) with fake digits."""
    digits = re.sub(r"\D", "", fake)[-9:]
    out: list[str] = []
    real_digits = re.sub(r"\D", "", real)
    take = list(digits[-min(len(real_digits), 9) :]) if real_digits else list(digits)
    prefix_len = max(0, len(real_digits) - len(take))
    seen = 0
    for ch in real:
        if ch.isdigit():
            if seen < prefix_len:
                out.append(ch)  # country code (998) stays
            elif take:
                out.append(take.pop(0))
            seen += 1
        else:
            out.append(ch)
    return "".join(out)


class DataGen:
    def __init__(self, seed: str, run_id: str, pseudonym_key: bytes) -> None:
        if len(pseudonym_key) < 16:
            raise ValueError("pseudonym_key kamida 16 bayt bo'lishi kerak")
        self.seed = seed
        self.run_id = run_id
        self._key = pseudonym_key
        self.generated: set[str] = set()
        self._counter = 0

    def __repr__(self) -> str:  # never show the key
        return f"DataGen(run_id={self.run_id!r})"

    # --- own test data ------------------------------------------------------------

    def _rng(self, *parts: str) -> random.Random:
        digest = hashlib.sha256("|".join([self.seed, self.run_id, *parts]).encode()).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    def _keep(self, value: str) -> str:
        self.generated.add(value)
        return value

    def identity(self, role: str, alias: str, mail_domain: str) -> Identity:
        rng = self._rng("identity", role, alias)
        person = _person(rng)
        short = hashlib.sha256(f"{self.run_id}|{role}|{alias}".encode()).hexdigest()[:6]
        email = f"{_translit(role)}.{alias.lower()}.{short}@{mail_domain}"
        password = "Yq-" + "".join(rng.choice(string.ascii_letters) for _ in range(7)) + "7a!"
        ident = Identity(role, alias, email, password, person.full_name, person.phone)
        for value in (email, password, person.full_name, person.phone):
            self._keep(value)
        return ident

    def value(self, kind: str, rules: str | None = None, context: str = "") -> str:
        """A fresh generated value of ``kind`` that satisfies ``rules``."""
        self._counter += 1
        rng = self._rng("value", kind, context, str(self._counter))
        person = _person(rng)
        text: str
        if kind == "full_name":
            text = person.full_name
        elif kind == "email":
            text = person.email
        elif kind == "phone_uz":
            text = person.phone
        elif kind == "address":
            text = person.address
        elif kind == "password":
            text = "Yq-" + "".join(rng.choice(string.ascii_letters) for _ in range(9)) + "7a!"
        elif kind == "number":
            text = str(rng.randint(1, 5))
        elif kind == "date":
            text = f"2026-12-{rng.randint(1, 28):02d}"
        else:
            text = rng.choice(SENTENCES)
        return self._keep(self._fit(text, rules))

    @staticmethod
    def _fit(text: str, rules: str | None) -> str:
        if not rules:
            return text
        mins = re.search(r"(?:^|\|)min:(\d+)", rules)
        maxs = re.search(r"(?:^|\|)max:(\d+)", rules)
        if text.isdigit():
            value = int(text)
            if mins:
                value = max(value, int(mins.group(1)))
            if maxs:
                value = min(value, int(maxs.group(1)))
            return str(value)
        if mins and len(text) < int(mins.group(1)):
            text = (text + " " + text) * (int(mins.group(1)) // max(len(text), 1) + 1)
        if maxs and len(text) > int(maxs.group(1)):
            text = text[: int(maxs.group(1))].rstrip()
        return text

    # --- stable fakes for foreign values ------------------------------------------

    def _hmac_rng(self, *parts: str) -> random.Random:
        mac = hmac.new(self._key, "|".join([self.run_id, *parts]).encode(), hashlib.sha256)
        return random.Random(int.from_bytes(mac.digest()[:8], "big"))

    def fake_person(self, record_key: str) -> Person:
        return _person(self._hmac_rng("person", normalize_real("name", record_key)))

    def substitute(self, kind: str, real: str, record_key: str | None = None) -> str:
        """The fake for a foreign ``real`` value; same input -> same fake within the run."""
        if record_key:
            person = self.fake_person(record_key)
        else:
            person = _person(self._hmac_rng(kind, normalize_real(kind, real)))
        rng = self._hmac_rng("text", kind, normalize_real(kind, real))
        if kind == "email":
            fake = person.email
        elif kind == "phone":
            fake = _format_phone_like(person.phone, real)
        elif kind == "name":
            fake = person.first if len(real.split()) == 1 else person.full_name
        elif kind == "address":
            fake = person.address
        elif kind == "card":
            fake = "4000 0000 0000 0002"
        elif kind == "passport":
            fake = "AA" + "".join(rng.choice(string.digits) for _ in range(7))
        elif kind == "pinfl":
            fake = "".join(rng.choice(string.digits) for _ in range(14))
        else:
            fake = rng.choice(SENTENCES)
        return self._keep(fake)
