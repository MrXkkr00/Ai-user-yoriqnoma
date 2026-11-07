"""Registration E2E (Playwright Python). The scanner turns this test into a flow."""

import re

from playwright.sync_api import Page, expect


def test_register_new_customer(page: Page) -> None:
    page.goto("/register")
    page.get_by_label("To'liq ism").fill("Aziza Rahimova")
    page.get_by_label("Email").fill("aziza.test@example.com")
    page.get_by_label("Telefon raqami").fill("+998901112233")
    page.get_by_label("Parol").fill("Sinov-parol-1")
    page.get_by_test_id("register-submit").click()
    expect(page).to_have_url(re.compile(r".*/verify-email"))
    expect(page.get_by_role("heading", name="Emailni tasdiqlash")).to_be_visible()


def test_admin_users_page(page: Page) -> None:
    # Admin test: the scanner must drop it (admin is never part of a manual).
    page.goto("/admin/users")
    expect(page.get_by_role("heading", name="Foydalanuvchilar")).to_be_visible()
