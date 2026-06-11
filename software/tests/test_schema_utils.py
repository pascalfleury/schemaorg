#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import logging
import os
import sys
import unittest

import rdflib

import software

import util.schema as schema
from software.data_model.registry import TermRegistry


class TestConversionFunctions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from software.util.paths import DefaultInputLayout
        from software.data_model.loader import GraphLoader
        layout = DefaultInputLayout()
        loader = GraphLoader.from_layout(layout)
        loader.load_all()

    def testVocabUri(self):
        self.assertEqual(schema.VOCABURI, "https://schema.org/")

    def testToFullId(self):
        self.assertEqual(schema.toFullId("fnord"), "https://schema.org/fnord")
        self.assertEqual(
            schema.toFullId("http://schema.org/Thing"), "http://schema.org/Thing"
        )

    def testUriWrap(self):
        self.assertEqual(schema.uriWrap("fnord"), "fnord")
        self.assertEqual(
            schema.uriWrap("http://schema.org/Thing"),
            "<http://schema.org/Thing>",
        )

    def testLayerFromUri(self):
        self.assertIsNone(schema.layerFromUri(None))
        self.assertIsNone(schema.layerFromUri("https://schema.org/Thing"))
        self.assertEqual(
            schema.layerFromUri("https://exclusive.schema.org/Thing"),
            "exclusive",
        )

    def testUriFromLayer(self):
        self.assertEqual(schema.uriFromLayer(), "https://schema.org")
        self.assertEqual(
            schema.uriFromLayer("premium"), "https://premium.schema.org"
        )

    def testGetProtoAndRoot(self):
        self.assertEqual(
            schema.getProtoAndRoot(""), schema.ProtoAndRoot(None, None)
        )
        self.assertEqual(
            schema.getProtoAndRoot("http://schema.org/Thing"),
            schema.ProtoAndRoot("http://", "schema.org/Thing"),
        )

    def testUri2id(self):
        self.assertEqual(schema.uri2id(""), "")
        self.assertEqual(schema.uri2id("https://schema.org/Thing"), "Thing")
        self.assertEqual(
            schema.uri2id("http://purl.org/dc/elements/1.1/"),
            "http://purl.org/dc/elements/1.1/",
        )

    def testPrefixFromUri(self):
        self.assertIsNone(schema.prefixFromUri(""))
        self.assertEqual(
            schema.prefixFromUri("https://schema.org/Thing"), "schema"
        )
        self.assertEqual(
            schema.prefixFromUri("http://purl.org/dc/elements/1.1/"), "dc"
        )

    def testUriForPrefix(self):
        self.assertIsNone(schema.uriForPrefix(""))
        self.assertEqual(
            schema.uriForPrefix("schema"),
            rdflib.term.URIRef("https://schema.org/"),
        )
        self.assertEqual(
            schema.uriForPrefix("dc"),
            rdflib.term.URIRef("http://purl.org/dc/elements/1.1/"),
        )
        self.assertIsNone(schema.uriForPrefix("feedface"))

    def testPrefixedIdFromUri(self):
        self.assertEqual(
            schema.prefixedIdFromUri("https://schema.org/Thing"), "schema:Thing"
        )
        self.assertEqual(
            schema.prefixedIdFromUri("http://purl.org/dc/elements/1.1/title"),
            "dc:title",
        )

    def testGetComment(self):
        product_term = TermRegistry.get_instance().get_by_id("Product")
        self.assertIn("product", product_term.comment)

    def testGetAckowledgements(self):
        product_term = TermRegistry.get_instance().get_by_id("Product")
        self.assertTrue(product_term.acknowledgements)
        collaborator = product_term.acknowledgements[0]
        self.assertEqual(
            collaborator.uri, "https://schema.org/docs/collab/GoodRelationsTerms"
        )
        self.assertIn(
            "GoodRelations Vocabulary for E-Commerce", collaborator.acknowledgement
        )


if __name__ == "__main__":
    unittest.main()
