"""End-to-end test profile (docker/compose.test.yml): production settings plus two things.

* ``demo_shop`` (the test site's container, a private Docker address) may be visited;
  no other private address. Production (prod.py) allows none (TZ SEC-10).
* Plain HTTP on 127.0.0.1:8000 for the test client (no Caddy, no TLS).
"""

from yoriqnoma_server.settings.prod import *  # noqa: F403

YORIQNOMA_PRIVATE_ALLOWLIST = ["demo_shop"]
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "web"]
