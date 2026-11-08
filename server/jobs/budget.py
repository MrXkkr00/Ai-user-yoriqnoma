"""Spending limits (TZ FR-SV6): per user per day and month, and for the whole server.

Sign-up is open and every job is paid by one Claude key, so a new job is refused when it
would cross a limit. Finished jobs count with what they really cost; jobs still running
count with their whole budget (they may still spend it).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Case, DecimalField, F, QuerySet, Sum, When
from django.utils import timezone

from jobs.models import ACTIVE, Job


class BudgetLimit(ValueError):
    """A spending limit would be crossed; the message is shown to the user."""


def _spent(jobs: QuerySet[Job]) -> Decimal:
    total = jobs.aggregate(
        total=Sum(
            Case(
                When(status__in=ACTIVE, then=F("budget_usd")),
                default=F("cost_usd"),
                output_field=DecimalField(max_digits=12, decimal_places=4),
            )
        )
    )["total"]
    return Decimal(total or 0)


def _day_start(now: datetime) -> datetime:
    local = timezone.localtime(now)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _month_start(now: datetime) -> datetime:
    return _day_start(now).replace(day=1)


def usage(user: User, now: datetime | None = None) -> dict[str, Decimal]:
    now = now or timezone.now()
    mine = Job.objects.filter(owner=user)
    return {
        "user_day": _spent(mine.filter(created_at__gte=_day_start(now))),
        "user_month": _spent(mine.filter(created_at__gte=_month_start(now))),
        "server_month": _spent(Job.objects.filter(created_at__gte=_month_start(now))),
    }


def limits() -> dict[str, Decimal]:
    return {
        "user_day": Decimal(str(settings.YORIQNOMA_USER_DAILY_BUDGET_USD)),
        "user_month": Decimal(str(settings.YORIQNOMA_USER_MONTHLY_BUDGET_USD)),
        "server_month": Decimal(str(settings.YORIQNOMA_MONTHLY_BUDGET_USD)),
    }


MESSAGES = {
    "user_day": (
        "Bugungi limitingiz tugadi: ${spent} sarflangan, limit ${limit}. Ertaga urinib ko'ring."
    ),
    "user_month": "Shu oydagi limitingiz tugadi: ${spent} sarflangan, limit ${limit}.",
    "server_month": (
        "Serverning shu oydagi umumiy limiti tugadi. Yangi ishlar keyingi oydan qabul qilinadi."
    ),
}


def check_budget(user: User, budget_usd: Decimal, now: datetime | None = None) -> None:
    if budget_usd <= 0:
        raise BudgetLimit("Ish byudjeti musbat bo'lishi kerak")
    maximum = Decimal(str(settings.YORIQNOMA_MAX_JOB_BUDGET_USD))
    if budget_usd > maximum:
        raise BudgetLimit(f"Bitta ish byudjeti ${maximum} dan oshmasligi kerak")
    spent = usage(user, now)
    for key, limit in limits().items():
        if spent[key] + budget_usd > limit:
            raise BudgetLimit(
                MESSAGES[key]
                .replace("${spent}", f"${spent[key]:.2f}")
                .replace("${limit}", f"${limit:.2f}")
            )
