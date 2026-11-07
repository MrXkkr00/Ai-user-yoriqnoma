"""Test settings: Huey runs tasks inline instead of queueing them (ARCHITECTURE §9)."""

from yoriqnoma_local.settings import *  # noqa: F403
from yoriqnoma_local.settings import HUEY

HUEY = {**HUEY, "immediate": True}
