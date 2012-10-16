from __future__ import unicode_literals

import os

from twisted.trial import unittest


example_file_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.path.pardir,
    os.path.pardir,
    "share",
    "example-tilde.ini",
)

from tilde.loader import load_config
from tilde.commands import ubuntu

class LoadTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(example_file_path)

    def test_resulting_config(self):
        srv = self.cfg["servers"]
        self.assertIn("foo", srv)
        self.assertIn("bar", srv)

        foo = srv["foo"]
        bar = srv["bar"]

        self.assertEquals("foo.domain", foo.hostname)
        self.assertEquals("/backup/homes", foo.archive_root)

        self.assertEquals("bar", bar.hostname, "Should default to name")
        self.assertEquals("/data/homes", bar.root)

        self.assertIs(foo.commands, ubuntu)
        self.assertIsNot(bar.commands, ubuntu)

        cmds = self.cfg["commands"]
        self.assertIn("ubuntu", cmds)
        self.assertIn("custom", cmds)

