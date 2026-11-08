"""Test data for demo_django: a support operator, a staff admin and another customer.

The operator account imitates an account the site owner gives to the tool. The other
customer's name, phone and ticket are "someone else's data": a support manual must show
them replaced with generated values (TZ FR-E10).
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from helpdesk.models import Ticket, User

OPERATOR = ("operator", "Operator-pass-1")
ADMIN = ("admin", "Admin-pass-1")


class Command(BaseCommand):
    help = "Create demo_django test data"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="flush the database first")

    def handle(self, *args, **options):
        if options["reset"]:
            call_command("flush", interactive=False, verbosity=0)
        if not User.objects.filter(username=ADMIN[0]).exists():
            User.objects.create_superuser(
                ADMIN[0], "admin@yordam.uz", ADMIN[1], role=User.Role.ADMIN
            )
        if not User.objects.filter(username=OPERATOR[0]).exists():
            User.objects.create_user(
                OPERATOR[0],
                "operator@yordam.uz",
                OPERATOR[1],
                role=User.Role.SUPPORT,
                first_name="Operator",
                last_name="Bir",
            )
        other, _ = User.objects.get_or_create(
            username="dilnoza",
            defaults={
                "email": "dilnoza.karimova@mail.uz",
                "first_name": "Dilnoza",
                "last_name": "Karimova",
                "phone": "+998977654321",
            },
        )
        if not Ticket.objects.filter(owner=other).exists():
            Ticket.objects.create(
                owner=other,
                subject="Internet ishlamayapti",
                body="Ikki kundan beri internet yo'q, iltimos yordam bering.",
                contact_phone="+998977654321",
            )
        self.stdout.write("demo_django: test data ready")
