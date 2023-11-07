# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from httpx import Response
from lightkube import ApiError
from pytest_mock import MockerFixture

from charm import OathkeeperCharm
from config_map import AccessRulesConfigMap, ConfigMapBase, ConfigMapManager, OathkeeperConfigMap


@pytest.fixture
def mocked_charm() -> MagicMock:
    mock = MagicMock(spec=OathkeeperCharm)
    mock.model.name = "namespace"
    return mock


def test_create_all(lk_client: MagicMock, mocker: MockerFixture, mocked_charm: MagicMock) -> None:
    mock = mocker.patch("config_map.ConfigMapBase.create")
    OathkeeperConfigMap(lk_client, mocked_charm)
    AccessRulesConfigMap(lk_client, mocked_charm)

    ConfigMapManager.create_all()

    assert mock.call_count == 2


def test_delete_all(lk_client: MagicMock, mocker: MockerFixture, mocked_charm: MagicMock) -> None:
    mock = mocker.patch("config_map.ConfigMapBase.delete")
    OathkeeperConfigMap(lk_client, mocked_charm)
    AccessRulesConfigMap(lk_client, mocked_charm)

    ConfigMapManager.delete_all()

    assert mock.call_count == 2


@pytest.mark.parametrize("cls", (OathkeeperConfigMap, AccessRulesConfigMap))
def test_config_map_create(
    lk_client: MagicMock, cls: ConfigMapBase, mocked_charm: MagicMock
) -> None:
    resp = Response(status_code=403, json={"message": "Forbidden", "code": 403})
    lk_client.get.side_effect = ApiError(response=resp)
    cm = cls(lk_client, mocked_charm)

    cm.create()

    assert lk_client.create.call_args[0][0].metadata.name == cm.name


@pytest.mark.parametrize("cls", (OathkeeperConfigMap, AccessRulesConfigMap))
def test_create_map_already_exists(
    lk_client: MagicMock, cls: ConfigMapBase, mocked_charm: MagicMock
) -> None:
    cm = cls(lk_client, mocked_charm)

    cm.create()

    assert lk_client.get.called
    assert not lk_client.create.called


@pytest.mark.parametrize("cls", (OathkeeperConfigMap, AccessRulesConfigMap))
def test_config_map_update(
    lk_client: MagicMock, cls: ConfigMapBase, mocked_charm: MagicMock
) -> None:
    data = {"a": 1}
    cm = cls(lk_client, mocked_charm)

    cm.update(data)

    assert lk_client.replace.call_args[0][0].data == data


@pytest.mark.parametrize("cls", (OathkeeperConfigMap, AccessRulesConfigMap))
def test_config_map_patch(
    lk_client: MagicMock, cls: ConfigMapBase, mocked_charm: MagicMock
) -> None:
    patch = {"data": {"a": 1}}
    cm = cls(lk_client, mocked_charm)

    cm.patch(patch, "cm-name")

    assert lk_client.patch.called
    assert lk_client.patch.call_args[1]["obj"] == patch


@pytest.mark.parametrize("cls", (OathkeeperConfigMap, AccessRulesConfigMap))
def test_config_map_pop(
    lk_client: MagicMock,
    cls: ConfigMapBase,
    mocked_charm: MagicMock,
) -> None:
    cm = cls(lk_client, mocked_charm)

    cm.pop(keys=["some-key"])

    assert lk_client.replace.called


@pytest.mark.parametrize("cls", (OathkeeperConfigMap, AccessRulesConfigMap))
def test_update_map_error(
    lk_client: MagicMock, cls: ConfigMapBase, mocked_charm: MagicMock
) -> None:
    data = {"data": 1}
    resp = Response(status_code=403, json={"message": "Forbidden", "code": 403})
    lk_client.get.side_effect = ApiError(response=resp)
    cm = cls(lk_client, mocked_charm)

    cm.update(data)

    assert lk_client.get.called
    assert not lk_client.replace.called


@pytest.mark.parametrize("cls", (OathkeeperConfigMap, AccessRulesConfigMap))
def test_config_map_get(lk_client: MagicMock, cls: ConfigMapBase, mocked_charm: MagicMock) -> None:
    cm = cls(lk_client, mocked_charm)

    cm.get()

    assert lk_client.get.called


@pytest.mark.parametrize("cls", (OathkeeperConfigMap, AccessRulesConfigMap))
def test_get_map_error(lk_client: MagicMock, cls: ConfigMapBase, mocked_charm: MagicMock) -> None:
    resp = Response(status_code=403, json={"message": "Forbidden", "code": 403})
    lk_client.get.side_effect = ApiError(response=resp)
    cm = cls(lk_client, mocked_charm)

    d = cm.get()

    assert lk_client.get.called
    assert d == {}


@pytest.mark.parametrize("cls", (OathkeeperConfigMap, AccessRulesConfigMap))
def test_config_map_delete(
    lk_client: MagicMock,
    cls: ConfigMapBase,
    mocked_charm: MagicMock,
) -> None:
    cm = cls(lk_client, mocked_charm)

    cm.delete()

    assert lk_client.delete.called


@pytest.mark.parametrize("cls", (OathkeeperConfigMap, AccessRulesConfigMap))
def test_delete_map_error(
    lk_client: MagicMock, cls: ConfigMapBase, mocked_charm: MagicMock
) -> None:
    resp = Response(status_code=403, json={"message": "Forbidden", "code": 403})
    lk_client.delete.side_effect = ApiError(response=resp)
    cm = cls(lk_client, mocked_charm)

    with pytest.raises(ValueError):
        cm.delete()
