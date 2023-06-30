#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Oathkeeper."""

import logging

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from jinja2 import Template
from ops.charm import CharmBase, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ChangeError, Layer

logger = logging.getLogger(__name__)

OATHKEEPER_API_PORT = 4456


class OathkeeperCharm(CharmBase):
    """Charmed Ory Oathkeeper."""

    def __init__(self, *args):
        super().__init__(*args)

        self._container_name = "oathkeeper"
        self._service_name = "oathkeeper"
        self._container = self.unit.get_container(self._container_name)
        self._oathkeeper_config_path = "/etc/config/oathkeeper.yaml"
        self._oathkeeper_access_rules_path = "/etc/config/oathkeeper/access-rules.yaml"
        self._name = self.model.app.name

        self._kratos_login_url = (
            f"http://kratos.{self.model.name}.svc.cluster.local:4433/self-service/login/browser"
        )
        self._kratos_session_url = (
            f"http://kratos.{self.model.name}.svc.cluster.local:4433/sessions/whoami"
        )

        self.service_patcher = KubernetesServicePatch(
            self, [("oathkeeper-api", OATHKEEPER_API_PORT)]
        )

        self.framework.observe(self.on.oathkeeper_pebble_ready, self._on_oathkeeper_pebble_ready)

    @property
    def _oathkeeper_layer(self) -> Layer:
        """Returns a pre-configured Pebble layer."""
        layer_config = {
            "summary": "oathkeeper-operator layer",
            "description": "pebble config layer for oathkeeper-operator",
            "services": {
                self._service_name: {
                    "override": "replace",
                    "summary": "Oathkeeper Operator layer",
                    "command": f"oathkeeper serve -c {self._oathkeeper_config_path}",
                    "startup": "enabled",
                }
            },
            "checks": {
                "alive": {
                    "override": "replace",
                    "http": {"url": f"http://localhost:{OATHKEEPER_API_PORT}/health/alive"},
                },
                "ready": {
                    "override": "replace",
                    "http": {"url": f"http://localhost:{OATHKEEPER_API_PORT}/health/ready"},
                },
            },
        }
        return Layer(layer_config)

    def _render_access_rules_file(self) -> str:
        """Render the access rules file."""
        with open("templates/access-rules.yaml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            kratos_login_url=self._kratos_login_url,
            return_to="http://default-url.com",
        )
        return rendered

    def _render_conf_file(self) -> str:
        """Render the Oathkeeper configuration file."""
        with open("templates/oathkeeper.yaml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            kratos_session_url=self._kratos_session_url,
            kratos_login_url=self._kratos_login_url,
        )
        return rendered

    def _on_oathkeeper_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Event Handler for pebble ready event."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Oathkeeper container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Oathkeeper container")
            return

        self.unit.status = MaintenanceStatus("Configuring the container")

        self._container.add_layer(self._container_name, self._oathkeeper_layer, combine=True)

        self._container.push(
            self._oathkeeper_access_rules_path, self._render_access_rules_file(), make_dirs=True
        )
        self._container.push(
            self._oathkeeper_config_path, self._render_conf_file(), make_dirs=True
        )

        try:
            self._container.restart(self._container_name)
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus(
                "Failed to restart the container, please consult the logs"
            )
            return

        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(OathkeeperCharm)
