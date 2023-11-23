#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Oathkeeper."""

import json
import logging
from typing import Dict, List, Optional

from charms.kratos.v0.kratos_endpoints import (
    KratosEndpointsRelationDataMissingError,
    KratosEndpointsRequirer,
)
from charms.oathkeeper.v0.auth_proxy import (
    AuthProxyConfigChangedEvent,
    AuthProxyConfigRemovedEvent,
    AuthProxyProvider,
)
from charms.oathkeeper.v0.forward_auth import (
    ForwardAuthConfig,
    ForwardAuthProvider,
    ForwardAuthProxySet,
    ForwardAuthRelationRemovedEvent,
    InvalidForwardAuthConfigEvent,
)
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from jinja2 import Template
from lightkube import Client
from lightkube.resources.apps_v1 import StatefulSet
from ops.charm import (
    ActionEvent,
    CharmBase,
    HookEvent,
    InstallEvent,
    PebbleReadyEvent,
    RelationChangedEvent,
    RemoveEvent,
)
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    Relation,
    WaitingStatus,
)
from ops.pebble import ChangeError, Error, ExecError, Layer
from tenacity import before_log, retry, stop_after_attempt, wait_exponential

import config_map
from config_map import AccessRulesConfigMap, OathkeeperConfigMap
from oathkeeper_cli import OathkeeperCLI

logger = logging.getLogger(__name__)

OATHKEEPER_API_PORT = 4456
PEER = "oathkeeper"


