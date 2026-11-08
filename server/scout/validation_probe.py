"""Validation probe of mode B (ARCHITECTURE §7.6): the site's own error messages.

On a form of the role's own pages the probe submits EMPTY values once (browser checks off,
``noValidate``) and reads the messages the site shows (``role=alert``, ``aria-invalid``
fields, ``.error``/``.invalid-feedback`` blocks). Empty data is rejected by the site, so
nothing is created. Never in passive mode or on production, never on login/sign-up forms.
The messages are added to the fields' rules (``msg:...``) for the manual's FAQ.
"""

from __future__ import annotations

from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from yoriqnoma_schemas import Form

PROBE_JS = r"""
async (index) => {
  const form = document.querySelectorAll('form')[index];
  if (!form) return null;
  form.noValidate = true;
  form.querySelectorAll('input, textarea').forEach(el => {
    const keep = ['hidden', 'checkbox', 'radio', 'submit', 'button', 'file'];
    if (!keep.includes(el.type)) el.value = '';
  });
  const button = form.querySelector('button[type=submit], input[type=submit], button:not([type])');
  if (!button) return null;
  button.click();
  await new Promise(r => setTimeout(r, 1200));
  const text = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const messages = [];
  const shown = '[role=alert], .error, .errors, .invalid-feedback, .field-error, ' +
    '.errorlist li, [aria-live]';
  document.querySelectorAll(shown)
    .forEach(el => { const t = text(el); if (t && t.length < 200) messages.push(t); });
  const fields = {};
  form.querySelectorAll('[aria-invalid=true]').forEach(el => {
    const id = el.getAttribute('aria-describedby');
    const hint = id ? document.getElementById(id) : null;
    fields[el.name || el.id] = hint ? text(hint) : '';
  });
  return {messages: Array.from(new Set(messages)).slice(0, 10), fields};
}
"""


async def probe_form(page: Page, url: str, index: int) -> dict[str, Any] | None:
    try:
        await page.goto(url)
        result: dict[str, Any] | None = await page.evaluate(PROBE_JS, index)
    except PlaywrightError:
        return None
    return result


def apply_messages(form: Form, result: dict[str, Any]) -> Form:
    """Add the site's messages to the fields they belong to (``msg:...`` rule)."""
    per_field: dict[str, str] = {
        str(k): str(v) for k, v in (result.get("fields") or {}).items() if v
    }
    fields = []
    for f in form.fields:
        message = per_field.get(f.name, "").replace("|", "/").strip()
        if message:
            rules = "|".join(r for r in [f.rules, f"msg:{message[:160]}"] if r)
            fields.append(f.model_copy(update={"rules": rules}))
        else:
            fields.append(f)
    return form.model_copy(update={"fields": fields})
