# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


import yaml
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

CONTAINER_NAME = "oathkeeper"
SERVICE_NAME = "oathkeeper"


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


def test_update_container_config_without_kratos_relation(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)

    harness.charm.on.oathkeeper_pebble_ready.emit(CONTAINER_NAME)
    container = harness.model.unit.get_container(CONTAINER_NAME)

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
                        "to": "http://default-kratos-url/self-service/login/browser",
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
                    "check_session_url": "http://default-kratos-url/sessions/whoami",
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

    container_config = container.pull(path="/etc/config/oathkeeper.yaml", encoding="utf-8")
    assert yaml.safe_load(container_config.read()) == expected_config


def test_update_container_config_with_kratos_relation(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, True)
    kratos_relation_id = setup_kratos_relation(harness)

    harness.charm.on.oathkeeper_pebble_ready.emit(CONTAINER_NAME)
    container = harness.model.unit.get_container(CONTAINER_NAME)

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
                        "to": harness.get_relation_data(kratos_relation_id, "kratos")[
                            "login_browser_endpoint"
                        ],
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
                    "check_session_url": harness.get_relation_data(kratos_relation_id, "kratos")[
                        "sessions_endpoint"
                    ],
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

    container_config = container.pull(path="/etc/config/oathkeeper.yaml", encoding="utf-8")
    assert yaml.safe_load(container_config.read()) == expected_config


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
                "command": "oathkeeper serve -c /etc/config/oathkeeper.yaml",
            }
        }
    }
    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    assert expected_plan == updated_plan
