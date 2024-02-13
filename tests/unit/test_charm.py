# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from typing import Optional, Tuple
from unittest.mock import MagicMock, Mock

import pytest
import yaml
from capture_events import capture_events
from charms.oathkeeper.v0.oathkeeper_info import OathkeeperInfoRelationCreatedEvent
from jinja2 import Template
from ops.model import ActiveStatus, WaitingStatus
from ops.pebble import ExecError
from ops.testing import Harness

ACCESS_RULES_PATH = "/etc/config/access-rules"
CONFIG_FILE_PATH = "/etc/config/oathkeeper/oathkeeper.yaml"
CONTAINER_NAME = "oathkeeper"
SERVICE_NAME = "oathkeeper"


def setup_ingress_relation(harness: Harness) -> Tuple[int, str]:
    """Set up ingress relation."""
    relation_id = harness.add_relation("ingress", "traefik")
    harness.add_relation_unit(relation_id, "traefik/0")
    url = f"http://ingress:80/{harness.model.name}-oathkeeper"
    harness.update_relation_data(
        relation_id,
        "traefik",
        {"ingress": json.dumps({"url": url})},
    )
    return relation_id, url


def setup_certificates_relation(harness: Harness) -> int:
    """Set up tls certificates relation."""
    relation_id = harness.add_relation("certificates", "certificates-provider")
    harness.add_relation_unit(relation_id, "certificates-provider/0")

    return relation_id


def setup_kratos_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("kratos-endpoint-info", "kratos")
    harness.add_relation_unit(relation_id, "kratos/0")
    harness.update_relation_data(
        relation_id,
        "kratos",
        {
            "admin_endpoint": f"http://kratos-admin-url:80/{harness.model.name}-kratos",
            "public_endpoint": f"http://kratos-public-url:80/{harness.model.name}-kratos",
            "login_browser_endpoint": f"http://kratos-public-url:80/{harness.model.name}-kratos/self-service/login/browser",
            "sessions_endpoint": f"http://kratos-admin-url:80/{harness.model.name}-kratos/sessions/whoami",
        },
    )
    return relation_id


def setup_oathkeeper_info_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("oathkeeper-info", "requirer")
    harness.add_relation_unit(relation_id, "requirer/0")
    harness.update_relation_data(
        relation_id,
        "requirer",
        {
            "access_rules_file": "requirer-access_rules.json",
        },
    )

    return relation_id


def setup_peer_relation(harness: Harness) -> Tuple[int, str]:
    app_name = "oathkeeper"
    relation_id = harness.add_relation("oathkeeper", app_name)
    return relation_id, app_name


def setup_auth_proxy_relation(
    harness: Harness, app_name: Optional[str] = "requirer"
) -> Tuple[int, str]:
    relation_id = harness.add_relation("auth-proxy", app_name)
    harness.add_relation_unit(relation_id, f"{app_name}/0")
    harness.update_relation_data(
        relation_id,
        app_name,
        {
            "protected_urls": '["https://example.com"]',
            "allowed_endpoints": '["welcome", "about/app"]',
            "headers": '["X-User"]',
        },
    )

    return relation_id, app_name


def setup_forward_auth_relation(harness: Harness) -> Tuple[int, str]:
    relation_id = harness.add_relation("forward-auth", "requirer")
    harness.add_relation_unit(relation_id, "requirer/0")
    harness.update_relation_data(
        relation_id,
        "requirer",
        {
            "ingress_app_names": '["charmed-app"]',
        },
    )

    return relation_id


def setup_auth_proxy_relation_without_allowed_endpoints(harness: Harness) -> Tuple[int, str]:
    app_name = "requirer"
    relation_id = harness.add_relation("auth-proxy", app_name)
    harness.add_relation_unit(relation_id, "requirer/0")
    harness.update_relation_data(
        relation_id,
        "requirer",
        {
            "protected_urls": '["https://example.com"]',
            "allowed_endpoints": "[]",
            "headers": '["X-User"]',
        },
    )

    return relation_id, app_name


