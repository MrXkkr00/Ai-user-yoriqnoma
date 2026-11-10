"""Django admin (``django.contrib.admin`` with ``UserAdmin``): exact steps, no guessing.

* login: ``<admin>/login/``;
* the user model: the admin index link of a user-like model (``auth/user``,
  ``accounts/user``, ``helpdesk/user`` ...);
* roles: options of a role-like select (``role``, ``user_type`` ...) and of ``groups``;
  only the option lists are read, never someone's values;
* create: the add form (username, password), then the change form (email, names, role
  or group; ``is_staff`` and ``is_superuser`` always off);
* delete: ``<model>/<id>/delete/`` and the confirmation button (Django removes related
  objects the user owns with it).
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from yoriqnoma_core.explorer.datagen import Identity
from yoriqnoma_core.provision.base import (
    AdminCredentials,
    CreatedUser,
    ProvisionError,
    RoleCandidate,
    classify_role,
)
from yoriqnoma_core.provision.guard import USERISH, object_key, singular

ROLE_FIELDS = ("role", "user_type", "usertype", "type", "kind", "account_type", "rol")
OPTIONS_JS = r"""
(names) => {
  const out = {};
  for (const name of names) {
    const el = document.querySelector(`select[name="${name}"]`);
    if (el) out[name] = Array.from(el.options)
      .filter(o => o.value !== '')
      .map(o => [o.value, o.text.trim()]);
  }
  return out;
}
"""
MODELS_JS = r"""
() => Array.from(document.querySelectorAll('#content-main a[href], .app- a[href], table a[href]'))
  .map(a => a.getAttribute('href'))
