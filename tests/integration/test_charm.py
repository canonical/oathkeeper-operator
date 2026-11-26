#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from os.path import join
from pathlib import Path
from typing import Dict, List, Optional

import jubilant
import pytest
import requests
import yaml
from lightkube import ApiError, Client
from lightkube.resources.core_v1 import ConfigMap, Service
from tenacity import retry, stop_after_attempt, wait_exponential

from tests.integration.conftest import all_active, and_, any_error, unit_number

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
CA_CHARM = "self-signed-certificates"
TRAEFIK = "traefik-k8s"
AUTH_PROXY_REQUIRER = "auth-proxy-requirer"


def get_k8s_service_address(
    juju: jubilant.Juju, service_name: str, lightkube_client: Client
) -> Optional[str]:
    """Get the address of a LoadBalancer Kubernetes service using lightkube."""
    try:
        result = lightkube_client.get(Service, name=service_name, namespace=juju.model)
        ip_address = result.status.loadBalancer.ingress[0].ip
        return ip_address
    except ApiError as e:
        logger.error(f"Error retrieving service address: {e}")
        return None


def get_reverse_proxy_app_url(
    juju: jubilant.Juju, ingress_app_name: str, app_name: str, lightkube_client: Client
) -> str:
    """Get the ingress address of an app."""
    address = get_k8s_service_address(juju, f"{ingress_app_name}-lb", lightkube_client)
    proxy_app_url = f"http://{address}/{juju.model}-{app_name}/"
    logger.debug(f"Retrieved address: {proxy_app_url}")
    return proxy_app_url


@pytest.mark.setup
def test_build_and_deploy(juju: jubilant.Juju, local_charm: Path) -> None:
    """Build and deploy oathkeeper."""
    oathkeeper_image_path = METADATA["resources"]["oci-image"]["upstream-source"]

    juju.deploy(
        charm=str(local_charm),
        app=APP_NAME,
        resources={"oci-image": oathkeeper_image_path},
        base="ubuntu@22.04",
        trust=True,
    )

    juju.wait(
        ready=all_active(APP_NAME),
        error=any_error(APP_NAME),
        timeout=1000,
    )


@pytest.mark.setup
def test_auth_proxy_relation(juju: jubilant.Juju, requirer_charm: Path) -> None:
    """Ensure that oathkeeper is able to provide auth-proxy relation."""
    juju.deploy(
        TRAEFIK,
        channel="latest/edge",
        trust=True,
    )

    juju.deploy(
        charm=str(requirer_charm),
        app=AUTH_PROXY_REQUIRER,
        resources={"oci-image": "kennethreitz/httpbin"},
        base="ubuntu@22.04",
        trust=True,
    )

    juju.integrate(f"{AUTH_PROXY_REQUIRER}:ingress", TRAEFIK)
    juju.integrate(f"{AUTH_PROXY_REQUIRER}:auth-proxy", APP_NAME)

    juju.wait(
        ready=all_active(APP_NAME, AUTH_PROXY_REQUIRER, TRAEFIK),
        error=any_error(APP_NAME, AUTH_PROXY_REQUIRER, TRAEFIK),
        timeout=1000,
    )


@pytest.mark.setup
def test_forward_auth_relation(juju: jubilant.Juju) -> None:
    """Ensure that oathkeeper is able to provide forward-auth relation."""
    juju.config(TRAEFIK, {"enable_experimental_forward_auth": "True"})
    juju.integrate(f"{TRAEFIK}:experimental-forward-auth", APP_NAME)

    juju.wait(
        ready=all_active(TRAEFIK, APP_NAME),
        error=any_error(TRAEFIK, APP_NAME),
        timeout=1000,
    )


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=20),
    stop=stop_after_attempt(20),
    reraise=True,
)
def test_allowed_forward_auth_url_redirect(juju: jubilant.Juju, lightkube_client: Client) -> None:
    """Test that a request hitting a protected application is forwarded by traefik to oathkeeper.

    An allowed request should be performed without authentication.
    Retry the request to ensure the access rules were populated by oathkeeper.
    """
    requirer_url = get_reverse_proxy_app_url(juju, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client)

    protected_url = join(requirer_url, "anything/allowed")

    resp = requests.get(protected_url, verify=False)
    assert resp.status_code == 200


def test_protected_forward_auth_url_redirect(
    juju: jubilant.Juju, lightkube_client: Client
) -> None:
    """Test reaching a protected url.

    The request should be forwarded by traefik to oathkeeper.
    An unauthenticated request should then be denied with 401 Unauthorized response.
    """
    requirer_url = get_reverse_proxy_app_url(juju, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client)

    protected_url = join(requirer_url, "anything/deny")

    resp = requests.get(protected_url, verify=False)
    assert resp.status_code == 401


