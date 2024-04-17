# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from typing import Any, Dict, Generator, List

import pytest
from charms.oathkeeper.v0.auth_proxy import (
    AuthProxyConfig,
    AuthProxyConfigError,
    AuthProxyRequirer,
    InvalidAuthProxyConfigEvent,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: requirer-tester
requires:
  auth-proxy:
    interface: auth_proxy
"""

AUTH_PROXY_CONFIG = {
    "protected_urls": ["https://example.com"],
    "allowed_endpoints": ["welcome", "about/app"],
    "headers": ["X-User"],
}


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(AuthProxyRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


def dict_to_relation_data(dic: Dict) -> Dict:
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


class AuthProxyRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        auth_proxy_config = AuthProxyConfig(**AUTH_PROXY_CONFIG)
        self.auth_proxy = AuthProxyRequirer(self, auth_proxy_config=auth_proxy_config)

        self.events: List = []
        self.framework.observe(self.auth_proxy.on.invalid_auth_proxy_config, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


def test_data_in_relation_bag(harness: Harness) -> None:
    relation_id = harness.add_relation("auth-proxy", "provider")
    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert relation_data == dict_to_relation_data(AUTH_PROXY_CONFIG)


def test_warning_when_http_protected_url_provided(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    """Check that a warning appears when one of the provided urls uses http scheme."""
    caplog.set_level(logging.WARNING)
    auth_proxy_config = AuthProxyConfig(**AUTH_PROXY_CONFIG)
    auth_proxy_config.protected_urls = ["https://some-url.com", "http://some-other-url.com"]

    harness.charm.auth_proxy.update_auth_proxy_config(auth_proxy_config=auth_proxy_config)
    assert (
        f"Provided URL {auth_proxy_config.protected_urls[1]} uses http scheme. In order to make the Identity Platform work with the Proxy, run kratos in dev mode: `juju config kratos dev=True`. Don't do this in production"
        in caplog.text
    )


def test_exception_raised_when_invalid_protected_url(harness: Harness) -> None:
    auth_proxy_config = AuthProxyConfig(**AUTH_PROXY_CONFIG)
    auth_proxy_config.protected_urls = ["https://some-valid-url.com", "invalid-url"]

    with pytest.raises(
        AuthProxyConfigError, match=f"Invalid URL {auth_proxy_config.protected_urls[1]}"
    ):
        harness.charm.auth_proxy.update_auth_proxy_config(auth_proxy_config=auth_proxy_config)


def test_exception_raised_when_invalid_header(harness: Harness) -> None:
    auth_proxy_config = AuthProxyConfig(**AUTH_PROXY_CONFIG)
    auth_proxy_config.headers = ["X-User", "X-Invalid-Header"]

    with pytest.raises(AuthProxyConfigError, match="Unsupported header"):
        harness.charm.auth_proxy.update_auth_proxy_config(auth_proxy_config=auth_proxy_config)


class InvalidConfigAuthProxyRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        auth_proxy_config = AuthProxyConfig(**AUTH_PROXY_CONFIG)
        auth_proxy_config.headers = ["X-Invalid-Header"]
        self.auth_proxy = AuthProxyRequirer(self, auth_proxy_config=auth_proxy_config)

        self.events: List = []
        self.framework.observe(self.auth_proxy.on.invalid_auth_proxy_config, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def harness_invalid_config() -> Generator:
    harness = Harness(InvalidConfigAuthProxyRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


def test_event_emitted_when_invalid_auth_proxy_config(harness_invalid_config: Harness) -> None:
    harness_invalid_config.add_relation("auth-proxy", "provider")

    assert any(
        isinstance(e, InvalidAuthProxyConfigEvent) for e in harness_invalid_config.charm.events
    )