class OathkeeperCharm(CharmBase):
    """Charmed Ory Oathkeeper."""

    def __init__(self, *args):
        super().__init__(*args)

        self._container_name = "oathkeeper"
        self._service_name = "oathkeeper"
        self._container = self.unit.get_container(self._container_name)
        self._oathkeeper_config_dir_path = "/etc/config/oathkeeper"
        self._oathkeeper_config_file_path = "/etc/config/oathkeeper/oathkeeper.yaml"
        self._access_rules_dir_path = "/etc/config/access-rules"
        self._name = self.model.app.name
        self._oathkeeper_config_map_name = "oathkeeper-config"
        self._access_rules_config_map_name = "access-rules"

        self._kratos_relation_name = "kratos-endpoint-info"
        self._auth_proxy_relation_name = "auth-proxy"
        self._forward_auth_relation_name = "forward-auth"

        self.auth_proxy = AuthProxyProvider(self, relation_name=self._auth_proxy_relation_name)
        self.forward_auth = ForwardAuthProvider(
            self,
            relation_name=self._forward_auth_relation_name,
            forward_auth_config=self._forward_auth_config,
        )

        self.service_patcher = KubernetesServicePatch(
            self, [("oathkeeper-api", OATHKEEPER_API_PORT)]
        )

        self.kratos_endpoints = KratosEndpointsRequirer(
            self, relation_name=self._kratos_relation_name
        )

        self.client = Client(field_manager=self.app.name, namespace=self.model.name)
        self.oathkeeper_configmap = OathkeeperConfigMap(self.client, self)
        self.access_rules_configmap = AccessRulesConfigMap(self.client, self)

        self._oathkeeper_cli = OathkeeperCLI(
            f"http://localhost:{OATHKEEPER_API_PORT}",
            self._container,
        )

        self.ingress = IngressPerAppRequirer(
            self,
            relation_name="ingress",
            port=OATHKEEPER_API_PORT,
            strip_prefix=True,
            redirect_https=False,
        )

        self.framework.observe(self.on.oathkeeper_pebble_ready, self._on_oathkeeper_pebble_ready)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.remove, self._on_remove)

        self.framework.observe(
            self.auth_proxy.on.proxy_config_changed, self._on_auth_proxy_config_changed
        )
        self.framework.observe(
            self.auth_proxy.on.config_removed, self._remove_auth_proxy_configuration
        )

        self.framework.observe(
            self.forward_auth.on.forward_auth_proxy_set, self._on_forward_auth_proxy_set
        )
        self.framework.observe(
            self.forward_auth.on.invalid_forward_auth_config, self._on_invalid_forward_auth_config
        )
        self.framework.observe(
            self.forward_auth.on.forward_auth_relation_removed,
            self._on_forward_auth_relation_removed,
        )

        self.framework.observe(self.on.list_rules_action, self._on_list_rules_action)
        self.framework.observe(self.on.get_rule_action, self._on_get_rule_action)

        self.framework.observe(
            self.on[self._kratos_relation_name].relation_changed, self._on_kratos_relation_changed
        )
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

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
                    "command": f"oathkeeper serve -c {self._oathkeeper_config_file_path}",
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

    @property
    def _forward_auth_config(self) -> ForwardAuthConfig:
        return ForwardAuthConfig(
            decisions_address=f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{OATHKEEPER_API_PORT}/decisions",
            app_names=self.auth_proxy.get_app_names(),
            headers=self.auth_proxy.get_headers(),
        )

    @property
    def _kratos_login_url(self) -> Optional[str]:
        return self._get_kratos_endpoint_info("login_browser_endpoint")

    @property
    def _kratos_session_url(self) -> Optional[str]:
        return self._get_kratos_endpoint_info("sessions_endpoint")

    def _get_all_access_rules_repositories(self) -> Optional[List]:
        repositories = list()
        if cm_access_rules := self.access_rules_configmap.get():
            for key in cm_access_rules.keys():
                repositories.append(f"{self._access_rules_dir_path}/{key}")
        return repositories

    def _render_conf_file(self) -> str:
        """Render the Oathkeeper configuration file."""
        with open("templates/oathkeeper.yaml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            kratos_session_url=self._kratos_session_url,
            kratos_login_url=self._kratos_login_url,
            access_rules=self._get_all_access_rules_repositories(),
        )
        return rendered

    @retry(
        wait=wait_exponential(multiplier=3, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
        before=before_log(logger, logging.DEBUG),
    )
    def _update_config(self) -> None:
        conf = self._render_conf_file()
        self.oathkeeper_configmap.update({"oathkeeper.yaml": conf})

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

    def _auth_proxy_relation_peer_data_key(self, relation_id: int) -> str:
        return f"auth_proxy_{relation_id}"

    @property
    def _peers(self) -> Optional[Relation]:
        """Fetch the peer relation."""
        return self.model.get_relation(PEER)

    def _set_peer_data(self, key: str, data: Dict) -> None:
        """Put information into the peer data bucket."""
        if not (peers := self._peers):
            return
        peers.data[self.app][key] = json.dumps(data)

    def _get_peer_data(self, key: str) -> Dict:
        """Retrieve information from the peer data bucket."""
        if not (peers := self._peers):
            return {}
        data = peers.data[self.app].get(key, "")
        return json.loads(data) if data else {}

    def _pop_peer_data(self, key: str) -> Dict:
        """Retrieve and remove information from the peer data bucket."""
        if not (peers := self._peers):
            return {}
        data = peers.data[self.app].pop(key, "")
        return json.loads(data) if data else {}

    def _set_auth_proxy_relation_peer_data(self, relation_id: int, data: Dict) -> None:
        key = self._auth_proxy_relation_peer_data_key(relation_id)
        self._set_peer_data(key, data)

    def _get_auth_proxy_relation_peer_data(self, relation_id: int) -> Dict:
        key = self._auth_proxy_relation_peer_data_key(relation_id)
        return self._get_peer_data(key)

    def _pop_auth_proxy_relation_peer_data(self, relation_id: int) -> Dict:
        key = self._auth_proxy_relation_peer_data_key(relation_id)
        return self._pop_peer_data(key)

    def _patch_statefulset(self) -> None:
        pod_spec_patch = {
            "containers": [
                {
                    "name": self._container_name,
                    "volumeMounts": [
                        {
                            "mountPath": self._oathkeeper_config_dir_path,
                            "name": "config",
                            "readOnly": True,
                        },
                        {
                            "mountPath": self._access_rules_dir_path,
                            "name": "access-rules",
                            "readOnly": True,
                        },
                    ],
                },
            ],
            "volumes": [
                {
                    "name": "config",
                    "configMap": {"name": self._oathkeeper_config_map_name},
                },
                {
                    "name": "access-rules",
                    "configMap": {"name": self._access_rules_config_map_name},
                },
            ],
        }
        patch = {"spec": {"template": {"spec": pod_spec_patch}}}
        self.client.patch(StatefulSet, name=self.meta.name, namespace=self.model.name, obj=patch)

    def _on_install(self, event: InstallEvent) -> None:
        if not self.unit.is_leader():
            return

        config_map.create_all()
        self._update_config()

    def _on_oathkeeper_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Event Handler for pebble ready event."""
        self._patch_statefulset()
        self._handle_status_update_config(event)

    def _on_remove(self, event: RemoveEvent) -> None:
        if not self.unit.is_leader():
            return

        config_map.delete_all()

    def _on_kratos_relation_changed(self, event: RelationChangedEvent) -> None:
        self._handle_status_update_config(event)

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info(f"This app's ingress URL: {event.url}")

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")

    def _handle_status_update_config(self, event: HookEvent) -> None:
        """Handle unit status, update access rules and config file."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Oathkeeper container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Oathkeeper container")
            return

        self.unit.status = MaintenanceStatus("Configuring the container")

        self._update_config()
        self._container.add_layer(self._container_name, self._oathkeeper_layer, combine=True)

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

    def _on_invalid_forward_auth_config(self, event: InvalidForwardAuthConfigEvent) -> None:
        logger.info(
            "The forward-auth config is invalid: one or more of the related apps is missing ingress relation"
        )
        self.unit.status = BlockedStatus(event.error)

    def _on_forward_auth_proxy_set(self, event: ForwardAuthProxySet) -> None:
        logger.info("The proxy was set successfully")
        self.unit.status = ActiveStatus("Identity and Access Proxy is ready")

    def _on_forward_auth_relation_removed(self, event: ForwardAuthRelationRemovedEvent) -> None:
        logger.info("The proxy was unset")
        # The proxy was removed, but the charm is still functional
        self.unit.status = ActiveStatus()

    def _on_auth_proxy_config_changed(self, event: AuthProxyConfigChangedEvent) -> None:
        if not self._oathkeeper_service_is_running:
            self.unit.status = WaitingStatus("Waiting for Oathkeeper service")
            event.defer()
            return

        if not self._peers:
            self.unit.status = WaitingStatus("Waiting for peer relation")
            event.defer()
            return

        access_rules_filenames = list()
        for rule_type in ("allow", "deny"):
            rules = self._render_access_rules(
                rule_type=rule_type,
                protected_urls=event.protected_urls,
                allowed_endpoints=event.allowed_endpoints,
                relation_app_name=event.relation_app_name,
            )

            if rules:
                cm_name = f"access-rules-{event.relation_app_name}-{rule_type}.json"
                patch = {"data": {cm_name: str(rules)}}
                self.access_rules_configmap.patch(patch=patch, cm_name="access-rules")
                access_rules_filenames.append(cm_name)

        self._set_auth_proxy_relation_peer_data(
            event.relation_id, dict(access_rules_filenames=access_rules_filenames)
        )

        try:
            self._update_config()
        except Error as e:
            logger.error(f"Failed to set new config: {e}")
            self.unit.status = BlockedStatus("Failed to set new config, see logs")
            self._pop_auth_proxy_relation_peer_data(event.relation_id)
            return

        logger.info("Auth-proxy config has changed. Forward-auth relation will be updated")
        self.forward_auth.update_forward_auth_config(self._forward_auth_config)

    def _rule_template(
        self, rule_id: str, url: str, authenticator: str, mutator: str, error_handler: str
    ) -> Dict:
        return {
            "id": rule_id,
            "match": {"url": url, "methods": ["GET", "POST", "OPTION", "PUT", "PATCH", "DELETE"]},
            "authenticators": [{"handler": authenticator}],
            "mutators": [{"handler": mutator}],
            "authorizer": {"handler": "allow"},
            "errors": [{"handler": error_handler}],
        }

    def _render_access_rules(
        self,
        rule_type: str,
        protected_urls: List[str],
        allowed_endpoints: List[str],
        relation_app_name: str,
    ) -> Optional[List[Dict]]:
        """Render access rules from a template."""
        rules = list()

        for url_index, url in enumerate(protected_urls):
            # Parse url
            if url.endswith("/"):
                url = url[:-1]
            # Replace with regex to match both http and https
            url = url.replace("https", "<^(https|http)>")

            if rule_type == "allow":
                if not allowed_endpoints:
                    return None
                for endpoint in allowed_endpoints:
                    allow_rule = self._rule_template(
                        rule_id=f"{relation_app_name}:{endpoint}:{url_index}:allow",
                        url=f"{url}/{endpoint}",
                        authenticator="noop",
                        mutator="noop",
                        error_handler="json",
                    )

                    rules.append(allow_rule)

            if rule_type == "deny":
                if allowed_endpoints:
                    # Render a regex to exclude allowed endpoints
                    exclude_endpoints = [endpoint + "$" for endpoint in allowed_endpoints]

                    # Add | alternation
                    deny_regex = f"{url}/<(?!{'|'.join(exclude_endpoints)}).*>"
                else:
                    # Protect all endpoints
                    deny_regex = f"{url}/<.*>"

                deny_rule = self._rule_template(
                    rule_id=f"{relation_app_name}:{url_index}:deny",
                    url=deny_regex,
                    authenticator="cookie_session",
                    mutator="header",
                    error_handler="redirect",
                )

                rules.append(deny_rule)

        return rules

    def _remove_auth_proxy_configuration(self, event: AuthProxyConfigRemovedEvent) -> None:
        """Remove the auth-proxy-related config for a given relation."""
        if not self._peers:
            self.unit.status = WaitingStatus("Waiting for peer relation")
            event.defer()
            return

        peer_data = self._get_auth_proxy_relation_peer_data(event.relation_id)
        if not peer_data:
            logger.error("No access rules locations found in peer data")
            return

        self.access_rules_configmap.pop(keys=peer_data["access_rules_filenames"])
        self._pop_auth_proxy_relation_peer_data(event.relation_id)

        self._update_config()
        self.forward_auth.update_forward_auth_config(self._forward_auth_config)


if __name__ == "__main__":
    main(OathkeeperCharm)
