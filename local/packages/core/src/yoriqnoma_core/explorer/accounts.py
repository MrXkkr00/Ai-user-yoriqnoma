"""Test accounts per role (TZ FR-RL4, FR-E2).

A role the tool can register by itself gets generated identities (A, B); other roles
need accounts from the site owner. Passwords live only in memory.
"""

from __future__ import annotations

from yoriqnoma_core.explorer.datagen import DataGen, Identity
from yoriqnoma_core.explorer.options import ExploreOptions
from yoriqnoma_schemas import Blueprint


class AccountMissing(Exception):
    pass


class AccountManager:
    def __init__(self, bp: Blueprint, opts: ExploreOptions, datagen: DataGen) -> None:
        self.bp = bp
        self.opts = opts
        self.datagen = datagen
        self._identities: dict[tuple[str, str], Identity] = {}
        self.registered: set[tuple[str, str]] = set()
        self.logged_in: set[tuple[str, str]] = set()

    def self_signup(self, role: str) -> bool:
        info = self.bp.role(role)
        return info is not None and info.self_signup

    def label(self, role: str) -> str:
        info = self.bp.role(role)
        return info.label if info else role

    def identity(self, role: str, alias: str) -> Identity:
        key = (role, alias)
        if key in self._identities:
            return self._identities[key]
        given = self.opts.accounts.get(role, {}).get(alias)
        if given is not None:
            ident = Identity(
                role,
                alias,
                given.login,
                given.password.get_secret_value(),
                "",
                "",
                provided=True,
                username=given.login,
            )
            self.datagen.generated.add(given.login)
        elif self.self_signup(role):
            ident = self.datagen.identity(role, alias, self.opts.mail_domain)
        else:
            raise AccountMissing(
                f"«{self.label(role)}» roli uchun test akkaunt bering ({alias} akkaunt). "
                "Bu rolda o'zi ro'yxatdan o'tib bo'lmaydi."
            )
        self._identities[key] = ident
        return ident

    def has_account(self, role: str, alias: str) -> bool:
        try:
            self.identity(role, alias)
        except AccountMissing:
            return False
        return True

    def needs_register(self, role: str, alias: str) -> bool:
        ident = self.identity(role, alias)
        return not ident.provided and (role, alias) not in self.registered

    def all_identities(self) -> list[Identity]:
        return list(self._identities.values())
