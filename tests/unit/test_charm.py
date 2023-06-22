# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Tuple

import yaml
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

CONTAINER_NAME = "oathkeeper"


def setup_ingress_relation(harness: Harness) -> Tuple[int, str]:
    """Set up ingress relation."""
    harness.set_leader(True)
    relation_id = harness.add_relation("ingress", "traefik")
    harness.add_relation_unit(relation_id, "traefik/0")
    url = f"http://ingress:80/{harness.model.name}-oathkeeper"
    harness.update_relation_data(
        relation_id,
        "traefik",
        {"ingress": json.dumps({"url": url})},
    )
    return relation_id, url


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


def test_update_container_config(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    harness.charm.on.oathkeeper_pebble_ready.emit(CONTAINER_NAME)

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "serve": {
            "api": {
                "cors": {
                    "enabled": True,
                    "allowed_origins": ["*"],
                },
            },
        },
        "errors": {
            "fallback": ["json"],
            "handlers": {
                "redirect": {
                    "enabled": True,
                    "config": {
                        "to": "http://kratos.testing.svc.cluster.local:4433/self-service/login/browser",
                        "when": [
                            {
                                "error": ["unauthorized", "forbidden"],
                                "request": {
                                    "header": {
                                        "accept": ["text/html"],
                                    },
                                },
                            }
                        ],
                    },
                },
                "json": {
                    "enabled": True,
                },
            },
        },
        "access_rules": {
            "matching_strategy": "regexp",
            "repositories": ["file:///etc/config/oathkeeper/access-rules.yaml"],
        },
        "authenticators": {
            "noop": {
                "enabled": True,
            },
            "cookie_session": {
                "enabled": True,
                "config": {
                    "check_session_url": "http://kratos.testing.svc.cluster.local:4433/sessions/whoami",
                    "preserve_path": True,
                    "extra_from": "@this",
                    "subject_from": "identity.id",
                    "only": ["ory_kratos_session"],
                },
            },
        },
        "authorizers": {
            "allow": {
                "enabled": True,
            },
        },
        "mutators": {
            "noop": {
                "enabled": True,
            },
            "header": {
                "enabled": True,
                "config": {
                    "headers": {
                        "X-User": "{{ print .Subject }}",
                    },
                },
            },
        },
    }

    assert yaml.safe_load(harness.charm._render_conf_file()) == expected_config


def test_on_pebble_ready_correct_plan(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.oathkeeper_pebble_ready.emit(container)

    expected_plan = {
        "services": {
            CONTAINER_NAME: {
                "override": "replace",
                "summary": "Oathkeeper Operator layer",
                "startup": "enabled",
                "command": "oathkeeper serve -c /etc/config/oathkeeper.yaml",
            }
        }
    }
    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    assert expected_plan == updated_plan


def test_ingress_relation_created(harness: Harness, mocked_fqdn) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    relation_id, url = setup_ingress_relation(harness)
    assert url == "http://ingress:80/testing-oathkeeper"

    app_data = harness.get_relation_data(relation_id, harness.charm.app)
    assert app_data == {
        "host": mocked_fqdn.return_value,
        "model": harness.model.name,
        "name": "oathkeeper",
        "port": "4456",
        "strip-prefix": "true",
    }
