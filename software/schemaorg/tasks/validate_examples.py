"""Floating task that validates JSON-LD examples against generated SHACL shapes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import json
import logging
from typing import Any, NamedTuple, Protocol
import warnings

import owlrl  # type: ignore[import-untyped]
from pyshacl.errors import (  # type: ignore[import-untyped]
    ShapeRecursionWarning,
    ValidationFailure,
)
from pyshacl.graph_abstraction import DataGraph  # type: ignore[import-untyped]
from pyshacl.monkey import (  # type: ignore[import-untyped]
    rdflib_bool_patch,
    rdflib_bool_unpatch,
)
from pyshacl.shapes_graph import ShapesGraph  # type: ignore[import-untyped]
from pyshacl.validator import Validator  # type: ignore[import-untyped]
import rdflib
from rdflib.namespace import RDF, RDFS, SH

from schemaorg.executor import TaskExecutor
from schemaorg.layout import Releases
from schemaorg.progress import ProgressReporter
from schemaorg.version import VersionItem

_SDO_CONTEXT_URLS: frozenset[str] = frozenset({
    "https://schema.org",
    "http://schema.org",
})


def _inline_local_context(obj: Any, local_ctx: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "@context":
                if isinstance(v, str) and v.rstrip("/") in _SDO_CONTEXT_URLS:
                    out[k] = local_ctx
                elif isinstance(v, list):
                    out[k] = [
                        local_ctx
                        if isinstance(x, str)
                        and x.rstrip("/") in _SDO_CONTEXT_URLS
                        else x
                        for x in v
                    ]
                else:
                    out[k] = v
            else:
                out[k] = _inline_local_context(v, local_ctx)
        return out
    if isinstance(obj, list):
        return [_inline_local_context(x, local_ctx) for x in obj]
    return obj


class ValidatableExample(Protocol):
    """Structural interface needed to validate one JSON-LD example."""

    def getKey(self) -> str: ...

    def getJsonldRaw(self) -> str: ...


class ShaclConfigError(ValueError):
    """Raised when SHACL inputs or gates are missing or degenerate."""


class ExampleResult(NamedTuple):
    """Outcome of validating one example."""

    example: ValidatableExample
    targeted: bool
    conforms: bool
    report: str | None
    error: str | None

    @property
    def name(self) -> str:
        return self.example.getKey()


@dataclass(frozen=True)
class ValidationSummary:
    """Structured result returned by ValidateExamplesTask."""

    total_count: int
    targeted_count: int
    error_count: int
    failures: tuple[ExampleResult, ...]


class ExampleValidator:
    """Validates examples against one pre-indexed set of SHACL shapes."""

    def __init__(
        self,
        shacl_graph: rdflib.Graph,
        ont_graph: rdflib.Graph,
        local_context: Any | None,
    ) -> None:
        self.shacl_graph: rdflib.Graph = shacl_graph
        self.ont_graph: rdflib.Graph = ont_graph
        self.local_context: Any | None = local_context
        self._empty_graph: rdflib.Graph = rdflib.Graph()

        # Closed once so validate() expands rdf:type superclasses via dict lookup.
        owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(self.ont_graph)

        self.target_classes: frozenset[str] = frozenset(
            str(t) for t in self.shacl_graph.objects(None, SH.targetClass)
        )
        if not self.target_classes:
            raise ValueError(
                "the shapes declare no sh:targetClass, so they can never "
                "select a focus node. Regenerate the shapes."
            )

        supers: dict[rdflib.term.Node, set[rdflib.term.Node]] = {}
        for sub, sup in self.ont_graph.subject_objects(RDFS.subClassOf):
            if sub != sup:
                supers.setdefault(sub, set()).add(sup)
        self._superclasses: dict[
            rdflib.term.Node, tuple[rdflib.term.Node, ...]
        ] = {k: tuple(v) for k, v in supers.items()}

        by_class: dict[rdflib.term.Node, list[rdflib.term.Node]] = {}
        for shape_node, cls_node in self.shacl_graph.subject_objects(
            SH.targetClass
        ):
            by_class.setdefault(cls_node, []).append(shape_node)
        self._shapes_by_class: dict[
            rdflib.term.Node, tuple[rdflib.term.Node, ...]
        ] = {k: tuple(v) for k, v in by_class.items()}

        rdflib_bool_patch()
        try:
            self._compiled_shapes: ShapesGraph = ShapesGraph(self.shacl_graph)
            _ = self._compiled_shapes.shapes
        finally:
            rdflib_bool_unpatch()

        self._unconditional_shapes: tuple[rdflib.term.Node, ...] = tuple(
            s.node
            for s in self._compiled_shapes.shapes
            if isinstance(s.node, rdflib.URIRef)
            and not list(self.shacl_graph.objects(s.node, SH.targetClass))
        )

    def validate(self, example: ValidatableExample) -> ExampleResult:
        """Validate one example's JSON-LD against the shapes without raising."""
        try:
            raw_jsonld = example.getJsonldRaw()
            if self.local_context is not None:
                parsed_json = json.loads(raw_jsonld)
                raw_jsonld = json.dumps(
                    _inline_local_context(parsed_json, self.local_context)
                )

            ds = rdflib.Dataset()
            data_graph = ds.default_graph
            data_graph.parse(data=raw_jsonld, format="json-ld")

            declared_types = {
                str(t) for t in data_graph.objects(None, RDF.type)
            }
            targeted = bool(declared_types & self.target_classes)

            # Materialize superclasses only for types present in this example.
            for subj, typ in list(data_graph.subject_objects(RDF.type)):
                for sup in self._superclasses.get(typ, ()):
                    data_graph.add((subj, RDF.type, sup))

            present_types = set(data_graph.objects(None, RDF.type))
            used_shapes = list(
                dict.fromkeys([
                    *self._unconditional_shapes,
                    *(
                        sh
                        for typ in present_types
                        for sh in self._shapes_by_class.get(typ, ())
                    ),
                ])
            )
            if not used_shapes:
                return ExampleResult(
                    example=example,
                    targeted=targeted,
                    conforms=True,
                    report=None,
                    error=None,
                )

            validator = Validator(
                DataGraph.from_rdflib(ds),
                shacl_graph=self._empty_graph,
                options={
                    "inference": "none",
                    "inplace": True,
                    "abort_on_first": False,
                    "max_validation_depth": 200,
                    "use_shapes": used_shapes,
                },
            )
            validator.shacl_graph = self._compiled_shapes
            try:
                conforms, _, report = validator.run()
            except ValidationFailure as failure:
                conforms = False
                report = failure.message

            return ExampleResult(
                example=example,
                targeted=targeted,
                conforms=bool(conforms),
                report=None if conforms else str(report),
                error=None,
            )
        except Exception as exception:  # noqa: BLE001 - reported, not swallowed
            return ExampleResult(
                example=example,
                targeted=False,
                conforms=False,
                report=None,
                error=str(exception),
            )


