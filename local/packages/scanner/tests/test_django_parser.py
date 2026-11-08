"""Django and DRF snippets: url chains, guards, mixins, groups, middleware, routers (T29)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yoriqnoma_scanner.api import scan
from yoriqnoma_scanner.parsers.django_routes import django_route, regex_route
from yoriqnoma_scanner.parsers.html_forms import URL_MARK, parse_template
from yoriqnoma_scanner.parsers.i18n import read_po
from yoriqnoma_schemas import Blueprint

Writer = Callable[[Path, dict[str, str]], Path]

GUARDS_PROJECT = {
    "requirements.txt": "django\n",
    "proj/settings.py": 'ROOT_URLCONF = "proj.urls"\nINSTALLED_APPS = []\n',
    "proj/urls.py": """
from django.urls import include, path, re_path
from shop import views

urlpatterns = [
    path("shop/", include(("shop.urls", "shop"), namespace="shop")),
    re_path(r"^legacy/(?P<slug>[-\\w]+)/$", views.legacy, name="legacy"),
]
""",
    "shop/urls.py": """
from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

urlpatterns = [
    path("orders/", login_required(views.OrderList.as_view()), name="orders"),
    path("reports/", views.reports, name="reports"),
    path("perm/", views.perm_view),
    path("super/", views.SuperView.as_view()),
    path("managers/", views.managers_only),
    path("group/", views.GroupView.as_view()),
]
""",
    "shop/models.py": """
from django.conf import settings
from django.db import models

ROLE_CHOICES = [("buyer", "Xaridor"), ("manager", "Menejer")]


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="buyer")


class Order(models.Model):
    STATUS = (("new", "Yangi"), ("done", "Tayyor"))
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS, default="new")
""",
    "shop/views.py": """
from django.contrib.auth.decorators import permission_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.generic import ListView, TemplateView

from .models import Order


class OrderList(ListView):
    model = Order

    def get_queryset(self):
        return Order.objects.filter(buyer=self.request.user)


@user_passes_test(lambda u: u.is_superuser)
def reports(request):
    return render(request, "reports.html")


@permission_required("shop.view_order")
def perm_view(request):
    return render(request, "perm.html")


class SuperView(UserPassesTestMixin, TemplateView):
    template_name = "x.html"

    def test_func(self):
        return self.request.user.is_staff


def managers_only(request):
    if request.user.profile.role != "manager":
        raise PermissionDenied
    return render(request, "m.html")


class GroupView(LoginRequiredMixin, TemplateView):
    template_name = "g.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.groups.filter(name="Couriers").exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def legacy(request, slug):
    return render(request, "legacy.html")
""",
}


def _access(bp: Blueprint) -> dict[str, tuple[str, list[str]]]:
    return {p.path: (p.access, p.roles) for p in [*bp.pages, *bp.excluded] if p.kind == "page"}


def test_route_conversion() -> None:
    assert django_route("tickets/<int:pk>/reply/") == "tickets/:pk/reply/"
    assert django_route("<slug>/") == ":slug/"
    assert regex_route(r"^a/(?P<pk>\d+)/b/$") == "a/:pk/b/"
    assert regex_route(r"^x/([0-9]+)/$") == "x/:arg/"


def test_guards_mixins_groups_and_profile_roles(tmp_path: Path, write_files: Writer) -> None:
    bp = scan(write_files(tmp_path, GUARDS_PROJECT), "http://127.0.0.1:9000").blueprint
    access = _access(bp)
    kinds = {r.id: r.kind for r in bp.roles}

    assert kinds["buyer"] == "role" and kinds["manager"] == "role"
    assert kinds["couriers"] == "role" and bp.role("couriers").label == "Couriers"  # type: ignore[union-attr]
    assert kinds["admin"] == "excluded"
    assert access["/shop/orders/"][0] == "roles"  # login_required(...) in urls + owner filter
    assert access["/shop/reports/"][0] == "excluded"  # user_passes_test(is_superuser)
    assert access["/shop/perm/"][0] == "excluded"  # permission_required: default-deny
    assert access["/shop/super/"][0] == "excluded"  # test_func checks is_staff
    assert access["/shop/managers/"] == ("roles", ["manager"])
    assert access["/shop/group/"] == ("roles", ["couriers"])
    assert access["/legacy/:slug/"][0] == "guest"
    order = bp.entity("order")
    assert order is not None and order.owner_field == "buyer"
    assert [s.value for s in order.statuses] == ["new", "done"]


def test_login_required_middleware(tmp_path: Path, write_files: Writer) -> None:
    project = {
        "requirements.txt": "django\n",
        "settings.py": (
            'ROOT_URLCONF = "urls"\nINSTALLED_APPS = []\n'
            'MIDDLEWARE = ["django.contrib.auth.middleware.LoginRequiredMiddleware"]\n'
        ),
        "urls.py": (
            "from django.urls import path\nimport views\n\n"
            'urlpatterns = [path("", views.home), path("about/", views.about)]\n'
        ),
        "views.py": """
from django.contrib.auth.decorators import login_not_required
from django.shortcuts import render


def home(request):
    return render(request, "home.html")


@login_not_required
def about(request):
    return render(request, "about.html")
""",
    }
    bp = scan(write_files(tmp_path, project), "http://127.0.0.1:9000").blueprint
    access = _access(bp)

    assert access["/"] == ("roles", ["user"])  # no role model: the plain logged-in user
    assert access["/about/"][0] == "guest"


DRF_PROJECT = {
    "requirements.txt": "django\ndjangorestframework\n",
    "proj/settings.py": (
        'ROOT_URLCONF = "api.urls"\nINSTALLED_APPS = []\n'
        "REST_FRAMEWORK = {\n"
        '    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"]\n'
        "}\n"
    ),
    "api/models.py": """
