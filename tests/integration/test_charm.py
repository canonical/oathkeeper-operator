#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from os.path import join
from pathlib import Path
from typing import Dict, List, Optional

import pytest
import requests
import yaml
from lightkube import ApiError, Client
from lightkube.resources.core_v1 import ConfigMap, Service
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
CA_CHARM = "self-signed-certificates"
TRAEFIK = "traefik-k8s"
AUTH_PROXY_REQUIRER = "auth-proxy-requirer"


async def get_k8s_service_address(ops_test: OpsTest, service_name: str, lightkube_client: Client) -> Optional[str]:
    """Get the address of a LoadBalancer Kubernetes service using kubectl."""
    try:
        result = lightkube_client.get(Service, name=service_name, namespace=ops_test.model.name)
        ip_address = result.status.loadBalancer.ingress[0].ip
        return ip_address
    except ApiError as e:
        logger.error(f"Error retrieving service address: {e}")
        return None


async def get_reverse_proxy_app_url(
    ops_test: OpsTest, ingress_app_name: str, app_name: str, lightkube_client: Client
) -> str:
    """Get the ingress address of an app."""
    address = await get_k8s_service_address(ops_test, f"{ingress_app_name}-lb", lightkube_client)
    proxy_app_url = f"http://{address}/{ops_test.model.name}-{app_name}/"
    logger.debug(f"Retrieved address: {proxy_app_url}")
    return proxy_app_url


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    """Build and deploy oathkeeper."""
    charm = await ops_test.build_charm(".")
    oathkeeper_image_path = METADATA["resources"]["oci-image"]["upstream-source"]

    await ops_test.model.deploy(
        application_name=APP_NAME,
        entity_url=charm,
        resources={"oci-image": oathkeeper_image_path},
        series="jammy",
        trust=True,
    )

    await ops_test.model.wait_for_idle(
        raise_on_blocked=False,
        raise_on_error=False,
        status="active",
        timeout=1000,
    )
    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"


@pytest.mark.abort_on_fail
async def test_auth_proxy_relation(ops_test: OpsTest, copy_libraries_into_tester_charm) -> None:
    """Ensure that oathkeeper is able to provide auth-proxy relation."""
    requirer_charm_path = Path(f"tests/integration/{AUTH_PROXY_REQUIRER}").absolute()
    requirer_charm = await ops_test.build_charm(requirer_charm_path, verbosity="debug")

    await ops_test.model.deploy(
        TRAEFIK,
        channel="latest/edge",
        trust=True,
    )

    await ops_test.model.deploy(
        application_name=AUTH_PROXY_REQUIRER,
        entity_url=requirer_charm,
        resources={"oci-image": "kennethreitz/httpbin"},
        series="jammy",
        trust=True,
    )

    await ops_test.model.integrate(f"{AUTH_PROXY_REQUIRER}:ingress", TRAEFIK)
    await ops_test.model.integrate(f"{AUTH_PROXY_REQUIRER}:auth-proxy", APP_NAME)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, AUTH_PROXY_REQUIRER, TRAEFIK],
        status="active",
        raise_on_blocked=False,
        timeout=1000,
    )


@pytest.mark.abort_on_fail
async def test_forward_auth_relation(ops_test: OpsTest) -> None:
    """Ensure that oathkeeper is able to provide forward-auth relation."""
    await ops_test.model.applications[TRAEFIK].set_config({
        "enable_experimental_forward_auth": "True"
    })
    await ops_test.model.integrate(f"{TRAEFIK}:experimental-forward-auth", APP_NAME)

    await ops_test.model.wait_for_idle([TRAEFIK, APP_NAME], status="active", timeout=1000)


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=20),
    stop=stop_after_attempt(20),
    reraise=True,
)
async def test_allowed_forward_auth_url_redirect(ops_test: OpsTest, lightkube_client: Client) -> None:
    """Test that a request hitting a protected application is forwarded by traefik to oathkeeper.

    An allowed request should be performed without authentication.
    Retry the request to ensure the access rules were populated by oathkeeper.
    """
    requirer_url = await get_reverse_proxy_app_url(ops_test, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client)

    protected_url = join(requirer_url, "anything/allowed")

    resp = requests.get(protected_url, verify=False)
    assert resp.status_code == 200


