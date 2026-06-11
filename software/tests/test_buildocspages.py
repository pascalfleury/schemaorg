#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import unittest

import software

import SchemaExamples.schemaexamples as schemaexamples
from software.util.paths import DefaultInputLayout
from software.data_model.loader import GraphLoader
import util.buildocspages as buildocspages


class TestBuildDocs(unittest.TestCase):
    """Test the buildocspages package."""

    @classmethod
    def setUpClass(cls):
        layout = DefaultInputLayout()
        loader = GraphLoader.from_layout(layout)
        loader.load_all()

    def testJsonldtree(self):
        buildocspages.jsonldtree(page=None)


if __name__ == "__main__":
    unittest.main()
