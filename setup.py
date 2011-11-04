#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Distutils setup script for tilde """

import os
import re

from distutils.core import setup
data_files_list = []

packages=[]
package_dirs={}
package_data={}

def add_files(target, root, ignore=None):
    ignore = ignore or re.compile("(^|/)(\.svn|RCS|CVS|\.hg|\.bzr|_darcs|\.git)(/|$)")
    for dirpath, dirnames, filenames in os.walk(root):
        ret = []
        reltarget = os.path.join(target, dirpath[len(root)+1:])
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if not ignore.search(os.path.join(reltarget, filename)):
                ret.append(filepath)
        if len(ret) > 0:
            data_files_list.append(
                (reltarget, ret )
            )

#Add all templates
add_files("/usr/share/tilde", "share")

# obtain name and version from the debian changelog
dch_data = open("debian/changelog").readline().split()
dch_name = dch_data[0]
dch_version = dch_data[1][1:-1]


setup(#cmdclass={'build_py': CompileI18nBuildWrapper},
    name=dch_name,
    version=dch_version,
    description="tilde home management system",
    author="Vincent Vinet",
    author_email="vvinet@revolutionlinux.com",
    url="http://www.revolutionlinux.com/",
    license="GPLv3",
    platforms=["Linux"],
    long_description="""Tilde home management system""",
    packages=['tilde'],
    scripts=["bin/tilded"],
    data_files = data_files_list,
    )
