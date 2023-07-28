"""setup.py file."""

import uuid

from setuptools import setup, find_packages

__author__ = 'Johan van den Dorpe <johan@vdltech.net>'

with open("requirements.txt", "r") as fs:
    reqs = [r for r in fs.read().splitlines() if (len(r) > 0 and not r.startswith("#"))]

setup(
    name="napalm-adva",
    version="0.1.4",
    packages=find_packages(),
    author="Johan van den Dorpe",
    author_email="johan@vdltech.net",
    description="Network Automation and Programmability Abstraction Layer with Multivendor support",
    classifiers=[
        'Topic :: Utilities',
         'Programming Language :: Python',
         'Programming Language :: Python :: 3',
         'Programming Language :: Python :: 3.9',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS',
    ],
    url="https://github.com/sohonet/napalm-adva",
    include_package_data=True,
    install_requires=reqs,
)
