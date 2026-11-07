"""scan_report.md: what was found, what was excluded and why, what was unclear (FR-S7)."""

from __future__ import annotations

from yoriqnoma_scanner.fs_guard import Skipped
from yoriqnoma_schemas import Blueprint, RouteInfo


def _table(headers: list[str], rows: list[list[str]]) -> str:
    def esc(text: str) -> str:
        return text.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(esc(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _routes(routes: list[RouteInfo]) -> list[list[str]]:
    return [
        [
            f"`{r.path}`",
            r.kind,
            ", ".join(r.methods),
            r.access if r.access != "roles" else ", ".join(r.roles),
            r.reason,
            f"`{r.source}`",
        ]
        for r in sorted(routes, key=lambda x: (x.kind, x.path))
    ]


def render_report(
    bp: Blueprint,
    stacks: list[str],
    skipped: list[Skipped],
    notes: list[str],
    unknown: list[RouteInfo],
) -> str:
    usable = [r for r in bp.roles if r.kind == "role"]
    parts = [
        f"# Skan hisoboti: {bp.project}",
        "",
        f"- Base URL: `{bp.base_url}`",
        f"- Stek: {', '.join(stacks) or 'aniqlanmadi'}",
        f"- Generator: {bp.generator}",
        f"- Rollar: {len(bp.roles)} ta (yo'riqnoma yozish mumkin: {len(usable)} ta)",
        f"- Sahifa va API yo'llari: {len(bp.pages)} ta, chiqarib tashlangan: {len(bp.excluded)} ta",
        f"- Formalar: {len(bp.forms)}, obyektlar: {len(bp.entities)}, flow'lar: {len(bp.flows)}",
        f"- O'qilmagan fayl va papkalar: {len(skipped)} ta",
        "",
        "## Rollar",
        "",
        _table(
            ["Rol", "Nomi", "Tasnif", "O'zi ro'yxatdan o'tadimi", "Sabab", "Manba"],
            [
                [
                    f"`{r.id}`",
                    r.label,
                    r.kind,
                    "ha" if r.self_signup else "yo'q",
                    r.reason,
                    f"`{r.source}`",
                ]
                for r in bp.roles
            ],
        ),
        "",
        "## Sahifalar va API yo'llari",
        "",
        _table(["Yo'l", "Turi", "Metod", "Kim kiradi", "Sabab", "Manba"], _routes(bp.pages)),
        "",
        "## Chiqarib tashlanganlar",
        "",
        "Bu yo'llar blueprint, capture va yo'riqnomaga kirmaydi (admin yoki noaniq, default-deny).",
        "",
        _table(["Yo'l", "Turi", "Metod", "Tasnif", "Sabab", "Manba"], _routes(bp.excluded)),
        "",
        "## Noaniqlar",
        "",
    ]
    if unknown:
        parts.append(
            _table(["Yo'l", "Turi", "Metod", "Tasnif", "Sabab", "Manba"], _routes(unknown))
        )
    else:
        parts.append("Noaniq guard topilmadi.")
    parts += ["", "## Obyektlar va statuslar", ""]
    for entity in bp.entities:
        parts.append(
            f"### `{entity.name}` — egasi: `{entity.owner_field or '-'}`, "
            f"amallar: {', '.join(entity.actions) or '-'}"
        )
        if entity.pii_fields:
            parts.append(
                f"Shaxsiy ma'lumot bo'lishi mumkin bo'lgan maydonlar (almashtiriladi): "
                f"{', '.join(entity.pii_fields)}"
            )
        if entity.statuses:
            parts.append("")
            parts.append(
                _table(
                    ["Status", "Nomi", "Kim o'rnata oladi", "Manba"],
                    [
                        [
                            f"`{s.value}`",
                            s.label or "-",
                            ", ".join(s.reachable_by) or "hech kim (faqat admin)",
                            ", ".join(f"`{x}`" for x in s.set_by) or "-",
                        ]
                        for s in entity.statuses
                    ],
                )
            )
        parts.append("")
    parts += ["## Flow'lar", ""]
    parts.append(
        _table(
            ["Flow", "Nomi", "Rol", "Bosqich", "Talab qiladi", "Qadamlar", "Manba"],
            [
                [
                    f"`{f.id}`",
                    f.title,
                    f.role,
                    f.stage,
                    ", ".join(f.requires) or "-",
                    str(len(f.steps)),
                    f"`{f.source}`",
                ]
                for f in bp.topo_order()
            ],
        )
    )
    parts += ["", "## Izohlar", ""]
    parts += [f"- {n}" for n in notes] or ["- yo'q"]
    parts += ["", "## O'qilmagan fayl va papkalar (SafeFS)", ""]
    parts.append(
        _table(["Yo'l", "Sabab"], [[f"`{s.path}`", s.reason] for s in skipped])
        if skipped
        else "yo'q"
    )
    return "\n".join(parts) + "\n"
