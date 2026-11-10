"""A plain admin panel with a "new user" form and a users list (no Django admin).

Heuristics, no LLM:

* login: the password form on the admin page (or the site's login page it sends to);
* the users page: the admin page itself or a link to a user-like path
  (``/admin/users``, «Foydalanuvchilar», «Users»);
* the create form: a form there with a password field, an email or login field and,
  usually, a role select or radio group — its options are the roles;
* create: the form is filled with the tool's own test identity and sent; the new id is
  learned by ``ProvisionGuard`` from the answer;
* delete: the row with the test user's email, its delete button and the confirmation.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from playwright.async_api import Dialog, Page
from playwright.async_api import Error as PlaywrightError

from yoriqnoma_core.discovery.forms import FORMS_JS, data_kind, to_form
from yoriqnoma_core.explorer.datagen import Identity
from yoriqnoma_core.provision.base import (
    AdminCredentials,
    CreatedUser,
    ProvisionError,
    RoleCandidate,
    classify_role,
)
from yoriqnoma_core.provision.guard import USERISH, ProvisionGuard
from yoriqnoma_core.text_uz import normalize_uz

ROLE_FIELD = re.compile(r"(^|_)(role|rol|type|user_?type|account_?type|kind|group)s?$", re.I)
USERS_TEXT = re.compile(r"(foydalanuvchi|users?|пользовател|xodim|accounts?)", re.I)
DELETE_TEXT = ("o'chirish", "ochirish", "delete", "remove", "удалить", "o'chir")
LINKS_JS = r"""
() => Array.from(document.querySelectorAll('a[href]')).map(a => [a.getAttribute('href'),
  (a.innerText || '').trim().slice(0, 60)])
