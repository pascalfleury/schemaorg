#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import tempfile
import unittest

import software

import util.fileutils as fileutils


class FileUtilsTest(unittest.TestCase):
    def test_checkFilePath(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fileutils.checkFilePath(tmp_dir)



if __name__ == "__main__":
    unittest.main()
