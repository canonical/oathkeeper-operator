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


@pytest.fixture(autouse=True)
def lk_client(mocker: MockerFixture) -> None:
    mock_lightkube = mocker.patch("charm.Client", autospec=True)
    return mock_lightkube.return_value


@pytest.fixture(autouse=True)
def mocked_oathkeeper_configmap(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.OathkeeperConfigMap", autospec=True)
    return mock.return_value


@pytest.fixture(autouse=True)
def mocked_access_rules_configmap(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.AccessRulesConfigMap", autospec=True)
    mock.return_value.name = "access-rules"
    return mock.return_value


@pytest.fixture()
def mocked_get_repositories(mocker: MockerFixture) -> MagicMock:
    repositories = [
        "/etc/config/access-rules/access-rules-requirer-allow.json",
        "/etc/config/access-rules/access-rules-requirer-deny.json",
    ]
    return mocker.patch(
        "charm.OathkeeperCharm._get_all_access_rules_repositories", return_value=repositories
    )


@pytest.fixture()
def mocked_get_repositories_for_multiple_relations(mocker: MockerFixture) -> MagicMock:
    repositories = [
        "/etc/config/access-rules/access-rules-requirer-allow.json",
        "/etc/config/access-rules/access-rules-requirer-deny.json",
        "/etc/config/access-rules/access-rules-other-requirer-allow.json",
        "/etc/config/access-rules/access-rules-other-requirer-deny.json",
    ]
    return mocker.patch(
        "charm.OathkeeperCharm._get_all_access_rules_repositories", return_value=repositories
    )


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


@pytest.fixture()
def mocked_request_certificate_creation(mocker: MockerFixture) -> MagicMock:
    mocked_request_certificate_creation = mocker.patch(
        "charms.tls_certificates_interface.v2.tls_certificates.TLSCertificatesRequiresV2.request_certificate_creation"
    )
    return mocked_request_certificate_creation


@pytest.fixture()
def mocked_update_forward_auth(mocker: MockerFixture) -> MagicMock:
    mocked_update_forward_auth = mocker.patch(
        "charms.oathkeeper.v0.forward_auth.ForwardAuthProvider.update_forward_auth_config"
    )
    return mocked_update_forward_auth


@pytest.fixture()
def mocked_oathkeeper_access_rules_list(mocker: MockerFixture) -> MagicMock:
    mocked_oathkeeper_access_rules_list = mocker.patch(
        "charm.OathkeeperCharm._get_all_access_rules_repositories"
    )
    mocked_oathkeeper_access_rules_list.return_value = ["requirer-access-rules.json"]
    return mocked_oathkeeper_access_rules_list


@pytest.fixture()
def mocked_auth_proxy_headers(mocker: MockerFixture) -> MagicMock:
    mocked_auth_proxy_headers = mocker.patch(
        "charms.oathkeeper.v0.auth_proxy.AuthProxyProvider.get_headers",
        return_value=["X-Name", "X-Email"],
    )
    return mocked_auth_proxy_headers
