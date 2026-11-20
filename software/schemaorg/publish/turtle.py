"""Deterministic Turtle serialisation.

rdflib's stock Turtle serialiser orders subjects by reference count, which
is stable for a given graph but says nothing useful to a human reading a
diff. ``CustomTurtleSerializer`` emits classes first, then properties, each
lexicographically sorted, then everything else. That ordering is what makes
the hand-maintained vocabulary files reviewable: a one-term change produces
a one-term diff.
"""

from rdflib import BNode, RDF, RDFS
from rdflib.plugins.serializers.turtle import TurtleSerializer
import rdflib.term


class CustomTurtleSerializer(TurtleSerializer):
    """Turtle serialiser with a human-reviewable subject order."""

    topClasses = [RDFS.Class, RDF.Property]

    def orderSubjects(self) -> list[rdflib.term.Node]:
        seen = set()
        subjects: list[rdflib.term.Node] = []

        # Emit classes and properties first, sorted lexicographically.
        for classURI in self.topClasses:
            members = sorted(
                self.store.subjects(RDF.type, classURI)  # type: ignore[type-var]
            )
            subjects.extend(members)
            for member in members:
                self._topLevels[member] = True
                seen.add(member)

        # Emit remaining subjects sorted by (is_bnode, subject).
        recursable = sorted(
            (isinstance(subject, BNode), subject)
            for subject in self._subjects
            if subject not in seen
        )
        subjects.extend(subject for _, subject in recursable)

        return subjects
