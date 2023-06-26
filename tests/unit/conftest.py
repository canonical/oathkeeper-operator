# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Generator

import pytest
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import OathkeeperCharm


@pytest.fixture()
def harness(mocked_kubernetes_service_patcher: Generator) -> Generator[Harness, None, None]:
    harness = Harness(OathkeeperCharm)
    harness.set_model_name("testing")
    harness.set_leader(True)
    harness.begin()
    yield harness
    harness.cleanup()


@pytest.fixture()
def mocked_kubernetes_service_patcher(mocker: MockerFixture) -> Generator:
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    yield mocked_service_patcher