from django.contrib.auth import get_user_model
from django.db import models


class Booking(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        CONFIRMED = "confirmed", "Tasdiqlangan"
        CANCELLED = "cancelled", "Bekor qilingan"

    owner = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    guest_name = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
""",
    "api/serializers.py": """
from rest_framework import serializers

from .models import Booking


class BookingSerializer(serializers.ModelSerializer):
    note = serializers.CharField(max_length=200, required=False)

    class Meta:
        model = Booking
        fields = ["id", "guest_name", "status", "note"]
        read_only_fields = ["status"]
""",
    "api/views.py": """
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Booking
from .serializers import BookingSerializer


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer

    def get_queryset(self):
        return Booking.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user, status=Booking.Status.NEW)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if booking.status != Booking.Status.NEW:
            return Response(status=400)
        booking.status = Booking.Status.CANCELLED
        booking.save()
        return Response({"ok": True})


class AdminBookingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAdminUser]
""",
    "api/urls.py": """
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminBookingViewSet, BookingViewSet

router = DefaultRouter()
router.register("bookings", BookingViewSet, basename="booking")
router.register(r"staff/bookings", AdminBookingViewSet)

urlpatterns = [path("api/", include(router.urls))]
""",
}


def test_drf_router_viewsets_actions_and_permissions(tmp_path: Path, write_files: Writer) -> None:
    result = scan(write_files(tmp_path, DRF_PROJECT), "http://127.0.0.1:9000")
    bp = result.blueprint
    api = {(p.path, m): p for p in bp.pages if p.kind == "api" for m in p.methods}
    excluded = {(p.path, m) for p in bp.excluded for m in p.methods}

    assert {
        ("/api/bookings/", "GET"),
        ("/api/bookings/", "POST"),
        ("/api/bookings/:pk/", "GET"),
        ("/api/bookings/:pk/", "PUT"),
        ("/api/bookings/:pk/", "PATCH"),
        ("/api/bookings/:pk/", "DELETE"),
        ("/api/bookings/:pk/cancel/", "POST"),
    } <= set(api)
    assert api[("/api/bookings/", "POST")].roles == ["user"]
    assert {("/api/staff/bookings/", "GET"), ("/api/staff/bookings/:pk/", "GET")} <= excluded
    booking = bp.entity("booking")
    assert booking is not None
    assert {"list", "create", "view", "update", "delete", "cancel"} <= set(booking.actions)
    reach = {s.value: s.reachable_by for s in booking.statuses}
    assert reach == {"new": ["user"], "confirmed": [], "cancelled": ["user"]}
    assert "guest_name" in booking.pii_fields


def test_drf_serializer_fields(tmp_path: Path, write_files: Writer) -> None:
    from yoriqnoma_scanner.detect import detect
    from yoriqnoma_scanner.fs_guard import SafeFS
    from yoriqnoma_scanner.parsers.django_routes import DjangoParser

    root = write_files(tmp_path, DRF_PROJECT)
    fs = SafeFS(root)
    result = DjangoParser().parse(detect(fs), fs)
    fields = {f.name: f for f in result.request_models["BookingSerializer"]}

    assert set(fields) == {"guest_name", "note"}  # id and read-only status are not input
    assert fields["guest_name"].rules == "max:80" and fields["guest_name"].required
    assert not fields["note"].required
    statuses = [r for r in result.routes if r.path == "/api/bookings/:pk/cancel/"]
    assert statuses[0].status_requires == ["new"]
    assert statuses[0].status_sets == [("status", "cancelled")]


def test_template_modal_form_and_url_markers() -> None:
    info = parse_template(
        """{% load i18n %}
<div class="modal" id="cancelModal">
  <form method="post" action="{% url 'shop:cancel' order.pk %}">{% csrf_token %}
    <button type="submit">{% trans "Yes" %}</button>
  </form>
</div>
<button data-bs-toggle="modal" data-bs-target="#cancelModal">Bekor qilish</button>
<form method="post">{{ form.as_p }}<input type="submit" value="Saqlash"></form>
<a href="{% url 'shop:orders' %}">Buyurtmalar</a>
""",
        lambda s: {"Yes": "Ha"}.get(s, s),
    )

    assert info.forms[0].modal == "cancelModal"
    assert info.forms[0].action == URL_MARK + "shop:cancel"
    assert info.forms[0].submit == "Ha"
    assert info.openers == {"cancelModal": "Bekor qilish"}
    assert info.forms[1].renders_form_object and info.forms[1].submit == "Saqlash"
    assert info.links == [(URL_MARK + "shop:orders", "Buyurtmalar")]
    assert "Bekor qilish" not in info.buttons


def test_read_po_multiline_and_fuzzy() -> None:
    catalogue = read_po(
        'msgid ""\nmsgstr ""\n"Language: uz\\n"\n\n'
        'msgid "Send"\nmsgstr "Yuborish"\n\n'
        'msgid ""\n"Long "\n"text"\nmsgstr ""\n"Uzun "\n"matn"\n\n'
        '#, fuzzy\nmsgid "Draft"\nmsgstr "Qoralama"\n\n'
        'msgid "Empty"\nmsgstr ""\n'
    )

    assert catalogue == {"Send": "Yuborish", "Long text": "Uzun matn"}
