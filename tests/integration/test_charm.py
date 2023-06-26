#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import requests
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
TRAEFIK = "traefik-k8s"
TRAEFIK_EXTERNAL_NAME = "some_hostname"


async def get_unit_address(ops_test: OpsTest, app_name: str, unit_num: int) -> str:
    """Get private address of a unit."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


async def get_app_address(ops_test: OpsTest, app_name: str) -> str:
    """Get address of an app."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["public-address"]


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

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            raise_on_blocked=False,
            status="active",
            timeout=1000,
        )
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"


async def test_oathkeeper_scale_up(ops_test: OpsTest) -> None:
    """Check that oathkeeper works after it is scaled up."""
    app = ops_test.model.applications[APP_NAME]

    await app.scale(2)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    address = await get_app_address(ops_test, TRAEFIK)
    health_check_url = f"http://{address}/{ops_test.model.name}-{APP_NAME}/health/ready"
    resp = requests.get(health_check_url)

    assert resp.status_code == 200