def test_pebble_container_can_connect(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.oathkeeper_pebble_ready.emit(CONTAINER_NAME)

    assert isinstance(harness.charm.unit.status, ActiveStatus)
    service = harness.model.unit.get_container(CONTAINER_NAME).get_service("oathkeeper")
    assert service.is_running()


def test_pebble_container_cannot_connect(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    harness.charm.on.oathkeeper_pebble_ready.emit(CONTAINER_NAME)

    assert harness.charm.unit.status == WaitingStatus("Waiting to connect to Oathkeeper container")


def test_ingress_relation_created(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, url = setup_ingress_relation(harness)
    assert url == "http://ingress:80/testing-oathkeeper"

    app_data = harness.get_relation_data(relation_id, harness.charm.app)
    assert app_data == {
        "model": json.dumps(harness.model.name),
        "name": json.dumps("oathkeeper"),
        "port": json.dumps(4456),
        "scheme": json.dumps("http"),
        "strip-prefix": json.dumps(True),
        "redirect-https": json.dumps(False),
    }


def test_ingress_relation_revoked(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, _ = setup_ingress_relation(harness)
    caplog.clear()
    harness.remove_relation(relation_id)

    assert "This app no longer has ingress" in caplog.record_tuples[2]


def test_on_pebble_ready_lk_called(harness: Harness, lk_client: MagicMock) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.oathkeeper_pebble_ready.emit(container)

    lk_client.patch.assert_called_once()


def test_update_container_config_without_kratos_relation(
    harness: Harness, mocked_oathkeeper_configmap: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    harness.charm.on.oathkeeper_pebble_ready.emit(CONTAINER_NAME)

    with open("templates/oathkeeper.yaml.j2", "r") as file:
        template = Template(file.read())

    expected_config = template.render(
        kratos_session_url=None,
        kratos_login_url=None,
    )

    configmap = mocked_oathkeeper_configmap.update.call_args_list[-1][0][0]
    config = configmap["oathkeeper.yaml"]
    assert yaml.safe_load(expected_config) == yaml.safe_load(config)


def test_update_container_config_with_kratos_relation(
    harness: Harness, mocked_oathkeeper_configmap: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    kratos_relation_id = setup_kratos_relation(harness)

    with open("templates/oathkeeper.yaml.j2", "r") as file:
        template = Template(file.read())

    expected_config = template.render(
        kratos_session_url=harness.get_relation_data(kratos_relation_id, "kratos")[
            "sessions_endpoint"
        ],
        kratos_login_url=harness.get_relation_data(kratos_relation_id, "kratos")[
            "login_browser_endpoint"
        ],
    )

    configmap = mocked_oathkeeper_configmap.update.call_args_list[-1][0][0]
    config = configmap["oathkeeper.yaml"]
    assert yaml.safe_load(expected_config) == yaml.safe_load(config)


def test_on_pebble_ready_correct_plan(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.oathkeeper_pebble_ready.emit(container)

    expected_plan = {
        "services": {
            SERVICE_NAME: {
                "override": "replace",
                "summary": "Oathkeeper Operator layer",
                "startup": "enabled",
                "command": f"oathkeeper serve -c {CONFIG_FILE_PATH}",
            }
        },
        "checks": {
            "alive": {
                "override": "replace",
                "http": {"url": "http://localhost:4456/health/alive"},
            },
        },
    }
    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    assert expected_plan == updated_plan


def test_on_pebble_ready_statefulset_patched(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm._patch_statefulset = mocked_handle = Mock(return_value=None)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.oathkeeper_pebble_ready.emit(container)

    assert mocked_handle.called


def test_list_rules_action(
    harness: Harness, mocked_oathkeeper_is_running: MagicMock, mocked_list_rules: MagicMock
) -> None:
    event = MagicMock()
    harness.charm._on_list_rules_action(event)

    expected_output = {"rule-0", "rule-1", "rule-2", "rule-3", "rule-4"}
    assert set(event.set_results.call_args_list[0][0][0].values()) == expected_output


def test_get_rule_action(
    harness: Harness, mocked_oathkeeper_is_running: MagicMock, mocked_get_rule: MagicMock
) -> None:
    rule_id = mocked_get_rule.return_value["id"]
    event = MagicMock()
    event.params = {"rule-id": rule_id}

    harness.charm._on_get_rule_action(event)

    expected_output = {
        "id": "sample-rule:protected",
        "authenticators": [{"handler": "cookie_session"}],
        "authorizer": {"handler": "allow"},
        "match": {"methods": ["GET", "POST"], "url": "http://some-url:8080/<.*>"},
        "mutators": [{"handler": "header"}],
    }

    event.set_results.assert_called_with(expected_output)


def test_generic_error_on_get_rule_action(
    harness: Harness, mocked_oathkeeper_is_running: MagicMock, mocked_get_rule: MagicMock
) -> None:
    event = MagicMock()
    mocked_get_rule.side_effect = ExecError(
        command=["oathkeeper", "get", "rule"],
        exit_code=1,
        stdout="",
        stderr="Error",
    )

    harness.charm._on_get_rule_action(event)

    event.fail.assert_called()


def test_generic_error_on_list_rules_action(
    harness: Harness, mocked_oathkeeper_is_running: MagicMock, mocked_list_rules: MagicMock
) -> None:
    event = MagicMock()
    mocked_list_rules.side_effect = ExecError(
        command=["oathkeeper", "list", "rules"],
        exit_code=1,
        stdout="",
        stderr="Error",
    )

    harness.charm._on_list_rules_action(event)

    event.fail.assert_called()


def test_rule_not_found_on_get_rule_action(
    harness: Harness, mocked_oathkeeper_is_running: MagicMock, mocked_get_rule: MagicMock
) -> None:
    event = MagicMock()
    event.params = {"rule-id": "unexisting_rule_id"}
    mocked_get_rule.side_effect = ExecError(
        command=["oathkeeper", "get", "rule", event.params, "--endpoint", "http://localhost:4456"],
        exit_code=1,
        stdout="",
        stderr="Could not get rule",
    )

    harness.charm._on_get_rule_action(event)

    event.fail.assert_called_with("Rule not found")


@pytest.mark.parametrize(
    "action",
    [
        "_on_get_rule_action",
        "_on_list_rules_action",
    ],
)
def test_actions_when_cannot_connect(harness: Harness, action: str) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    event = MagicMock()

    getattr(harness.charm, action)(event)

    event.fail.assert_called_with(
        "Service is not ready. Please re-run the action when the charm is active"
    )


def test_oathkeeper_not_ready_on_auth_proxy_config_changed(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_auth_proxy_relation(harness)
    assert harness.charm.unit.status == WaitingStatus("Waiting for Oathkeeper service")


def test_no_peer_relation_on_auth_proxy_config_changed(
    harness: Harness, mocked_oathkeeper_is_running: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_auth_proxy_relation(harness)

    assert harness.charm.unit.status == WaitingStatus("Waiting for peer relation")


def test_config_file_updated_with_access_rules_locations(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_oathkeeper_configmap: MagicMock,
    mocked_get_repositories: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_peer_relation(harness)

    relation_id, app_name = setup_auth_proxy_relation(harness)

    with open("templates/oathkeeper.yaml.j2", "r") as file:
        template = Template(file.read())

    expected_config = template.render(
        kratos_session_url=None,
        kratos_login_url=None,
        access_rules=[
            f"{ACCESS_RULES_PATH}/access-rules-{app_name}-allow.json",
            f"{ACCESS_RULES_PATH}/access-rules-{app_name}-deny.json",
        ],
    )

    configmap = mocked_oathkeeper_configmap.update.call_args_list[-1][0][0]
    container_config = configmap["oathkeeper.yaml"]

    assert yaml.safe_load(container_config) == yaml.safe_load(expected_config)


def test_config_file_updated_when_multiple_auth_proxy_relations(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_oathkeeper_configmap: MagicMock,
    mocked_get_repositories_for_multiple_relations: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    peer_relation_id, _ = setup_peer_relation(harness)

    requirer_relation_id, requirer_app_name = setup_auth_proxy_relation(harness)
    other_requirer_relation_id, other_requirer_app_name = setup_auth_proxy_relation(
        harness, app_name="other-requirer"
    )

    with open("templates/oathkeeper.yaml.j2", "r") as file:
        template = Template(file.read())

    expected_config = template.render(
        kratos_session_url=None,
        kratos_login_url=None,
        access_rules=[
            f"{ACCESS_RULES_PATH}/access-rules-{requirer_app_name}-allow.json",
            f"{ACCESS_RULES_PATH}/access-rules-{requirer_app_name}-deny.json",
            f"{ACCESS_RULES_PATH}/access-rules-{other_requirer_app_name}-allow.json",
            f"{ACCESS_RULES_PATH}/access-rules-{other_requirer_app_name}-deny.json",
        ],
    )

    configmap = mocked_oathkeeper_configmap.update.call_args_list[-1][0][0]
    container_config = configmap["oathkeeper.yaml"]
    assert yaml.safe_load(container_config) == yaml.safe_load(expected_config)


def test_allow_access_rules_rendering(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_access_rules_configmap: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_peer_relation(harness)

    relation_id, app_name = setup_auth_proxy_relation(harness)

    expected_allow_rules = [
        {
            "id": f"{app_name}:welcome:0:allow",
            "match": {
                "url": "<^(https|http)>://example.com/<welcome((/.*$)|$)>",
                "methods": ["GET", "POST", "OPTION", "PUT", "PATCH", "DELETE"],
            },
            "authenticators": [{"handler": "noop"}],
            "mutators": [{"handler": "noop"}],
            "authorizer": {"handler": "allow"},
            "errors": [{"handler": "json"}],
        },
        {
            "id": f"{app_name}:about/app:0:allow",
            "match": {
                "url": "<^(https|http)>://example.com/<about/app((/.*$)|$)>",
                "methods": ["GET", "POST", "OPTION", "PUT", "PATCH", "DELETE"],
            },
            "authenticators": [{"handler": "noop"}],
            "mutators": [{"handler": "noop"}],
            "authorizer": {"handler": "allow"},
            "errors": [{"handler": "json"}],
        },
    ]

    configmap_data = mocked_access_rules_configmap.patch.call_args_list[0][1]
    container_allow_rules = configmap_data["patch"]["data"][f"access-rules-{app_name}-allow.json"]
    assert str(expected_allow_rules) == container_allow_rules


def test_allow_access_rules_not_rendered_when_no_allowed_endpoints_provided(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_access_rules_configmap: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_peer_relation(harness)

    relation_id, app_name = setup_auth_proxy_relation_without_allowed_endpoints(harness)

    configmap_data = mocked_access_rules_configmap.patch.call_args_list[0][1]
    container_allow_rules = configmap_data["patch"]["data"]

    assert f"access-rules-{app_name}-allow.json" not in container_allow_rules


def test_allow_access_rules_rendering_when_auth_proxy_config_changed(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_access_rules_configmap: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_peer_relation(harness)

    relation_id, app_name = setup_auth_proxy_relation(harness)

    harness.update_relation_data(
        relation_id,
        "requirer",
        {
            "protected_urls": '["https://example.com", "https://other-example.com"]',
            "allowed_endpoints": '["welcome"]',
        },
    )

    expected_allow_rules = [
        {
            "id": f"{app_name}:welcome:0:allow",
            "match": {
                "url": "<^(https|http)>://example.com/<welcome((/.*$)|$)>",
                "methods": ["GET", "POST", "OPTION", "PUT", "PATCH", "DELETE"],
            },
            "authenticators": [{"handler": "noop"}],
            "mutators": [{"handler": "noop"}],
            "authorizer": {"handler": "allow"},
            "errors": [{"handler": "json"}],
        },
        {
            "id": f"{app_name}:welcome:1:allow",
            "match": {
                "url": "<^(https|http)>://other-example.com/<welcome((/.*$)|$)>",
                "methods": ["GET", "POST", "OPTION", "PUT", "PATCH", "DELETE"],
            },
            "authenticators": [{"handler": "noop"}],
            "mutators": [{"handler": "noop"}],
            "authorizer": {"handler": "allow"},
            "errors": [{"handler": "json"}],
        },
    ]

    configmap_data = mocked_access_rules_configmap.patch.call_args_list[2][1]
    container_allow_rules = configmap_data["patch"]["data"][f"access-rules-{app_name}-allow.json"]
    assert str(expected_allow_rules) == container_allow_rules


def test_deny_access_rules_rendering_when_single_protected_url_provided(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_access_rules_configmap: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_peer_relation(harness)

    relation_id, app_name = setup_auth_proxy_relation(harness)

    expected_deny_rules = [
        {
            "id": f"{app_name}:0:deny",
            "match": {
                "url": "<^(https|http)>://example.com<(?!/welcome((/.*$)|$)|/about/app((/.*$)|$)).*>",
                "methods": ["GET", "POST", "OPTION", "PUT", "PATCH", "DELETE"],
            },
            "authenticators": [{"handler": "cookie_session"}],
            "mutators": [{"handler": "header"}],
            "authorizer": {"handler": "allow"},
            "errors": [{"handler": "redirect"}],
        },
    ]

    configmap_data = mocked_access_rules_configmap.patch.call_args_list[1][1]
    container_deny_rules = configmap_data["patch"]["data"][f"access-rules-{app_name}-deny.json"]
    assert str(expected_deny_rules) == container_deny_rules


def test_deny_access_rules_rendering_when_multiple_protected_urls_provided(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_access_rules_configmap: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_peer_relation(harness)

    relation_id, app_name = setup_auth_proxy_relation(harness)

    harness.update_relation_data(
        relation_id,
        "requirer",
        {
            "protected_urls": '["https://example.com/unit-0", "https://example.com/unit-1"]',
        },
    )

    expected_deny_rules = [
        {
            "id": f"{app_name}:0:deny",
            "match": {
                "url": "<^(https|http)>://example.com/unit-0<(?!/welcome((/.*$)|$)|/about/app((/.*$)|$)).*>",
                "methods": ["GET", "POST", "OPTION", "PUT", "PATCH", "DELETE"],
            },
            "authenticators": [{"handler": "cookie_session"}],
            "mutators": [{"handler": "header"}],
            "authorizer": {"handler": "allow"},
            "errors": [{"handler": "redirect"}],
        },
        {
            "id": f"{app_name}:1:deny",
            "match": {
                "url": "<^(https|http)>://example.com/unit-1<(?!/welcome((/.*$)|$)|/about/app((/.*$)|$)).*>",
                "methods": ["GET", "POST", "OPTION", "PUT", "PATCH", "DELETE"],
            },
            "authenticators": [{"handler": "cookie_session"}],
            "mutators": [{"handler": "header"}],
            "authorizer": {"handler": "allow"},
            "errors": [{"handler": "redirect"}],
        },
    ]

    configmap_data = mocked_access_rules_configmap.patch.call_args_list[3][1]
    container_deny_rules = configmap_data["patch"]["data"][f"access-rules-{app_name}-deny.json"]
    assert str(expected_deny_rules) == container_deny_rules


def test_all_endpoints_protected_when_no_allowed_endpoints_provided(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_access_rules_configmap: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_peer_relation(harness)

    relation_id, app_name = setup_auth_proxy_relation_without_allowed_endpoints(harness)

    expected_deny_rules = [
        {
            "id": f"{app_name}:0:deny",
            "match": {
                "url": "<^(https|http)>://example.com<.*>",
                "methods": ["GET", "POST", "OPTION", "PUT", "PATCH", "DELETE"],
            },
            "authenticators": [{"handler": "cookie_session"}],
            "mutators": [{"handler": "header"}],
            "authorizer": {"handler": "allow"},
            "errors": [{"handler": "redirect"}],
        },
    ]

    configmap_data = mocked_access_rules_configmap.patch.call_args_list[0][1]
    container_deny_rules = configmap_data["patch"]["data"][f"access-rules-{app_name}-deny.json"]

    assert str(expected_deny_rules) == container_deny_rules


def test_peer_data_set_on_auth_proxy_config_changed(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    peer_relation_id, _ = setup_peer_relation(harness)
    relation_id, _ = setup_auth_proxy_relation(harness)
    auth_proxy_peer_id = f"auth_proxy_{relation_id}"

    peer_data = '{"access_rules_filenames": ["access-rules-requirer-allow.json", "access-rules-requirer-deny.json"]}'
    assert harness.get_relation_data(peer_relation_id, harness.charm.app) == {
        auth_proxy_peer_id: peer_data
    }


def test_no_peer_relation_on_auth_proxy_config_removed(
    harness: Harness, mocked_oathkeeper_is_running: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, _ = setup_auth_proxy_relation(harness)

    harness.remove_relation(relation_id)

    assert harness.charm.unit.status == WaitingStatus("Waiting for peer relation")


def test_peer_data_pop_on_auth_proxy_config_removed(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    peer_relation_id, _ = setup_peer_relation(harness)
    relation_id, _ = setup_auth_proxy_relation(harness)

    harness.remove_relation(relation_id)

    assert harness.get_relation_data(peer_relation_id, harness.charm.app) == {}


def test_access_rules_pop_from_configmap_on_auth_proxy_config_removed(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_access_rules_configmap: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    peer_relation_id, _ = setup_peer_relation(harness)
    relation_id, app_name = setup_auth_proxy_relation(harness)
    harness.charm.access_rules_configmap.pop = mocked_handle = Mock(return_value=None)

    harness.remove_relation(relation_id)

    configmap_keys = mocked_access_rules_configmap.pop.call_args_list[0][1]["keys"]
    mocked_handle.assert_called_with(keys=configmap_keys)


def test_peer_data_when_multiple_auth_proxy_relations(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    peer_relation_id, _ = setup_peer_relation(harness)

    requirer_relation_id, requirer_app_name = setup_auth_proxy_relation(harness)
    requirer_auth_proxy_peer_id = f"auth_proxy_{requirer_relation_id}"

    other_requirer_relation_id, other_requirer_app_name = setup_auth_proxy_relation(
        harness, app_name="other-requirer"
    )
    other_requirer_auth_proxy_peer_id = f"auth_proxy_{other_requirer_relation_id}"

    requirer_peer_data = '{"access_rules_filenames": ["access-rules-requirer-allow.json", "access-rules-requirer-deny.json"]}'
    other_requirer_peer_data = '{"access_rules_filenames": ["access-rules-other-requirer-allow.json", "access-rules-other-requirer-deny.json"]}'

    assert harness.get_relation_data(peer_relation_id, harness.charm.app) == {
        requirer_auth_proxy_peer_id: requirer_peer_data,
        other_requirer_auth_proxy_peer_id: other_requirer_peer_data,
    }


def test_forward_auth_relation_removed(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id = setup_forward_auth_relation(harness)
    harness.remove_relation(relation_id)

    assert "The proxy was unset" in caplog.record_tuples[0]
    assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_certificates_relation_databag(
    harness: Harness, mocked_oathkeeper_is_running: MagicMock
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    peer_relation_id, _ = setup_peer_relation(harness)
    relation_id = setup_certificates_relation(harness)

    unit_databag = harness.get_relation_data(relation_id, harness.charm.unit.name)
    assert unit_databag.get("certificate_signing_requests") is not None


def test_certificates_creation_requested(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_request_certificate_creation: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    peer_relation_id, _ = setup_peer_relation(harness)
    _ = setup_certificates_relation(harness)

    assert harness.charm._sans_dns == f"{SERVICE_NAME}.{harness.model.name}.svc.cluster.local"
    mocked_request_certificate_creation.assert_called()


def test_forward_auth_config_updated_on_tls_set_up(
    harness: Harness,
    mocked_oathkeeper_is_running: MagicMock,
    mocked_update_forward_auth: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    peer_relation_id, _ = setup_peer_relation(harness)
    _ = setup_certificates_relation(harness)

    harness.charm.cert_handler.on.cert_changed.emit()

    mocked_update_forward_auth.assert_called()


def test_oathkeeper_info_ready_event_emitted_when_relation_created(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    with capture_events(harness.charm) as captured:
        _ = setup_oathkeeper_info_relation(harness)

    assert any(isinstance(e, OathkeeperInfoRelationCreatedEvent) for e in captured)


def test_oathkeeper_info_updated_on_relation_ready(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.info_provider.send_info_relation_data = mocked_handle = Mock(return_value=None)
    _ = setup_oathkeeper_info_relation(harness)

    mocked_handle.assert_called_with(
        public_endpoint="http://oathkeeper.testing.svc.cluster.local:4456",
        rules_configmap_name="access-rules",
        configmaps_namespace="testing",
    )


def test_config_file_includes_oathkeeper_info_requirer_rules(
    harness: Harness,
    mocked_oathkeeper_configmap: MagicMock,
    mocked_oathkeeper_access_rules_list: MagicMock,
) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.oathkeeper_pebble_ready.emit(CONTAINER_NAME)
    _ = setup_oathkeeper_info_relation(harness)

    with open("templates/oathkeeper.yaml.j2", "r") as file:
        template = Template(file.read())

    expected_config = template.render(
        access_rules=[
            "requirer-access-rules.json",
        ],
    )

    configmap = mocked_oathkeeper_configmap.update.call_args_list[-1][0][0]
    container_config = configmap["oathkeeper.yaml"]

    assert yaml.safe_load(container_config) == yaml.safe_load(expected_config)
