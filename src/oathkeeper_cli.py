# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""A helper class for interacting with the Oathkeeper CLI."""


import json
import logging
from typing import Dict, List, Tuple, Union

from ops.model import Container

logger = logging.getLogger(__name__)


class OathkeeperCLI:
    """Helper object for running Oathkeeper CLI commands."""

    def __init__(self, oathkeeper_api_url: str, container: Container):
        self.oathkeeper_api_url = oathkeeper_api_url
        self.container = container

    def _run_cmd(
        self, cmd: List[str], timeout: float = 20
    ) -> Tuple[Union[str, bytes], Union[str, bytes]]:
        logger.debug(f"Running cmd: {cmd}")
        process = self.container.exec(cmd, timeout=timeout)
        stdout, stderr = process.wait_output()
        return stdout, stderr

    def list_rules(self, limit: int) -> Dict:
        """List access rules."""
        cmd = [
            "oathkeeper",
            "rules",
            "list",
            "--endpoint",
            self.oathkeeper_api_url,
            "--limit",
            limit,
        ]

        stdout, _ = self._run_cmd(cmd)
        return json.loads(stdout)

    def get_rule(self, rule_id: str) -> Dict:
        """Get an access rule content by id."""
        cmd = [
            "oathkeeper",
            "rules",
            "get",
            rule_id,
            "--endpoint",
            self.oathkeeper_api_url,
        ]

        stdout, _ = self._run_cmd(cmd)
        return json.loads(stdout)