"""
ROW_BUTTON_JS = r"""
([email, words]) => {
  const rows = Array.from(document.querySelectorAll('tr, li, [role=row], .row, .card'));
  const row = rows.filter(r => (r.innerText || '').includes(email))
    .sort((a, b) => (a.innerText || '').length - (b.innerText || '').length)[0];
  if (!row) return 'no-row';
  const norm = (s) => (s || '').toLowerCase().replace(/[‘’`ʻʼ]/g, "'");
  const button = Array.from(row.querySelectorAll('button, a, input[type=submit]'))
    .find(b => words.some(w => norm(b.innerText || b.value || b.getAttribute('aria-label'))
      .includes(w)));
  if (!button) return 'no-button';
  button.setAttribute('data-yq-delete', '1');
  return 'ok';
}
"""


class FormAdminAdapter:
    name = "form-admin"

    def __init__(self, base_url: str, admin_path: str, guard: ProvisionGuard) -> None:
        self.base_url = base_url
        self.admin_path = admin_path or "/admin"
        self.guard = guard
        self.users_url = ""
        self.form_index = -1
        self.raw: dict[str, Any] = {}

    def url(self, path: str) -> str:
        return urljoin(self.base_url, path)

    async def _forms(self, page: Page) -> list[dict[str, Any]]:
        await page.wait_for_load_state("networkidle")
        forms: list[dict[str, Any]] = await page.evaluate(FORMS_JS)
        return forms

    @staticmethod
    def _is_create_form(raw: dict[str, Any]) -> bool:
        types = [f.get("type") for f in raw.get("fields", [])]
        names = " ".join(str(f.get("name", "")) for f in raw.get("fields", []))
        has_login = "email" in types or re.search(r"email|login|username", names, re.I)
        return types.count("password") == 1 and bool(has_login) and len(types) >= 3

    async def detect(self, page: Page) -> bool:
        try:
            await page.goto(self.url(self.admin_path))
        except PlaywrightError:
            return False
        return True  # the generic fallback; login() and _find_form() decide for real

    async def login(self, page: Page, creds: AdminCredentials) -> None:
        await page.goto(self.url(self.admin_path))
        login_form = None
        for _ in range(6):  # SPAs check the session first and only then show or redirect
            forms = await self._forms(page)
            login_form = next(
                (
                    f
                    for f in forms
                    if [x.get("type") for x in f["fields"]].count("password") == 1
                    and len(f["fields"]) <= 3
                ),
                None,
            )
            if login_form is not None or any(self._is_create_form(f) for f in forms):
                break
            await page.wait_for_timeout(500)
        if login_form is not None:
            for field in login_form["fields"]:
                selector = f'form >> nth={login_form["index"]} >> [name="{field["name"]}"]'
                if field["type"] == "password":
                    await page.fill(selector, creds.password.get_secret_value())
                elif field["type"] in {"email", "text"}:
                    await page.fill(selector, creds.login)
            button = (
                page.locator("form")
                .nth(login_form["index"])
                .locator("button[type=submit], input[type=submit], button:not([type])")
                .first
            )
            async with page.expect_response(
                lambda r: r.request.method in {"POST", "PUT"}, timeout=15000
            ) as answer:
                await button.click()
            if (await answer.value).status >= 400:
                raise ProvisionError("Admin login yoki paroli noto'g'ri (sayt kirishni rad etdi)")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(500)
        self.guard.signed_in = True
        await self._find_form(page)

    async def _find_form(self, page: Page) -> None:
        candidates = [self.url(self.admin_path)]
        await page.goto(candidates[0])
        await page.wait_for_load_state("networkidle")
        links: list[list[str]] = await page.evaluate(LINKS_JS)
        for href, text in links:
            path = urlsplit(urljoin(page.url, href or "")).path
            last = [p for p in path.split("/") if p][-1:] or [""]
            if USERISH.match(last[0]) or USERS_TEXT.search(text or ""):
                full = self.url(path)
                if full not in candidates:
                    candidates.append(full)
        for url in candidates[:8]:
            await page.goto(url)
            for raw in await self._forms(page):
                if self._is_create_form(raw):
                    self.users_url, self.form_index, self.raw = url, raw["index"], raw
                    return
        raise ProvisionError(
            "Admin panelida yangi foydalanuvchi yaratish formasi topilmadi "
            "(parol, email va rol maydonlari bo'lgan forma)"
        )

    async def roles(self, page: Page) -> list[RoleCandidate]:
        out: list[RoleCandidate] = []
        source = f"admin forma: {urlsplit(self.users_url).path}"
        for field in self.raw.get("fields", []):
            if field.get("type") not in {"select", "radio"} or not ROLE_FIELD.search(
                str(field.get("name", ""))
            ):
                continue
            values = (
                await page.locator("form")
                .nth(self.form_index)
                .evaluate(
                    """(form, name) => Array.from(form.querySelectorAll(`[name="${name}"]`))
                  .flatMap(el => el.tagName === 'SELECT'
                    ? Array.from(el.options).filter(o => o.value).map(o => [o.value, o.text.trim()])
                    : [[el.value, (el.closest('label') || {}).innerText || el.value]])""",
                    field["name"],
                )
            )
            for value, label in values:
                out.append(classify_role(str(label), str(value), source, str(field["name"])))
        if not out:
            raise ProvisionError("Admin formasida rol tanlash maydoni topilmadi")
        return out

    async def create_user(
        self, page: Page, role: RoleCandidate, identity: Identity, alias: str
    ) -> CreatedUser:
        await page.goto(self.users_url)
        await page.wait_for_load_state("networkidle")
        form = page.locator("form").nth(self.form_index)
        values = {
            "fake:email": identity.email,
            "fake:password": identity.password,
            "fake:full_name": identity.full_name,
            "fake:first_name": identity.first_name,
            "fake:last_name": identity.last_name,
            "fake:phone_uz": identity.phone,
            "fake:username": identity.username or identity.email,
        }
        spec = to_form(self.raw, urlsplit(self.users_url).path, "admin_user_form")
        for field in spec.fields:
            target = form.locator(f'[name="{field.name}"]')
            if field.name == role.field:
                if field.type == "select":
                    await target.select_option(role.value)
                else:
                    await form.locator(f'[name="{field.name}"][value="{role.value}"]').check()
                continue
            kind = data_kind(field)
            if field.type in {"select", "radio", "checkbox", "file"}:
                continue
            value = values.get(kind) or identity.full_name
            await target.first.fill(value)
        before = len(self.guard.created)
        try:
            async with page.expect_response(
                lambda r: r.request.method == "POST", timeout=15000
            ) as answer:
                await form.locator(
                    "button[type=submit], input[type=submit], button:not([type])"
                ).first.click()
            await self.guard.on_response(await answer.value)  # learn the new id now
        except PlaywrightError:
            pass  # no request: the form did not pass its own checks (reported below)
        await page.wait_for_load_state("networkidle")
        if len(self.guard.created) == before:
            shown = await page.locator(".error, [role=alert], .errorlist").all_inner_texts()
            raise ProvisionError(
                "test foydalanuvchi yaratilmadi" + (f": {shown[0][:200]}" if shown else "")
            )
        model, remote_id = self.guard.created[-1]
        return CreatedUser(
            role=role.id,
            alias=alias,
            login=identity.email,
            email=identity.email,
            remote_id=remote_id,
            model=model,
        )

    async def delete_object(self, page: Page, entity: str, object_id: str) -> bool:
        return False  # no generic way; the user's own records go with the user, or are reported

    async def delete_user(self, page: Page, user: CreatedUser) -> None:
        await page.goto(self.users_url)
        await page.wait_for_load_state("networkidle")
        words = [normalize_uz(w) for w in DELETE_TEXT]
        state = await page.evaluate(ROW_BUTTON_JS, [user.email, words])
        if state != "ok":
            raise ProvisionError(f"{user.email}: o'chirish tugmasi topilmadi ({state})")

        async def accept(dialog: Dialog) -> None:
            await dialog.accept()

        page.on("dialog", accept)
        try:
            await page.locator("[data-yq-delete]").first.click()
            await page.wait_for_timeout(500)
            confirm = page.locator("[role=dialog] button, .modal button, dialog button").filter(
                has_text=re.compile("(ha|tasdiq|yes|confirm|o'chir|delete)", re.I)
            )
            if await confirm.count():
                await confirm.first.click()
            await page.wait_for_load_state("networkidle")
        finally:
            page.remove_listener("dialog", accept)
        await page.goto(self.users_url)
        await page.wait_for_load_state("networkidle")
        if user.email in (await page.locator("body").inner_text()):
            raise ProvisionError(f"{user.email}: foydalanuvchi ro'yxatdan o'chmadi")