def format_numbered_source(raw_jsonld: str) -> str:
    return "\n".join(
        f"{i:4d}: {line.rstrip()}"
        for i, line in enumerate(raw_jsonld.splitlines(), start=1)
    )


class ValidateExamplesTask:
    """Validates JSON-LD examples against release SHACL shapes via TaskExecutor."""

    def __init__(
        self,
        releases: Releases,
        version: VersionItem,
        examples: Sequence[ValidatableExample],
        invalid_only: bool,
        source_output: bool,
        progress: ProgressReporter,
        executor: TaskExecutor,
    ) -> None:
        self.releases: Releases = releases
        self.version: VersionItem = version
        self.examples: Sequence[ValidatableExample] = examples
        self.invalid_only: bool = invalid_only
        self.source_output: bool = source_output
        self.progress: ProgressReporter = progress
        self.executor: TaskExecutor = executor

    def run(self) -> ValidationSummary:
        if not self.examples:
            raise ShaclConfigError("No JSON-LD examples found to validate.")

        shacl_file = self.releases.file(
            self.version, protocol="", scope="shapes", extension=".shacl"
        )
        subclass_file = self.releases.file(
            self.version, protocol="", scope="subclasses", extension=".shacl"
        )
        if not shacl_file.is_file() or not subclass_file.is_file():
            raise ShaclConfigError(
                f"SHACL files not found at {shacl_file} or {subclass_file} – check site build"
            )

        local_ctx: Any | None = None
        ctx_file = self.releases.file(
            self.version, filename="schemaorgcontext.jsonld"
        )
        if ctx_file.is_file():
            local_ctx = json.loads(ctx_file.read_text(encoding="utf-8")).get(
                "@context"
            )

        with self.progress.task(
            f"Validating {len(self.examples)} JSON-LD examples",
            total=len(self.examples),
            unit="examples",
        ) as p:
            p.step("loading SHACL shapes")
            shacl_graph = rdflib.Graph()
            shacl_graph.parse(shacl_file, format="turtle")

            ont_graph = rdflib.Graph()
            ont_graph.parse(subclass_file, format="turtle")

            try:
                engine = ExampleValidator(
                    shacl_graph=shacl_graph,
                    ont_graph=ont_graph,
                    local_context=local_ctx,
                )
            except ValueError as exc:
                raise ShaclConfigError(f"SHACL gate is dead: {exc}") from exc

            def _validate_idx(
                idx: int,
            ) -> tuple[int, bool, bool, str | None, str | None]:
                res = engine.validate(self.examples[idx])
                return (
                    idx,
                    res.targeted,
                    res.conforms,
                    res.report,
                    res.error,
                )

            targeted_count = 0
            failures: list[ExampleResult] = []

            # Schema.org shapes are intentionally cyclic (e.g. Organization -> parentOrganization).
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=ShapeRecursionWarning)
                for idx, targeted, conforms, report, error in self.executor.map(
                    _validate_idx, range(len(self.examples))
                ):
                    result = ExampleResult(
                        example=self.examples[idx],
                        targeted=targeted,
                        conforms=conforms,
                        report=report,
                        error=error,
                    )
                    if not self.invalid_only:
                        p.step(result.name)
                    if result.targeted:
                        targeted_count += 1

                    failed = result.error is not None or not result.conforms
                    if result.error is not None:
                        failures.append(result)
                        p.log(
                            f"Invalid JSON example {result.name}: {result.error}",
                            logging.ERROR,
                        )
                    elif not result.conforms:
                        failures.append(result)
                        p.log(
                            f"Validation failed for example {result.name}:\n{result.report}",
                            logging.ERROR,
                        )
                    if self.source_output and failed:
                        p.log(
                            f"Source:\n{format_numbered_source(result.example.getJsonldRaw())}",
                            logging.INFO,
                        )
                    p.advance(1)

        if not targeted_count:
            raise ShaclConfigError(
                f"SHACL gate inspected none of the {len(self.examples)} examples: "
                "no example declares a type that any shape targets."
            )

        return ValidationSummary(
            total_count=len(self.examples),
            targeted_count=targeted_count,
            error_count=len(failures),
            failures=tuple(failures),
        )
