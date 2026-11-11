"""Trusted sign-in hosts (single sign-on): what a named host may do, and nothing else."""

from __future__ import annotations

import pytest

from yoriqnoma_core.provision.guard import ProvisionGuard
from yoriqnoma_core.safety.policy_engine import PolicyEngine, RequestContext
from yoriqnoma_core.safety.sso import invalid_entries, parse_hosts, trusted_decision
from yoriqnoma_core.safety.url_guard import HostGuard
from yoriqnoma_schemas import Policy

APP = "https://app.example.uz/home?version=1"
AUTH = "auth.example.uz"


def test_parse_hosts_takes_names_and_urls() -> None:
    assert parse_hosts("auth.example.uz, https://sso.example.uz/login  AUTH.example.uz") == (
        "auth.example.uz",
        "sso.example.uz",
    )
    assert parse_hosts("") == () and parse_hosts(None) == ()
    assert invalid_entries("auth.example.uz, nothost, 1.2") == ["nothost", "1.2"]


@pytest.mark.parametrize(
    ("method", "url", "rtype", "allowed"),
    [
        ("GET", f"https://{AUTH}/Account/Login?ReturnUrl=x", "document", True),
        ("GET", f"https://{AUTH}/.well-known/openid-configuration", "fetch", True),
        ("OPTIONS", f"https://{AUTH}/connect/token", "fetch", True),
        ("POST", f"https://{AUTH}/Account/Login", "document", True),
        ("POST", f"https://{AUTH}/connect/token", "fetch", True),
        ("POST", f"https://{AUTH}/Account/ChangePassword", "document", False),
        ("POST", f"https://{AUTH}/Account/Register", "document", False),
        ("POST", f"https://{AUTH}/api/users", "fetch", False),
        ("DELETE", f"https://{AUTH}/connect/token", "fetch", False),
        ("PUT", f"https://{AUTH}/Account/Login", "fetch", False),
        ("GET", f"https://{AUTH}/Account/LogOut", "document", False),
    ],
)
def test_trusted_host_rules(method: str, url: str, rtype: str, allowed: bool) -> None:
    decision = trusted_decision(method, url, rtype, (AUTH,))
    assert decision is not None and decision[0] is allowed, (method, url, decision)


def test_other_hosts_are_not_trusted() -> None:
    assert trusted_decision("GET", "https://evil.example.com/", "document", (AUTH,)) is None
    assert (
        trusted_decision("GET", f"https://x.{AUTH}/", "document", (AUTH,)) is None
    )  # no subdomains
    assert trusted_decision("GET", f"https://{AUTH}/", "document", ()) is None


def test_engine_lets_sso_through_only_when_named() -> None:
    policy = Policy(target_role="customer")
    ctx = RequestContext()
    plain = PolicyEngine(policy, APP)
    named = PolicyEngine(policy, APP, trusted_hosts=(AUTH,))
    login = f"https://{AUTH}/Account/Login"

    assert not plain.allows_request("GET", login, "document", ctx)[0]
    assert named.allows_request("GET", login, "document", ctx)[0]
    assert named.allows_request("POST", login, "document", ctx)[0]
    assert not named.allows_request("POST", f"https://{AUTH}/api/orders", "fetch", ctx)[0]
    assert not named.allows_request("GET", "https://evil.example.com/", "document", ctx)[0]


def test_passive_engine_never_posts_to_the_sso_host() -> None:
    passive = PolicyEngine(Policy(target_role="customer"), APP, passive=True, trusted_hosts=(AUTH,))
    assert not passive.allows_request(
        "POST", f"https://{AUTH}/Account/Login", "document", RequestContext()
    )[0]


def test_admin_guard_follows_the_same_rules() -> None:
    base = "https://app.example.uz/"
    plain = ProvisionGuard(base, HostGuard(allow_private=True), signed_in=True)
    named = ProvisionGuard(
        base, HostGuard(allow_private=True), signed_in=True, trusted_hosts=(AUTH,)
    )

    assert not plain.decide("GET", f"https://{AUTH}/.well-known/openid-configuration", "fetch")[0]
    assert named.decide("GET", f"https://{AUTH}/.well-known/openid-configuration", "fetch")[0]
    assert named.decide("POST", f"https://{AUTH}/connect/token", "fetch")[0]
    assert not named.decide("POST", f"https://{AUTH}/api/users", "fetch")[0]
    assert not named.decide("GET", f"https://{AUTH}/Account/LogOut", "document")[0]
    assert not named.decide("GET", "https://evil.example.com/", "document")[0]


def test_failed_login_attempt_does_not_leave_the_guard_signed_in() -> None:
    """A second way of signing in must be able to send its login request."""
    guard = ProvisionGuard("https://app.example.uz/", HostGuard(allow_private=True))
    guard.signed_in = True  # what a failed attempt used to leave behind
    assert not guard.decide("POST", "https://app.example.uz/Account/Login", "document")[0]
    guard.signed_in = False  # what the Provisioner now does before each way
    assert guard.decide("POST", "https://app.example.uz/Account/Login", "document")[0]