async def test_protected_forward_auth_url_redirect(ops_test: OpsTest, lightkube_client: Client) -> None:
    """Test reaching a protected url.

    The request should be forwarded by traefik to oathkeeper.
    An unauthenticated request should then be denied with 401 Unauthorized response.
    """
    requirer_url = await get_reverse_proxy_app_url(ops_test, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client)

    protected_url = join(requirer_url, "anything/deny")

    resp = requests.get(protected_url, verify=False)
    assert resp.status_code == 401


async def test_forward_auth_url_response_headers(
    ops_test: OpsTest, lightkube_client: Client
) -> None:
    """Test that a response mutated by oathkeeper contains expected custom headers."""
    requirer_url = await get_reverse_proxy_app_url(ops_test, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client)
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

    update_access_rules_configmap(ops_test, lightkube_client, rule=anonymous_rule)
    update_config_configmap(ops_test, lightkube_client)

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
    ops_test: OpsTest, lightkube_client: Client, rule: List[Dict]
) -> None:
    """Modify the ConfigMap to force access rules update.

    This is a workaround to test response headers without deploying identity-platform bundle.
    The anonymous authenticator is used only for testing purposes.
    """
    cm = lightkube_client.get(ConfigMap, "access-rules", namespace=ops_test.model.name)
    data = {"access-rules-iap-requirer-anonymous.json": str(rule)}
    cm.data = data
    lightkube_client.replace(cm)


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=10),
    stop=stop_after_attempt(5),
    reraise=True,
)
def update_config_configmap(ops_test: OpsTest, lightkube_client: Client) -> None:
    """Modify the ConfigMap to force config file update.

    This is required to include the custom anonymous rule.
    """
    cm = lightkube_client.get(ConfigMap, name="oathkeeper-config", namespace=ops_test.model.name)
    cm = yaml.safe_load(cm.data["oathkeeper.yaml"])
    cm["access_rules"]["repositories"] = [
        "file://etc/config/access-rules/access-rules-iap-requirer-anonymous.json"
    ]
    patch = {"data": {"oathkeeper.yaml": yaml.dump(cm)}}
    lightkube_client.patch(
        ConfigMap, name="oathkeeper-config", namespace=ops_test.model.name, obj=patch
    )


async def test_oathkeeper_scale_up(ops_test: OpsTest) -> None:
    """Check that oathkeeper works after it is scaled up."""
    app = ops_test.model.applications[APP_NAME]

    await app.scale(2)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
        wait_for_active=True,
    )


async def test_oathkeeper_scale_down(ops_test: OpsTest) -> None:
    """Check that oathkeeper works after it is scaled down."""
    app = ops_test.model.applications[APP_NAME]

    await app.scale(1)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
        wait_for_active=True,
    )


async def test_remove_forward_auth_integration(ops_test: OpsTest) -> None:
    """Ensure that the forward-auth relation doesn't cause errors on removal."""
    await ops_test.juju("remove-relation", APP_NAME, f"{TRAEFIK}:experimental-forward-auth")

    await ops_test.model.wait_for_idle([TRAEFIK, APP_NAME], status="active")


async def test_remove_auth_proxy_integration(ops_test: OpsTest) -> None:
    """Ensure that the auth-proxy relation doesn't cause errors on removal."""
    await ops_test.juju("remove-relation", APP_NAME, f"{AUTH_PROXY_REQUIRER}:auth-proxy")

    await ops_test.model.wait_for_idle([APP_NAME, AUTH_PROXY_REQUIRER], status="active")


async def test_list_rules(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[APP_NAME]
        .units[0]
        .run_action(
            "list-rules",
        )
    )
    res = (await action.wait()).results

    assert len(res) > 0


async def test_certificates_relation(ops_test: OpsTest) -> None:
    """Test the TLS certificates relation."""
    await ops_test.model.deploy(
        CA_CHARM,
        channel="edge",
        trust=True,
    )

    await ops_test.model.add_relation(CA_CHARM, f"{APP_NAME}:certificates")

    await ops_test.model.wait_for_idle([APP_NAME, CA_CHARM], status="active", timeout=1000)
