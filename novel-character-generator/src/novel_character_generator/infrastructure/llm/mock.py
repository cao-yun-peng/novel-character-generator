import re
from collections import defaultdict

from novel_character_generator.application.ports.entity_resolution import (
    ENTITY_RESOLUTION_SCHEMA_VERSION,
    EntityConvergenceDecision,
    EntityConvergenceInput,
    EntityConvergenceResult,
    EntityMentionDecision,
    EntityResolutionInput,
    EntityResolutionResult,
)
from novel_character_generator.application.ports.extraction import (
    VisualCandidateExtractionResult,
    VisualEntityCandidate,
    VisualFactCandidate,
)
from novel_character_generator.domain.policies.visual_fields import EXTRACTION_SCHEMA_VERSION

NAME_CONTEXT = re.compile(
    r"(?:少年|少女|将军|姑娘|公子)?([一-鿿]{2,4})(?="
    r"披着|约莫|换下|已是|看见|望向|认出|走进|仍私下)"
)
FEATURE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("hair.color", "黑发"),
    ("hair.change", "几缕银白"),
    ("face.distinctive_mark", "左眼下有一颗浅痣"),
    ("face.injury", "右眉留下旧伤"),
    ("clothing.outerwear", "旧青氅"),
    ("clothing.style", "深色轻甲"),
    ("clothing.color", "白衣"),
    ("clothing.outerwear", "朱红斗篷"),
    ("accessory.waist", "白玉铃"),
)


class MockExtractionProvider:
    """Deterministic v3 producer used by local development and integration tests."""

    version = f"mock:{EXTRACTION_SCHEMA_VERSION}"

    async def extract_chunk(self, text: str) -> VisualCandidateExtractionResult:
        return self.extract_visual_candidates(text)

    def extract_visual_candidates(self, text: str) -> VisualCandidateExtractionResult:
        names = self._names(text)
        entity_ids = {name: f"entity_{index}" for index, name in enumerate(names, start=1)}
        entities = [
            VisualEntityCandidate(
                local_id=entity_ids[name],
                representative_name=name,
                mention_quote=name,
                mention_kind="name",
                confidence=1.0,
            )
            for name in names
        ]
        facts: list[VisualFactCandidate] = []
        for field_path, phrase in FEATURE_PATTERNS:
            position = text.find(phrase)
            if position < 0:
                continue
            owner = self._nearest_name(text, names, position)
            if owner is None:
                continue
            facts.append(
                VisualFactCandidate(
                    entity_ref=entity_ids[owner],
                    field_path=field_path,
                    value=phrase,
                    evidence_quote=phrase,
                    epistemic_status="asserted",
                    confidence=1.0,
                )
            )
        return VisualCandidateExtractionResult(
            entities=entities,
            visual_candidates=facts,
        )

    def _names(self, text: str) -> list[str]:
        found = {match.group(1) for match in NAME_CONTEXT.finditer(text)}
        return sorted(found, key=lambda name: text.find(name))

    def _nearest_name(self, text: str, names: list[str], position: int) -> str | None:
        candidates = [(text.rfind(name, 0, position + 1), name) for name in names]
        valid = [candidate for candidate in candidates if candidate[0] >= 0]
        return max(valid)[1] if valid else None


class MockEntityResolutionProvider:
    """Deterministic local stand-in for the two structured model calls.

    Its heuristics are test fixtures only. Production identity decisions always go
    through the configured remote provider and the same validation/materialization
    gates.
    """

    version = f"mock:{ENTITY_RESOLUTION_SCHEMA_VERSION}"

    async def resolve_chunk(self, request: EntityResolutionInput) -> EntityResolutionResult:
        decisions: list[EntityMentionDecision] = []
        for mention in request.candidates.mentions:
            if mention.mention_kind != "name":
                decisions.append(
                    EntityMentionDecision(
                        mention_id=mention.mention_id,
                        action="unresolved",
                        evidence_quotes=[mention.mention_text],
                        confidence=1.0,
                        rationale="mock keeps non-name mentions local and unresolved",
                    )
                )
                continue
            exact = next(
                (
                    item
                    for item in reversed(request.cumulative_memory)
                    if mention.representative_name in item.names
                    and item.status in {"stable", "provisional"}
                ),
                None,
            )
            if exact is None:
                decisions.append(
                    EntityMentionDecision(
                        mention_id=mention.mention_id,
                        action="create_candidate",
                        evidence_quotes=[mention.mention_text],
                        confidence=1.0,
                        rationale="mock creates one provisional identity for a new named mention",
                    )
                )
            else:
                decisions.append(
                    EntityMentionDecision(
                        mention_id=mention.mention_id,
                        action="link_existing",
                        target_memory_id=exact.memory_id,
                        evidence_quotes=[mention.mention_text],
                        confidence=1.0,
                        rationale="mock links an exact repeated representative name",
                    )
                )
        return EntityResolutionResult(decisions=decisions)

    async def converge_batch(
        self, request: EntityConvergenceInput
    ) -> EntityConvergenceResult:
        groups: dict[str, list[str]] = defaultdict(list)
        records = {item.memory_id: item for item in request.provisional_memory}
        for record in request.provisional_memory:
            groups[record.memory_id].extend(record.mention_ids)
        decisions: list[EntityConvergenceDecision] = []
        for memory_id, mention_ids in groups.items():
            record = records[memory_id]
            if record.character_id is not None:
                decisions.append(
                    EntityConvergenceDecision(
                        mention_ids=sorted(set(mention_ids)),
                        action="confirm_link",
                        target_character_id=record.character_id,
                        evidence_quotes=record.evidence_quotes[:1] or record.names[:1],
                        confidence=1.0,
                        rationale="mock confirms a link to an already materialized character",
                    )
                )
            elif record.status == "provisional" and record.names:
                decisions.append(
                    EntityConvergenceDecision(
                        mention_ids=sorted(set(mention_ids)),
                        action="create_character",
                        canonical_name=record.names[-1],
                        creation_key=memory_id,
                        evidence_quotes=record.evidence_quotes[:1] or record.names[:1],
                        confidence=1.0,
                        rationale="mock promotes one provisional memory group",
                    )
                )
            else:
                decisions.append(
                    EntityConvergenceDecision(
                        mention_ids=sorted(set(mention_ids)),
                        action="keep_unresolved",
                        evidence_quotes=record.evidence_quotes[:1] or ["unresolved"],
                        confidence=1.0,
                        rationale="mock preserves unresolved identity without materialization",
                    )
                )
        return EntityConvergenceResult(decisions=decisions)
