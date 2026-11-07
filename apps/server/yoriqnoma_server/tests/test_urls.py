import pytest
from django.contrib.auth.models import User
from django.test import Client


def test_admin_lives_at_ops_and_asks_for_login(client: Client) -> None:
    response = client.get("/ops/")

    assert response.status_code == 302
    assert response["Location"].startswith("/ops/login/")


def test_there_is_no_admin_path(client: Client) -> None:
    assert client.get("/admin/").status_code == 404


@pytest.mark.django_db
def test_ops_is_closed_to_non_staff_users(client: Client) -> None:
    user = User.objects.create_user("oddiy", password="parol-12345")
    client.force_login(user)

    response = client.get("/ops/")

    assert response.status_code == 302
    assert response["Location"].startswith("/ops/login/")


@pytest.mark.django_db
def test_ops_is_open_to_staff(client: Client) -> None:
    staff = User.objects.create_user("operator", password="parol-12345", is_staff=True)
    client.force_login(staff)

    assert client.get("/ops/").status_code == 200
