#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import sys
import unittest
import unittest.mock

import software

import SchemaTerms.sdoterm as sdoterm
import SchemaTerms.sdotermsource as sdotermsource
from software.data_model.models import (
    SdoDataType,
    SdoEnumeration,
    SdoEnumerationvalue,
    SdoProperty,
    SdoReference,
    SdoTerm,
    SdoType,
)
from software.data_model.type_map import SdoTermType
import util.sdojsonldcontext as sdojsonldcontext


class SdoJsonLdContextTest(unittest.TestCase):
    """Tests for the sdojsonldcontext library."""

    @unittest.mock.patch("software.data_model.registry.TermRegistry.get_all_terms")
    def test_createcontextEmpty(self, mock_getAllTerms):
        """Test that createcontext outputs valid JSON data"""
        mock_getAllTerms.return_value = []
        json_data = sdojsonldcontext.createcontext()
        parsed = json.loads(json_data)
        self.assertIn("@context", parsed)
        context = parsed["@context"]
        self.assertIn("type", context)
        self.assertIn("id", context)
        self.assertIn("@vocab", context)

    @unittest.mock.patch("software.data_model.registry.TermRegistry.get_all_terms")
    def test_createcontextOneProperty(self, mock_getAllTerms):
        """Test that createcontext outputs valid JSON data"""
        self.maxDiff = None
        mock_id = "1234"
        mock_property = SdoProperty(
            term_id=mock_id, uri="http://schema.org/thang", label="thang"
        )
        mock_property.domainIncludes = [SdoType(id="Thing", uri="http://schema.org/Thing", label="Thing")]
        mock_property.rangeIncludes = [SdoType(id="Date", uri="http://schema.org/Date", label="Date"), SdoType(id="Thing", uri="http://schema.org/Thing", label="Thing")]
        mock_getAllTerms.return_value = [mock_property]
        json_data = sdojsonldcontext.createcontext()
        parsed = json.loads(json_data)
        self.assertIn("@context", parsed)
        context = parsed["@context"]
        self.assertIn("type", context)
        self.assertIn("id", context)
        self.assertIn("@vocab", context)

        # Historically, @type=Date (or @type=id) was included for non-Text-related properties. Since we support multiple
        # datatypes/things for properties, this led to inaccurate datatype results and inconsistent usage of
        # datatypes/IRIs for property values (post-JSON-LD processing). This test helps ensure it is not unintentionally
        # re-introduced and to document a bit more of the background.
        self.assertEqual(
            context[mock_id], {"@id": "http://schema.org/thang"}
        )

    @unittest.mock.patch("software.data_model.registry.TermRegistry.get_all_terms")
    def test_createcontextOneDataType(self, mock_getAllTerms):
        self.maxDiff = None
        mock_id = "1234"
        mock_type = SdoDataType(
            term_id=mock_id, uri="http://schema.org/Fnubl", label="fnubl"
        )
        mock_getAllTerms.return_value = [mock_type]
        json_data = sdojsonldcontext.createcontext()
        parsed = json.loads(json_data)
        self.assertIn("@context", parsed)
        context = parsed["@context"]
        self.assertIn("type", context)
        self.assertIn("id", context)
        self.assertIn("@vocab", context)
        self.assertEqual(context[mock_id], {"@id": "http://schema.org/Fnubl"})

    @unittest.mock.patch("software.data_model.registry.TermRegistry.get_all_terms")
    def test_createcontextOneEnumeration(self, mock_getAllTerms):
        self.maxDiff = None
        mock_id = "1234"
        mock_enumeration = SdoEnumeration(
            term_id=mock_id, uri="http://schema.org/Grabl", label="grabl"
        )
        mock_getAllTerms.return_value = [mock_enumeration]
        json_data = sdojsonldcontext.createcontext()
        parsed = json.loads(json_data)
        self.assertIn("@context", parsed)
        context = parsed["@context"]
        self.assertIn("type", context)
        self.assertIn("id", context)
        self.assertIn("@vocab", context)
        self.assertEqual(context[mock_id], {"@id": "http://schema.org/Grabl"})

    @unittest.mock.patch("software.data_model.registry.TermRegistry.get_all_terms")
    def test_createcontextOneEnumerationValue(self, mock_getAllTerms):
        self.maxDiff = None
        mock_id = "1234"
        mock_enumeration = SdoEnumerationvalue(
            term_id=mock_id, uri="http://schema.org/Bobl", label="bobl"
        )
        mock_getAllTerms.return_value = [mock_enumeration]
        json_data = sdojsonldcontext.createcontext()
        parsed = json.loads(json_data)
        self.assertIn("@context", parsed)
        context = parsed["@context"]
        self.assertIn("type", context)
        self.assertIn("id", context)
        self.assertIn("@vocab", context)
        self.assertEqual(context[mock_id], {"@id": "http://schema.org/Bobl"})

    @unittest.mock.patch("software.data_model.registry.TermRegistry.get_all_terms")
    def test_createcontextOneReference(self, mock_getAllTerms):
        self.maxDiff = None
        mock_id = "1234"
        mock_reference = SdoReference(
            term_id=mock_id, uri="http://schema.org/Bobl", label="bobl"
        )
        mock_getAllTerms.return_value = [mock_reference]
        json_data = sdojsonldcontext.createcontext()
        parsed = json.loads(json_data)
        self.assertIn("@context", parsed)
        context = parsed["@context"]
        self.assertIn("type", context)
        self.assertIn("id", context)
        self.assertIn("@vocab", context)
        self.assertNotIn(mock_id, context)

    @unittest.mock.patch("software.data_model.registry.TermRegistry.get_all_terms")
    def test_createcontextMultiple(self, mock_getAllTerms):
        self.maxDiff = None
        mock_property = SdoProperty(
            id="a", uri="http://schema.org/a", label="a", termType=SdoTermType.PROPERTY
        )
        mock_property.domainIncludes = [SdoType(id="Thing", uri="http://schema.org/Thing", label="Thing")]
        mock_property.rangeIncludes = [SdoType(id="Date", uri="http://schema.org/Date", label="Date"), SdoType(id="URL", uri="http://schema.org/URL", label="URL"), SdoType(id="Thing", uri="http://schema.org/Thing", label="Thing")]
        mock_enumeration = SdoEnumeration(
            id="b", uri="http://schema.org/b", label="b", termType=SdoTermType.ENUMERATION
        )
        mock_enumeration_value = SdoEnumerationvalue(
            id="c", uri="http://schema.org/c", label="c", termType=SdoTermType.ENUMERATIONVALUE
        )
        mock_getAllTerms.return_value = [
            mock_property,
            mock_enumeration,
            mock_enumeration_value,
        ]
        json_data = sdojsonldcontext.createcontext()
        parsed = json.loads(json_data)
        self.assertIn("@context", parsed)
        self.assertEqual(
            dict(
                [
                    (k, v)
                    for k, v in parsed["@context"].items()
                    if k in ["a", "b", "c"]
                ]
            ),
            {
                "a": {"@id": "http://schema.org/a"},
                "b": {"@id": "http://schema.org/b"},
                "c": {"@id": "http://schema.org/c"},
            },
        )


if __name__ == "__main__":
    unittest.main()
