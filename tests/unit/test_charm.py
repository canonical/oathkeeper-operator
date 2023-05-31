# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops.testing import Harness

from charm import OathkeeperCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(OathkeeperCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
