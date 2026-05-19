#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Any, List, Optional, Iterable, Union, Dict, Type

class UnexpandedTermError(LookupError):
    """Exception raised when accessing terms in a sequence that hasn't been expanded."""
    pass

class CompatibilityList(list):
    """A list wrapper that provides .ids and .terms for backward compatibility with SdoTermSequence."""
    def __init__(self, elements=None, term_id=None, term=None):
        if elements:
            super().__init__(elements)
        elif term:
            super().__init__([term])
        elif term_id:
            super().__init__([term_id])
        else:
            super().__init__()

    @property
    def id(self) -> Optional[str]:
        if not self:
            return None
        t = self[0]
        return getattr(t, "id", str(t))

    @property
    def term(self) -> Any:
        if not self:
            raise UnexpandedTermError("Empty sequence has no term.")
        t = self[0]
        if isinstance(t, str):
            from .bridge import SdoTermSource
            res = SdoTermSource.getTerm(t)
            if not res:
                raise UnexpandedTermError(f"Term {t} not found.")
            return res
        return t

    @property
    def ids(self) -> List[str]:
        return [getattr(t, "id", str(t)) for t in self]
    
    @property
    def terms(self) -> List[Any]:
        if not self.expanded and any(isinstance(t, str) for t in self):
            raise UnexpandedTermError("Accessing terms of an unexpanded sequence.")
        return [t for t in self if not isinstance(t, str)]

    @property
    def expanded(self) -> bool:
        if not self:
            return True
        return all(not isinstance(t, str) for t in self)

    def setIds(self, ids: Iterable[str]) -> None:
        self.clear()
        for i in ids:
            self.append(i)

    def setTerms(self, terms: Iterable[SdoTerm]) -> None:
        self.clear()
        for t in terms:
            self.append(t)

    def clear(self) -> None:
        super().clear()

    @classmethod
    def forElements(cls, elements: Iterable[Any]) -> CompatibilityList:
        return cls(elements)

