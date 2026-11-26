# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import platform
import secrets
import shutil
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Callable, Generator, Optional, Tuple

import jubilant
import pytest
from lightkube import Client

AUTH_PROXY_REQUIRER = "auth-proxy-requirer"

StatusPredicate = Callable[[jubilant.Status], bool]


def all_active(*apps: str) -> StatusPredicate:
    """Return a predicate that checks all given apps are active and agents idle."""
    return lambda status: (
        jubilant.all_active(status, *apps) and jubilant.all_agents_idle(status, *apps)
    )


def any_error(*apps: str) -> StatusPredicate:
    """Return a predicate that checks any given app is in error state."""
    return lambda status: jubilant.any_error(status, *apps)


def unit_number(app: str, expected_num: int) -> StatusPredicate:
    """Return a predicate that checks the unit count of an app."""
    return lambda status: app in status.apps and len(status.apps[app].units) == expected_num


def and_(*predicates: StatusPredicate) -> StatusPredicate:
    """Combine multiple status predicates with logical AND."""
    return lambda status: all(predicate(status) for predicate in predicates)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options for model management and deployment control."""
    parser.addoption(
        "--keep-models",
        "--no-teardown",
        action="store_true",
        dest="no_teardown",
        default=False,
        help="Keep the model after the test is finished.",
    )
    parser.addoption(
        "--model",
        action="store",
        dest="model",
        default=None,
        help="The model to run the tests on.",
    )
    parser.addoption(
        "--no-deploy",
        "--no-setup",
        action="store_true",
        dest="no_setup",
        default=False,
        help="Skip deployment of the charm.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for test selection."""
    config.addinivalue_line("markers", "setup: tests that setup some parts of the environment")
    config.addinivalue_line(
        "markers", "teardown: tests that teardown some parts of the environment."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip setup/teardown tests when --no-setup or --no-teardown is passed."""
    skip_setup = pytest.mark.skip(reason="no_setup provided")
    skip_teardown = pytest.mark.skip(reason="no_teardown provided")
    for item in items:
        if config.getoption("no_setup") and "setup" in item.keywords:
            item.add_marker(skip_setup)
        if config.getoption("no_teardown") and "teardown" in item.keywords:
            item.add_marker(skip_teardown)


def juju_model_factory(model_name: str) -> Tuple[jubilant.Juju, bool]:
    """Create or connect to a Juju model and return (Juju, created)."""
    juju = jubilant.Juju()
    created = False
    try:
        juju.add_model(model_name, config={"logging-config": "<root>=INFO;unit=DEBUG"})
        created = True
    except jubilant.CLIError as e:
        if "already exists" not in e.stderr:
            raise
        juju.model = model_name

    if created or os.getenv("CI"):
        arch_map = {
            "aarch64": "arm64",
            "arm64": "arm64",
            "x86_64": "amd64",
            "amd64": "amd64",
        }
        host_arch = arch_map.get(platform.machine().lower(), "amd64")
        juju.cli("set-model-constraints", f"arch={host_arch}")

    return juju, created


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    """Create a temporary Juju model for integration tests."""
    model_name = request.config.getoption("--model") or f"test-oathkeeper-{secrets.token_hex(4)}"
    juju_, created = juju_model_factory(model_name)
    juju_.wait_timeout = 10 * 60

    try:
        yield juju_
    finally:
        if request.session.testsfailed:
            print(juju_.debug_log(limit=1000), end="")

        no_teardown = bool(request.config.getoption("--no-teardown"))
        keep_model = no_teardown or request.session.testsfailed > 0 or not created
        if not keep_model:
            with suppress(jubilant.CLIError):
                juju_.destroy_model(
                    model_name,
                    destroy_storage=True,
                    force=True,
                    timeout=600,
                )


@pytest.fixture(scope="module")
def lightkube_client(juju: jubilant.Juju) -> Client:
    return Client(field_manager="oathkeeper", namespace=juju.model)


@pytest.fixture(scope="module")
def copy_libraries_into_tester_charm() -> None:
    """Ensure the tester charm has the required libraries."""
    libraries = [
        "traefik_k8s/v2/ingress.py",
        "oathkeeper/v0/auth_proxy.py",
    ]

    for lib in libraries:
        install_path = f"tests/integration/{AUTH_PROXY_REQUIRER}/lib/charms/{lib}"
        os.makedirs(os.path.dirname(install_path), exist_ok=True)
        shutil.copyfile(f"lib/charms/{lib}", install_path)


def build_charm_artifact(charm_dir: Path) -> Path:
    """Build a charm in charm_dir and return its artifact path."""
    subprocess.run(["charmcraft", "pack"], cwd=charm_dir, check=True)

    charms = list(charm_dir.glob("*.charm"))
    if not charms:
        raise RuntimeError(f"Charm not found and build failed in {charm_dir}")
    return max(charms, key=lambda p: p.stat().st_mtime).absolute()


@pytest.fixture(scope="session")
def local_charm() -> Path:
    """Get the local charm path from CHARM_PATH or charmcraft pack."""
    # in GitHub CI, charms are built with charmcraftcache and uploaded to $CHARM_PATH
    charm: Optional[str] = os.getenv("CHARM_PATH")
    if not charm:
        return build_charm_artifact(Path("."))
    return Path(charm).absolute()


@pytest.fixture(scope="module")
def requirer_charm(copy_libraries_into_tester_charm: None) -> Path:
    """Pack and return the auth-proxy-requirer tester charm."""
    return build_charm_artifact(Path(f"tests/integration/{AUTH_PROXY_REQUIRER}").absolute())
