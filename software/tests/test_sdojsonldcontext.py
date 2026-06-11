#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import sys
import unittest
import unittest.mock

import software

from software.data_model.models import SdoTerm, SdoType, SdoProperty, SdoDataType, SdoEnumeration, SdoEnumerationvalue, SdoReference
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
        mock_id = "thang"
        mock_property = SdoProperty(
            id=mock_id, uri="http://schema.org/thang", label="thang", termType=SdoTermType.PROPERTY
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
        self.assertEqual(
            context[mock_id], {"@id": "http://schema.org/thang", "@type": "Date"}
        )

    @unittest.mock.patch("software.data_model.registry.TermRegistry.get_all_terms")
    def test_createcontextOneDataType(self, mock_getAllTerms):
        self.maxDiff = None
        mock_id = "Fnubl"
        mock_type = SdoDataType(
            id=mock_id, uri="http://schema.org/Fnubl", label="fnubl", termType=SdoTermType.DATATYPE
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
        mock_id = "Grabl"
        mock_enumeration = SdoEnumeration(
            id=mock_id, uri="http://schema.org/Grabl", label="grabl", termType=SdoTermType.ENUMERATION
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
        mock_id = "Bobl"
        mock_enumeration = SdoEnumerationvalue(
            id=mock_id, uri="http://schema.org/Bobl", label="bobl", termType=SdoTermType.ENUMERATIONVALUE
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
        mock_id = "Bobl"
        mock_reference = SdoReference(
            id=mock_id, uri="http://schema.org/Bobl", label="bobl", termType=SdoTermType.REFERENCE
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
                "a": {"@id": "http://schema.org/a", "@type": ["@id", "Date"]},
                "b": {"@id": "http://schema.org/b"},
                "c": {"@id": "http://schema.org/c"},
            },
        )


if __name__ == "__main__":
    unittest.main()
