"""Guided tours for Driver.js (T30): one tour per manual article.

``dist/tour/tours.json`` holds, per flow, its steps: the page path, the element's CSS path
(captured as ``Element.css``) and the step text. ``dist/tour/tour.js`` is a small loader a
site owner adds next to Driver.js: ``YoriqnomaTour.start("customer.order.create")`` starts
a tour; on multi-page flows it continues on the next page (progress in sessionStorage).
Texts come from the manual, so other people's data is already replaced.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from yoriqnoma_core.explorer.session import path_template
from yoriqnoma_schemas import CaptureRun, Manual, State

SKIP_SECTIONS = {"reference", "faq", "unverified"}

LOADER = """/* Yo'riqnoma: Driver.js turlari.
   Driver.js (v1) sahifaga bu fayldan oldin qo'shilgan bo'lishi kerak. */
(function () {
  var TOURS = __TOURS__;
  var KEY = "yoriqnoma-tour";
  function pattern(path) {
    var escaped = path.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");
    return new RegExp("^" + escaped.replace(/:[A-Za-z_]+/g, "[^/]+") + "/?$");
  }
  function run(id, from) {
    var tour = TOURS[id];
    if (!tour) { console.warn("tur topilmadi:", id); return; }
    var here = location.pathname;
    var steps = [];
    var next = null;
    for (var i = from; i < tour.steps.length; i++) {
      var s = tour.steps[i];
      if (s.path && !pattern(s.path).test(here)) { next = i; break; }
      steps.push({ element: s.element || undefined, popover: s.popover });
    }
    if (next === null) { sessionStorage.removeItem(KEY); }
    else { sessionStorage.setItem(KEY, JSON.stringify({ id: id, step: next })); }
    if (!steps.length) {
      var target = next !== null ? tour.steps[next].path : null;
      if (target && target.indexOf(":") < 0) location.assign(target);  /* go to the step's page */
      return;
    }
    var make = (window.driver && window.driver.js && window.driver.js.driver) || window.driver;
    make({ showProgress: true, nextBtnText: "Keyingi", prevBtnText: "Oldingi",
           doneBtnText: "Tushunarli", steps: steps }).drive();
  }
  window.YoriqnomaTour = {
    tours: TOURS,
    start: function (id) { run(id, 0); },
    resume: function () {
      var saved = JSON.parse(sessionStorage.getItem(KEY) || "null");
      if (saved) run(saved.id, saved.step);
    }
  };
  if (document.readyState !== "loading") window.YoriqnomaTour.resume();
  else document.addEventListener("DOMContentLoaded", window.YoriqnomaTour.resume);
})();
"""

README = """# Interaktiv tur (Driver.js)

1. Saytingizga Driver.js ni qo'shing (masalan, `npm i driver.js` yoki o'z nusxangiz):
   `driver.css` va `driver.js.iife.js`.
2. Shu papkadagi `tour.js` ni ulardan keyin qo'shing.
3. Turni boshlash: `YoriqnomaTour.start("<flow id>")`. Mavjud turlar: `tours.json`.

Bir nechta sahifadan o'tadigan turda foydalanuvchi keyingi sahifaga o'tgach tur o'zi davom etadi.
Element topilmasa (sayt o'zgargan bo'lsa), qadam sahifa o'rtasida ko'rsatiladi.
"""


def _step(state: State | None, markers: list[int], n: int, text: str) -> dict[str, Any]:
    # the tour points at the element itself: the image's marker numbers (①) mean nothing here
    clean = re.sub(r"\s*[①-⓿❶-➓]", "", text).strip()
    step: dict[str, Any] = {"popover": {"title": f"{n}-qadam", "description": clean}}
    if state is None:
        return step
    # any record, not the one the test account used: /tickets/5/ -> /tickets/:id/
    step["path"] = path_template(urlsplit(state.url).path or "/")
    element = next((e for e in state.elements if e.marker in markers), None) if markers else None
    if element is not None and element.css:
        step["element"] = element.css
    return step


def tours(manual: Manual, capture: CaptureRun) -> dict[str, dict[str, Any]]:
    states = {s.id: s for s in capture.states}
    out: dict[str, dict[str, Any]] = {}
    for section in manual.sections:
        if section.stage in SKIP_SECTIONS:
            continue
        for article in section.articles:
            steps = [
                _step(states.get(st.state_id or ""), st.markers, st.n, st.text)
                for st in article.steps
            ]
            if steps:
                out[article.flow_id] = {
                    "title": article.title,
                    "purpose": article.purpose,
                    "steps": steps,
                }
    return out


def build_tours(manual: Manual, capture: CaptureRun, out_dir: Path) -> Path:
    tour_dir = out_dir / "tour"
    tour_dir.mkdir(parents=True, exist_ok=True)
    data = tours(manual, capture)
    (tour_dir / "tours.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    loader = LOADER.replace("__TOURS__", json.dumps(data, ensure_ascii=False))
    (tour_dir / "tour.js").write_text(loader, encoding="utf-8")
    (tour_dir / "README.md").write_text(README, encoding="utf-8")
    return tour_dir / "tours.json"
