# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Dict, Generator
from unittest.mock import MagicMock

import pytest
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import OathkeeperCharm


@pytest.fixture()
def harness(mocked_kubernetes_service_patcher: Generator) -> Generator[Harness, None, None]:
    harness = Harness(OathkeeperCharm)
    harness.set_model_name("testing")
    harness.set_leader(True)
    harness.begin()
    yield harness
    harness.cleanup()


@pytest.fixture()
def mocked_kubernetes_service_patcher(mocker: MockerFixture) -> MagicMock:
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    return mocked_service_patcher


@pytest.fixture()
def mocked_oathkeeper_is_running(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.OathkeeperCharm._oathkeeper_service_is_running", return_value=True)


@pytest.fixture()
def oathkeeper_cli_rule() -> Dict:
    return {
        "id": "sample-rule:protected",
        "authenticators": [{"handler": "cookie_session"}],
        "authorizer": {"handler": "allow"},
        "match": {"methods": ["GET", "POST"], "url": "http://some-url:8080/<.*>"},
        "mutators": [{"handler": "header"}],
    }


@pytest.fixture()
def mocked_get_rule(mocker: MockerFixture, oathkeeper_cli_rule: Dict) -> MagicMock:
    mock = mocker.patch("charm.OathkeeperCLI.get_rule", return_value=oathkeeper_cli_rule)
    return mock


@pytest.fixture()
def mocked_list_rules(mocker: MockerFixture, oathkeeper_cli_rule: Dict) -> MagicMock:
    mock = mocker.patch(
        "charm.OathkeeperCLI.list_rules",
        return_value=[dict(oathkeeper_cli_rule, id=f"rule-{i}") for i in range(5)],
    )
    return mock