class LegacySdoTermAdapter:
    """Wraps an SdoTerm to provide legacy properties and recursive wrapping."""
    
    def __init__(self, term: SdoTerm):
        from .models import SdoTerm as _SdoTerm
        if not isinstance(term, _SdoTerm):
             raise TypeError(f"Expected SdoTerm, got {type(term)}")
        self._term = term

    def __getattr__(self, name):
        return getattr(self._term, name)

    def __hash__(self):
        return hash(self._term.uri)

    def __eq__(self, other):
        if isinstance(other, LegacySdoTermAdapter):
            return self._term.uri == other._term.uri
        from .models import SdoTerm as _SdoTerm
        if isinstance(other, _SdoTerm):
            return self._term.uri == other.uri
        return False

    def _wrap(self, obj):
        from .models import SdoTerm as _SdoTerm
        if isinstance(obj, _SdoTerm):
            return wrap_term(obj)
        if isinstance(obj, (list, CompatibilityList)):
            return CompatibilityList([self._wrap(i) for i in obj])
        return obj

    @property
    def id(self) -> str:
        return self._term.id

    @property
    def uri(self) -> URIRef:
        return self._term.uri

    @property
    def label(self) -> str:
        return self._term.label

    @property
    def comment(self) -> str:
        return self._term.comment

    @property
    def layer(self) -> str:
        return self._term.layer

    @property
    def termType(self) -> Any:
        return self._term.termType

    @property
    def superseded(self) -> bool:
        return bool(self._term.superseded_by_uri)

    @property
    def supersededBy(self) -> str:
        return str(self._term.superseded_by_uri).split("/")[-1] if self._term.superseded_by_uri else ""

    @property
    def supersedes(self) -> List[str]:
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        return sorted([
            t.id for t in registry.all_terms().values() 
            if t.superseded_by_uri == self._term.uri
        ])

    @property
    def sources(self) -> List[str]:
        return [str(u) for u in self._term.source_uris]

    @property
    def extLayer(self) -> str:
        return self._term.layer if self._term.layer and self._term.layer != "core" else ""

    @property
    def equivalents(self) -> CompatibilityList:
        from .registry import TermRegistry
        from .models import SdoProperty as _SdoProperty
        registry = TermRegistry.get_instance()
        eqs = [
            t for u in self._term.equivalent_uris 
            if (t := registry.get(u))
        ]
        if isinstance(self._term, _SdoProperty):
            for u in self._term.equivalent_property_uris:
                if (t := registry.get(u)):
                    eqs.append(t)
        return self._wrap(sorted(list(set(eqs)), key=lambda x: x.id))

    @property
    def acknowledgements(self) -> List[Any]:
        import SchemaTerms.sdocollaborators as sdocollaborators
        acks = []
        for uri in self._term.contributor_uris:
            cont = sdocollaborators.collaborator.getContributor(str(uri))
            if cont:
                acks.append(cont)
        return sorted(acks, key=lambda t: t.title or "")

    @property
    def supers(self) -> CompatibilityList:
        if not hasattr(self._term, "super_uris"):
            return CompatibilityList()
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        res = [
            t for u in self._term.super_uris 
            if (t := registry.get(u)) and isinstance(t, type(self._term))
        ]
        return self._wrap(sorted(res, key=lambda x: x.id))

    @property
    def subs(self) -> CompatibilityList:
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        res = [
            t for t in registry.all_terms().values()
            if isinstance(t, type(self._term)) and self._term.uri in getattr(t, "super_uris", [])
        ]
        return self._wrap(sorted(res, key=lambda x: x.id))

    @property
    def termStack(self) -> CompatibilityList:
        stack = []
        for sup in self.supers:
            if sup not in stack:
                stack.append(sup)
                for ancestor in sup.termStack:
                    if ancestor not in stack:
                        stack.append(ancestor)
        return CompatibilityList(stack)

    @property
    def superPaths(self) -> List[List[Any]]:
        if self.id == "Thing":
            return [[self]]
        
        from .models import SdoEnumerationvalue as _SdoEnumerationvalue
        if isinstance(self._term, _SdoEnumerationvalue):
            paths = []
            parent = self.enumerationParent
            if parent:
                for path in parent.superPaths:
                    paths.append(path + [self])
            return paths

        if not self.supers:
            return [[self]]
            
        paths = []
        for parent in self.supers:
            for path in parent.superPaths:
                paths.append(path + [self])
        return paths

    @property
    def properties(self) -> CompatibilityList:
        from .models import SdoType as _SdoType, SdoProperty as _SdoProperty
        if not isinstance(self._term, _SdoType):
            return CompatibilityList()
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        terms = [t for t in registry.all_terms().values() if isinstance(t, _SdoProperty) and self._term.uri in t.domain_uris]
        return self._wrap(sorted(terms, key=lambda x: x.id))

    @property
    def allproperties(self) -> CompatibilityList:
        from .models import SdoType as _SdoType
        if not isinstance(self._term, _SdoType):
            return CompatibilityList()
        props = sorted(list(set(self.properties) | set([p for t in self.termStack for p in t.properties])), key=lambda x: x.id)
        return CompatibilityList(props)

    @property
    def expectedTypeFor(self) -> CompatibilityList:
        from .models import SdoType as _SdoType, SdoProperty as _SdoProperty
        if not isinstance(self._term, _SdoType):
            return CompatibilityList()
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        terms = [t for t in registry.all_terms().values() if isinstance(t, _SdoProperty) and self._term.uri in t.range_uris]
        return self._wrap(sorted(terms, key=lambda x: x.id))

    @property
    def domainIncludes(self) -> CompatibilityList:
        from .models import SdoProperty as _SdoProperty
        if not isinstance(self._term, _SdoProperty):
             return CompatibilityList()
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        terms = [t for u in self._term.domain_uris if (t := registry.get(u))]
        lst = self._wrap(sorted(terms, key=lambda x: x.id))
        
        def setIds(ids):
            from .bridge import SdoTermSource
            from rdflib import URIRef
            self._term.domain_uris = [URIRef(SdoTermSource.toFullId(i)) for i in ids]
        lst.setIds = setIds
        return lst

    @property
    def rangeIncludes(self) -> CompatibilityList:
        from .models import SdoProperty as _SdoProperty
        if not isinstance(self._term, _SdoProperty):
             return CompatibilityList()
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        terms = [t for u in self._term.range_uris if (t := registry.get(u))]
        lst = self._wrap(sorted(terms, key=lambda x: x.id))
        
        def setIds(ids):
            from .bridge import SdoTermSource
            from rdflib import URIRef
            self._term.range_uris = [URIRef(SdoTermSource.toFullId(i)) for i in ids]
        lst.setIds = setIds
        return lst

    @property
    def inverseOf(self) -> Optional[Any]:
        return self.inverse

    @property
    def domains(self) -> CompatibilityList:
        return self.domainIncludes

    @property
    def ranges(self) -> CompatibilityList:
        return self.rangeIncludes

    @property
    def inverse(self) -> Any:
        from .models import SdoProperty as _SdoProperty
        if not isinstance(self._term, _SdoProperty):
            return None
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        res = None
        if self._term.inverse_uri:
            res = registry.get(self._term.inverse_uri)
        if not res:
            for t in registry.all_terms().values():
                if isinstance(t, _SdoProperty) and t.inverse_uri == self._term.uri:
                    res = t
                    break
        
        if res:
            return self._wrap(res)
        
        class NullInverse:
            id = ""
            def __bool__(self): return False
        return NullInverse()

    @property
    def enumerationMembers(self) -> CompatibilityList:
        from .models import SdoEnumeration as _SdoEnumeration, SdoEnumerationvalue as _SdoEnumerationvalue
        if not isinstance(self._term, _SdoEnumeration):
            return CompatibilityList()
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        res = [
            t for t in registry.all_terms().values() 
            if isinstance(t, _SdoEnumerationvalue) and t.enumeration_uri == self._term.uri
        ]
        return self._wrap(sorted(res, key=lambda x: x.id))

    @property
    def enumerationParent(self) -> Optional[Any]:
        from .models import SdoEnumerationvalue as _SdoEnumerationvalue, SdoEnumeration as _SdoEnumeration
        if not isinstance(self._term, _SdoEnumerationvalue) or not self._term.enumeration_uri:
            return None
        from .registry import TermRegistry
        t = TermRegistry.get_instance().get(self._term.enumeration_uri)
        return self._wrap(t) if isinstance(t, _SdoEnumeration) else None

_ADAPTER_CLASS: Type[LegacySdoTermAdapter] = LegacySdoTermAdapter

def set_adapter_class(cls: Type[LegacySdoTermAdapter]):
    global _ADAPTER_CLASS
    _ADAPTER_CLASS = cls

def wrap_term(term: SdoTerm) -> LegacySdoTermAdapter:
    return _ADAPTER_CLASS(term)
