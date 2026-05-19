#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
from typing import Any, Dict, FrozenSet, Type

import util.schema as schema
from software.data_model.type_map import SdoTermType

# Import new models for internal use
from software.data_model.models import (
    SdoTerm as _SdoTerm,
    SdoType as _SdoType,
    SdoProperty as _SdoProperty,
    SdoDataType as _SdoDataType,
    SdoEnumeration as _SdoEnumeration,
    SdoEnumerationvalue as _SdoEnumerationvalue,
    SdoReference as _SdoReference,
)
from software.data_model.compat import (
    CompatibilityList as CompatibilityList,
    UnexpandedTermError as UnexpandedTermError,
    LegacySdoTermAdapter as _LegacySdoTermAdapter,
    set_adapter_class,
)

log: logging.Logger = logging.getLogger(__name__)

# Re-export CompatibilityList under legacy names
SdoTermSequence = CompatibilityList
SdoTermOrId = CompatibilityList

class SdoTerm(_LegacySdoTermAdapter):
    def __init__(self, term=None, **kwargs):
        if term is None:
            term = _SdoTerm.model_validate(kwargs)
        super().__init__(term)

class SdoType(SdoTerm):
    def __init__(self, term=None, **kwargs):
        if term is None:
            term = _SdoType.model_validate(kwargs)
        super().__init__(term)

class SdoProperty(SdoTerm):
    def __init__(self, term=None, **kwargs):
        if term is None:
            term = _SdoProperty.model_validate(kwargs)
        super().__init__(term)

class SdoDataType(SdoType):
    def __init__(self, term=None, **kwargs):
        if term is None:
            term = _SdoDataType.model_validate(kwargs)
        super().__init__(term)

class SdoEnumeration(SdoType):
    def __init__(self, term=None, **kwargs):
        if term is None:
            term = _SdoEnumeration.model_validate(kwargs)
        super().__init__(term)

class SdoEnumerationvalue(SdoTerm):
    def __init__(self, term=None, **kwargs):
        if term is None:
            term = _SdoEnumerationvalue.model_validate(kwargs)
        super().__init__(term)

class SdoReference(SdoTerm):
    def __init__(self, term=None, **kwargs):
        if term is None:
            term = _SdoReference.model_validate(kwargs)
        super().__init__(term)

# Register SdoTerm as the primary adapter class
set_adapter_class(SdoTerm)

_TYPES_FOR_TYPES: Dict[SdoTermType, Type[SdoTerm]] = {
    SdoTermType.TYPE: SdoType,
    SdoTermType.DATATYPE: SdoDataType,
    SdoTermType.PROPERTY: SdoProperty,
    SdoTermType.ENUMERATION: SdoEnumeration,
    SdoTermType.ENUMERATIONVALUE: SdoEnumerationvalue,
    SdoTermType.REFERENCE: SdoReference
}

def SdoTermforType(term_type: SdoTermType, **kwargs: Any) -> SdoTerm:
    t: Type[SdoTerm] = _TYPES_FOR_TYPES[term_type]
    return t(**kwargs)