"""


class DjangoAdminAdapter:
    name = "django-admin"

    def __init__(self, base_url: str, admin_path: str = "/admin/") -> None:
        self.base_url = base_url
        self.admin = "/" + admin_path.strip("/") + "/" if admin_path.strip("/") else "/admin/"
        self.user_path = ""  # "/admin/helpdesk/user/"
        self.models: dict[str, str] = {}  # singular model name -> changelist path

    def url(self, path: str) -> str:
        return urljoin(self.base_url, path)

    async def detect(self, page: Page) -> bool:
        try:
            await page.goto(self.url(self.admin + "login/"))
        except PlaywrightError:
            return False
        return bool(await page.locator("#login-form, body.login #id_username, #user-tools").count())

    async def login(self, page: Page, creds: AdminCredentials) -> None:
        await page.goto(self.url(self.admin + "login/?next=" + self.admin))
        if await page.locator("#user-tools").count():
            return
        await page.fill("#id_username", creds.login)
        await page.fill("#id_password", creds.password.get_secret_value())
        await page.locator("#login-form [type=submit], form [type=submit]").first.click()
        await page.wait_for_load_state("domcontentloaded")
        if not await page.locator("#user-tools").count():
            note = await page.locator(".errornote").all_inner_texts()
            raise ProvisionError(
                "Django admin'ga kirib bo'lmadi" + (f": {note[0].strip()}" if note else "")
            )
        await self._find_models(page)

    async def _find_models(self, page: Page) -> None:
        await page.goto(self.url(self.admin))
        hrefs: list[str | None] = await page.evaluate(MODELS_JS)
        pattern = re.compile("^" + re.escape(self.admin) + r"([a-z0-9_]+)/([a-z0-9_]+)/$")
        for href in hrefs:
            path = urlsplit(href or "").path
            match = pattern.match(path)
            if match:
                self.models.setdefault(singular(match.group(2)), path)
        users = [p for m, p in self.models.items() if USERISH.match(m)]
        if not users:
            raise ProvisionError("Django admin'da foydalanuvchilar bo'limi topilmadi")
        self.user_path = sorted(users, key=lambda p: ("auth/" in p, p))[0]

    async def roles(self, page: Page) -> list[RoleCandidate]:
        await page.goto(self.url(self.user_path + "add/"))
        found: dict[str, list[list[str]]] = await page.evaluate(
            OPTIONS_JS, [*ROLE_FIELDS, "groups"]
        )
        if not found:
            # the role is often only on the change form: read the options of one record
            await page.goto(self.url(self.user_path))
            first = page.locator("#result_list tbody th a").first
            if await first.count():
                await first.click()
                await page.wait_for_load_state("domcontentloaded")
                found = await page.evaluate(OPTIONS_JS, [*ROLE_FIELDS, "groups"])
        out: list[RoleCandidate] = []
        for field_name, options in found.items():
            source = f"django admin: {self.user_path} «{field_name}»"
            for value, label in options:
                out.append(classify_role(label, value, source, field_name))
        if not out:
            raise ProvisionError("Django admin'da rol maydoni (role yoki groups) topilmadi")
        return out

    async def _fill_if(self, page: Page, selector: str, value: str) -> None:
        if value and await page.locator(selector).count():
            await page.fill(selector, value)

    async def _errors(self, page: Page) -> str:
        texts = await page.locator(".errornote, .errorlist").all_inner_texts()
        return "; ".join(t.strip() for t in texts if t.strip())[:300]

    async def create_user(
        self, page: Page, role: RoleCandidate, identity: Identity, alias: str
    ) -> CreatedUser:
        await page.goto(self.url(self.user_path + "add/"))
        login = identity.username or identity.email
        await self._fill_if(page, "#id_username", login)
        await self._fill_if(page, "#id_email", identity.email)
        if await page.locator("input[name=usable_password][value=true]").count():
            await page.check("input[name=usable_password][value=true]")
        await self._fill_if(page, "#id_password1", identity.password)
        await self._fill_if(page, "#id_password2", identity.password)
        await self._set_role(page, role)
        button = page.locator("input[name=_continue]")
        if not await button.count():
            button = page.locator("input[name=_save]")
        await button.first.click()
        await page.wait_for_load_state("domcontentloaded")
        key = object_key(urlsplit(page.url).path)
        if key is None:
            raise ProvisionError(f"test foydalanuvchi yaratilmadi: {await self._errors(page)}")
        model, remote_id = key
        user = CreatedUser(
            role=role.id,
            alias=alias,
            login=login,
            email=identity.email,
            remote_id=remote_id,
            model=model,
        )
        # the change form: names, email, role or group; never staff or superuser rights
        await self._fill_if(page, "#id_email", identity.email)
        await self._fill_if(page, "#id_first_name", identity.first_name)
        await self._fill_if(page, "#id_last_name", identity.last_name)
        await self._set_role(page, role)
        for flag in ("#id_is_staff", "#id_is_superuser"):
            if await page.locator(flag).count() and await page.locator(flag).is_checked():
                await page.uncheck(flag)
        if await page.locator("#id_is_active").count():
            await page.check("#id_is_active")
        save = page.locator("input[name=_save]")
        if await save.count():
            await save.first.click()
            await page.wait_for_load_state("domcontentloaded")
            errors = await self._errors(page)
            if errors:
                user.error = errors
        return user

    async def _set_role(self, page: Page, role: RoleCandidate) -> None:
        if not role.field or not role.value:
            return
        select = page.locator(f'select[name="{role.field}"]')
        if not await select.count():
            return
        if role.field == "groups":
            await select.select_option([role.value])
        else:
            await select.select_option(role.value)

    async def _delete(self, page: Page, changelist: str, object_id: str) -> bool:
        await page.goto(self.url(f"{changelist}{object_id}/delete/"))
        button = page.locator('form input[type="submit"]').first
        if not await button.count() or "/delete/" not in page.url:
            return False
        await button.click()
        await page.wait_for_load_state("domcontentloaded")
        return "/delete/" not in page.url

    async def delete_object(self, page: Page, entity: str, object_id: str) -> bool:
        changelist = self.models.get(singular(entity))
        if changelist is None:
            return False
        return await self._delete(page, changelist, object_id)

    async def delete_user(self, page: Page, user: CreatedUser) -> None:
        if not await self._delete(page, self.user_path, user.remote_id):
            raise ProvisionError(f"test foydalanuvchi o'chirilmadi: {user.login}")
