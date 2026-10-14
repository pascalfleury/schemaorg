#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Unit tests for schemaorg.so_uri."""

import unittest

from rdflib import URIRef

from schemaorg.so_uri import SDO, SoUri


class TestSoUri(unittest.TestCase):
    def test_schema_org_uri(self) -> None:
        so = SoUri(SDO.Person)
        self.assertTrue(so.is_so())
        self.assertEqual(so.term_name(), "Person")
        self.assertEqual(so.uri, SDO.Person)
        self.assertEqual(str(so), "https://schema.org/Person")

    def test_external_uri_preserved(self) -> None:
        ext = SoUri("http://xmlns.com/foaf/0.1/Person")
        self.assertFalse(ext.is_so())
        self.assertEqual(ext.uri, URIRef("http://xmlns.com/foaf/0.1/Person"))
        self.assertEqual(str(ext), "http://xmlns.com/foaf/0.1/Person")

    def test_bare_term_name(self) -> None:
        bare = SoUri("Person")
        self.assertTrue(bare.is_so())
        self.assertEqual(bare.uri, SDO.Person)
        self.assertEqual(bare.term_name(), "Person")
        self.assertEqual(str(bare), "https://schema.org/Person")

    def test_layer_extraction(self) -> None:
        self.assertEqual(
            SoUri("https://health-lifesci.schema.org").layer(),
            "health-lifesci",
        )
        self.assertEqual(SoUri("https://pending.schema.org").layer(), "pending")
        self.assertEqual(SoUri("https://schema.org").layer(), "core")

    def test_http_schema_org_upgraded_with_warning(self) -> None:
        with self.assertLogs("schemaorg.so_uri", level="WARNING"):
            upgraded = SoUri("http://schema.org/Person")
        self.assertTrue(upgraded.is_so())
        self.assertEqual(upgraded.uri, SDO.Person)
        self.assertEqual(upgraded.term_name(), "Person")
        self.assertEqual(str(upgraded), "https://schema.org/Person")

        with self.assertLogs("schemaorg.so_uri", level="WARNING"):
            upgraded_layer = SoUri("http://pending.schema.org")
        self.assertEqual(upgraded_layer.layer(), "pending")
        self.assertEqual(str(upgraded_layer), "https://pending.schema.org")


if __name__ == "__main__":
    unittest.main()
