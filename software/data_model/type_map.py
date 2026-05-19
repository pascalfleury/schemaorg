#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import enum

class SdoTermType(str, enum.Enum):
    """Enumeration describing the type of an SdoTerm."""
    TYPE = "Type"
    PROPERTY = "Property"
    DATATYPE = "Datatype"
    ENUMERATION = "Enumeration"
    ENUMERATIONVALUE = "Enumerationvalue"
    REFERENCE = "Reference"

    def __str__(self) -> str:
        return self.value