def test_forward_auth_url_response_headers(juju: jubilant.Juju, lightkube_client: Client) -> None:
    """Test that a response mutated by oathkeeper contains expected custom headers."""
    requirer_url = get_reverse_proxy_app_url(juju, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client)
    protected_url = join(requirer_url, "anything/anonymous")

    # Push an anonymous access rule as a workaround to avoid deploying identity-platform bundle
    anonymous_rule = [
        {
            "id": "iap-requirer:anonymous",
            "match": {
                "url": protected_url,
                "methods": ["GET", "POST", "OPTION", "PUT", "PATCH", "DELETE"],
            },
            "authenticators": [{"handler": "anonymous"}],
            "mutators": [{"handler": "header"}],
            "authorizer": {"handler": "allow"},
            "errors": [{"handler": "json"}],
        }
    ]

    update_access_rules_configmap(juju, lightkube_client, rule=anonymous_rule)
    update_config_configmap(juju, lightkube_client)

    assert_anonymous_response(protected_url)


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=20),
    stop=stop_after_attempt(20),
    reraise=True,
)
def assert_anonymous_response(url: str) -> None:
    resp = requests.get(url, verify=False)
    assert resp.status_code == 200

    headers = json.loads(resp.content).get("headers")
    assert headers["X-User"] == "anonymous"


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=10),
    stop=stop_after_attempt(5),
    reraise=True,
)
def update_access_rules_configmap(
    juju: jubilant.Juju, lightkube_client: Client, rule: List[Dict]
) -> None:
    """Modify the ConfigMap to force access rules update.

    This is a workaround to test response headers without deploying identity-platform bundle.
    The anonymous authenticator is used only for testing purposes.
    """
    cm = lightkube_client.get(ConfigMap, "access-rules", namespace=juju.model)
    data = {"access-rules-iap-requirer-anonymous.json": str(rule)}
    cm.data = data
    lightkube_client.replace(cm)


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=10),
    stop=stop_after_attempt(5),
    reraise=True,
)
def update_config_configmap(juju: jubilant.Juju, lightkube_client: Client) -> None:
    """Modify the ConfigMap to force config file update.

    This is required to include the custom anonymous rule.
    """
    cm = lightkube_client.get(ConfigMap, name="oathkeeper-config", namespace=juju.model)
    config = yaml.safe_load(cm.data["oathkeeper.yaml"])
    config["access_rules"]["repositories"] = [
        "file://etc/config/access-rules/access-rules-iap-requirer-anonymous.json"
    ]
    patch = {"data": {"oathkeeper.yaml": yaml.dump(config)}}
    lightkube_client.patch(ConfigMap, name="oathkeeper-config", namespace=juju.model, obj=patch)


def test_oathkeeper_scale_up(juju: jubilant.Juju) -> None:
    """Check that oathkeeper works after it is scaled up."""
    juju.cli("scale-application", APP_NAME, "2")

    juju.wait(
        ready=and_(all_active(APP_NAME), unit_number(APP_NAME, 2)),
        error=any_error(APP_NAME),
        timeout=1000,
    )


def test_oathkeeper_scale_down(juju: jubilant.Juju) -> None:
    """Check that oathkeeper works after it is scaled down."""
    juju.cli("scale-application", APP_NAME, "1")

    juju.wait(
        ready=and_(all_active(APP_NAME), unit_number(APP_NAME, 1)),
        error=any_error(APP_NAME),
        timeout=1000,
    )


def test_remove_forward_auth_integration(juju: jubilant.Juju) -> None:
    """Ensure that the forward-auth relation doesn't cause errors on removal."""
    juju.remove_relation(APP_NAME, f"{TRAEFIK}:experimental-forward-auth")

    juju.wait(
        ready=all_active(TRAEFIK, APP_NAME),
        error=any_error(TRAEFIK, APP_NAME),
        timeout=1000,
    )


def test_remove_auth_proxy_integration(juju: jubilant.Juju) -> None:
    """Ensure that the auth-proxy relation doesn't cause errors on removal."""
    juju.remove_relation(APP_NAME, f"{AUTH_PROXY_REQUIRER}:auth-proxy")

    juju.wait(
        ready=all_active(APP_NAME, AUTH_PROXY_REQUIRER),
        error=any_error(APP_NAME, AUTH_PROXY_REQUIRER),
        timeout=1000,
    )


def test_list_rules(juju: jubilant.Juju) -> None:
    task = juju.run(f"{APP_NAME}/0", "list-rules")

    assert len(task.results) > 0


def test_certificates_relation(juju: jubilant.Juju) -> None:
    """Test the TLS certificates relation."""
    juju.deploy(
        CA_CHARM,
        channel="latest/stable",
        trust=True,
    )

    juju.integrate(CA_CHARM, f"{APP_NAME}:certificates")

    juju.wait(
        ready=all_active(APP_NAME, CA_CHARM),
        error=any_error(APP_NAME, CA_CHARM),
        timeout=1000,
    )
