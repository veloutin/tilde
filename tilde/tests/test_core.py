from __future__ import unicode_literals
import unittest

import tempfile
import shutil
import os, pwd, grp
import sys

from .mock import MockPwd, MockGrp, MockOS

from tilde import core
from tilde.models import Home


mpwd = MockPwd([
    ("root", 0),
    ("john", 1500),
    ("jane", 1501),
    ("jack", 1502),
    ("jill", 1503),
    ("tilde", os.getuid()),
])

mgrp = MockGrp([
    ("root", 0),
    ("tilde", os.getgid()),
    ("employees", 2000),
    ("others", 2001),
])


CUR_SRV = "server1"
OTH_SRC = "other"
class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.mos = MockOS()
        core.__dict__.update({
            'os':self.mos,
            'grp':mgrp,
            'pwd':mpwd,
        })
        self.root = tempfile.mkdtemp(prefix='unittest')
        self.archive = tempfile.mkdtemp(prefix='unittest')
        self.share = core.ShareUpdater(
            CUR_SRV,
            self.root,
            self.archive,
        )

    def test_creation_update_archival(self):
        real_path = os.path.join(self.root, "home/data/badger")

        home = Home()
        home.path = "/home/data/badger"
        home.owner = "jack"
        home.group = "employees"

        self.assertFalse(os.path.exists(real_path))

        # Request creation on this server
        home.server_name = CUR_SRV
        self.share.update(home)

        self.assertTrue(os.path.exists(real_path))
        self.assertEquals(home.cur_server_name, CUR_SRV)
        self.assertEquals(home.cur_path, "/home/data/badger")
        self.assertEquals(self.mos.owns[real_path], (1502, 2000))


        # Request moving and changing owner
        new_path = os.path.join(self.root, "home/data/snake")
        arch_path = os.path.join(self.archive, "home/data/snake")
        home.path = "/home/data/snake"
        home.owner = "jill"
        self.share.update(home)

        self.assertFalse(os.path.exists(real_path))
        self.assertTrue(os.path.exists(new_path))
        self.assertEquals(self.mos.owns[new_path], (1503, 2000))

        # Request archival
        home.server_name = None
        self.share.update(home)

        self.assertFalse(os.path.exists(new_path))
        self.assertTrue(os.path.exists(arch_path))
        self.assertEquals(home.cur_server_name, None)
        self.assertEquals(home.cur_path, None)


    def tearDown(self):
        shutil.rmtree(self.root)
        shutil.rmtree(self.archive)
        core.__dict__.update({
            'os':os,
            'pwd':pwd,
            'grp':grp,
        })
