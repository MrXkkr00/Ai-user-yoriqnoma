"""Domain pages: add, the three ways to prove ownership, "Tekshirish" (TZ SEC-9)."""

from __future__ import annotations

from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from domains.models import Domain
from domains.services import DomainError, add_domain, verify


@login_required
@require_http_methods(["GET", "POST"])
def domain_list(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        try:
            domain = add_domain(cast(User, request.user), request.POST.get("host", ""))
            messages.success(request, f"{domain.host} qo'shildi. Endi uni tasdiqlang.")
        except DomainError as exc:
            messages.error(request, str(exc))
        return redirect("domains:list")
    domains = Domain.objects.filter(owner=cast(User, request.user))
    return render(request, "domains/list.html", {"domains": domains})


@login_required
@require_POST
def domain_verify(request: HttpRequest, pk: int) -> HttpResponse:
    domain = get_object_or_404(Domain, pk=pk, owner=cast(User, request.user))
    try:
        verify(domain)
        messages.success(request, f"{domain.host} tasdiqlandi ({domain.get_method_display()}).")
    except DomainError as exc:
        messages.error(request, f"{domain.host}: {exc}")
    return redirect("domains:list")


@login_required
@require_POST
def domain_delete(request: HttpRequest, pk: int) -> HttpResponse:
    domain = get_object_or_404(Domain, pk=pk, owner=cast(User, request.user))
    domain.delete()
    messages.info(request, f"{domain.host} o'chirildi.")
    return redirect("domains:list")
