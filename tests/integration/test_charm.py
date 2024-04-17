#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CA_CHARM = "self-signed-certificates"


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

    await ops_test.model.wait_for_idle(
        raise_on_blocked=False,
        raise_on_error=False,
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

    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"
    assert ops_test.model.applications[APP_NAME].units[1].workload_status == "active"


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
