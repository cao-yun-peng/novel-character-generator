import re
from typing import Literal

from novel_character_generator.application.ports.extraction import (
    AliasDraft,
    ChunkExtractionResult,
    ExpressionDraft,
    MentionDraft,
    ObservationDraft,
)

NAME_CONTEXT = re.compile(
    r"(?:少年|少女|将军|姑娘|公子)?([一-鿿]{2,4})(?="
    r"披着|约莫|换下|已是|看见|望向|认出|走进|仍私下)"
)
ALIAS_PATTERN = re.compile(r'称(?:他|她|其)?(?:为)?[“"]([^”"]{2,8})[”"]')
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
Emotion = Literal[
    "joy", "sadness", "anger", "fear", "surprise", "disgust", "calm", "mixed", "unknown"
]

EXPRESSION_PATTERNS: tuple[tuple[str, Emotion, list[str]], ...] = (
    ("嘴角微扬", "joy", ["嘴角微扬"]),
    ("神色平静", "calm", ["神色平静"]),
    ("握剑的手却微微发紧", "fear", ["握剑的手发紧"]),
    ("先是惊讶", "surprise", ["惊讶"]),
    ("克制的笑", "joy", ["克制的笑"]),
)


class MockExtractionProvider:
    version = "mock-extraction-v1"

    async def extract_chunk(self, text: str) -> ChunkExtractionResult:
        names = self._names(text)
        mentions = self._mentions(text, names)
        aliases = self._aliases(text, names)
        observations = [
            observation
            for field_path, phrase in FEATURE_PATTERNS
            if (observation := self._observation(text, names, field_path, phrase)) is not None
        ]
        expressions = [
            expression
            for phrase, emotion, cues in EXPRESSION_PATTERNS
            if (expression := self._expression(text, names, phrase, emotion, cues)) is not None
        ]
        return ChunkExtractionResult(
            mentions=mentions,
            alias_hypotheses=aliases,
            observations=observations,
            expression_observations=expressions,
        )

    def _names(self, text: str) -> list[str]:
        found = {match.group(1) for match in NAME_CONTEXT.finditer(text)}
        return sorted(found, key=lambda name: text.find(name))

    def _mentions(self, text: str, names: list[str]) -> list[MentionDraft]:
        mentions: list[MentionDraft] = []
        for name in names:
            for match in re.finditer(re.escape(name), text):
                mentions.append(
                    MentionDraft(
                        text=name,
                        canonical_name=name,
                        start=match.start(),
                        end=match.end(),
                        kind="name",
                    )
                )
        return sorted(mentions, key=lambda mention: mention.start)

    def _aliases(self, text: str, names: list[str]) -> list[AliasDraft]:
        aliases: list[AliasDraft] = []
        for match in ALIAS_PATTERN.finditer(text):
            owner = self._nearest_name(text, names, match.start())
            aliases.append(
                AliasDraft(
                    alias_text=match.group(1),
                    canonical_name=owner,
                    mention_start=match.start(1),
                    mention_end=match.end(1),
                    alias_kind="title" if "将军" in match.group(1) else "nickname",
                )
            )
        return aliases

    def _observation(
        self, text: str, names: list[str], field_path: str, phrase: str
    ) -> ObservationDraft | None:
        start = text.find(phrase)
        if start < 0:
            return None
        owner = self._nearest_name(text, names, start)
        if owner is None:
            return None
        return ObservationDraft(
            character_name=owner,
            field_path=field_path,
            value=phrase,
            evidence_quote=phrase,
            start=start,
            end=start + len(phrase),
            confidence=1.0,
        )

    def _expression(
        self, text: str, names: list[str], phrase: str, emotion: Emotion, cues: list[str]
    ) -> ExpressionDraft | None:
        start = text.find(phrase)
        if start < 0:
            return None
        owner = self._nearest_name(text, names, start)
        if owner is None:
            return None
        return ExpressionDraft(
            character_name=owner,
            outward_emotion=emotion,
            expression_text=phrase,
            visible_cues=cues,
            start=start,
            end=start + len(phrase),
            confidence=1.0,
        )

    def _nearest_name(self, text: str, names: list[str], position: int) -> str | None:
        candidates = [(text.rfind(name, 0, position + 1), name) for name in names]
        valid = [candidate for candidate in candidates if candidate[0] >= 0]
        return max(valid)[1] if valid else None
