#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Oathkeeper."""

import logging
from typing import Optional

from charms.kratos.v0.kratos_endpoints import (
    KratosEndpointsRelationDataMissingError,
    KratosEndpointsRequirer,
)
from charms.oathkeeper.v0.auth_proxy import AuthProxyConfigRemovedEvent, AuthProxyProvider
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from jinja2 import Template
from ops.charm import ActionEvent, CharmBase, HookEvent, PebbleReadyEvent, RelationChangedEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus
from ops.pebble import ChangeError, Error, ExecError, Layer

from oathkeeper_cli import OathkeeperCLI

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

        self._kratos_relation_name = "kratos-endpoint-info"

        self.auth_proxy = AuthProxyProvider(self)

        self.service_patcher = KubernetesServicePatch(
            self, [("oathkeeper-api", OATHKEEPER_API_PORT)]
        )

        self.kratos_endpoints = KratosEndpointsRequirer(
            self, relation_name=self._kratos_relation_name
        )

        self._oathkeeper_cli = OathkeeperCLI(
            f"http://localhost:{OATHKEEPER_API_PORT}",
            self._container,
        )

        self.framework.observe(self.on.oathkeeper_pebble_ready, self._on_oathkeeper_pebble_ready)

        self.framework.observe(
            self.auth_proxy.on.config_changed, self._configure_auth_proxy_provider
        )
        self.framework.observe(
            self.auth_proxy.on.config_removed, self._remove_auth_proxy_configuration
        )

        self.framework.observe(self.on.list_rules_action, self._on_list_rules_action)
        self.framework.observe(self.on.get_rule_action, self._on_get_rule_action)

        self.framework.observe(
            self.on[self._kratos_relation_name].relation_changed, self._on_kratos_relation_changed
        )

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

    @property
    def _oathkeeper_service_is_running(self) -> bool:
        if not self._container.can_connect():
            return False

        try:
            service = self._container.get_service(self._service_name)
        except (ModelError, RuntimeError):
            return False
        return service.is_running()

    def _render_access_rules_file(self) -> str:
        """Render the access rules file."""
        with open("templates/access-rules.yaml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            kratos_login_url=self._get_kratos_endpoint_info("login_browser_endpoint"),
            return_to="http://default-url.com",
        )
        return rendered

    def _render_conf_file(self) -> str:
        """Render the Oathkeeper configuration file."""
        with open("templates/oathkeeper.yaml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            kratos_session_url=self._get_kratos_endpoint_info("sessions_endpoint"),
            kratos_login_url=self._get_kratos_endpoint_info("login_browser_endpoint"),
        )
        return rendered

    def _get_kratos_endpoint_info(self, key: str) -> Optional[str]:
        if not self.model.relations[self._kratos_relation_name]:
            logger.info("Kratos relation not found")
            return

        try:
            kratos_endpoints = self.kratos_endpoints.get_kratos_endpoints()
            return kratos_endpoints[key]
        except KratosEndpointsRelationDataMissingError:
            logger.info("No kratos-endpoint-info relation data found")
            return

    def _on_oathkeeper_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Event Handler for pebble ready event."""
        self._handle_status_update_config(event)

    def _on_kratos_relation_changed(self, event: RelationChangedEvent) -> None:
        self._handle_status_update_config(event)

    def _handle_status_update_config(self, event: HookEvent) -> None:
        """Handle unit status, update access rules and config file."""
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

    def _on_list_rules_action(self, event: ActionEvent) -> None:
        if not self._oathkeeper_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        limit = event.params["limit"]
        event.log("Fetching access rules")
        try:
            rules = self._oathkeeper_cli.list_rules(limit)
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log("Successfully listed rules")
        event.set_results({str(i): r["id"] for i, r in list(enumerate(rules))})

    def _on_get_rule_action(self, event: ActionEvent) -> None:
        if not self._oathkeeper_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        rule_id = event.params["rule-id"]
        event.log(f"Getting rule: {rule_id}")

        try:
            rule = self._oathkeeper_cli.get_rule(rule_id)
        except ExecError as err:
            if err.stderr and "Could not get rule" in err.stderr:
                event.log(f"No such rule: {rule_id}")
                event.fail("Rule not found")
                return
            event.fail(f"Exited with code: {err.exit_code}. Stderr: {err.stderr}")
            return
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log(f"Successfully fetched rule: {rule_id}")
        event.set_results(rule)

    def _configure_auth_proxy_provider(self, event: HookEvent) -> None:
        """Create access rules and update config."""
        pass

    def _remove_auth_proxy_configuration(self, event: AuthProxyConfigRemovedEvent) -> None:
        """Remove the auth-proxy-related config for a given relation."""
        pass


if __name__ == "__main__":
    main(OathkeeperCharm)
