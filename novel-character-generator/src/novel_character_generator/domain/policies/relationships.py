from __future__ import annotations

RELATION_TYPE_ALIASES = {
    "father": "father",
    "父亲": "father",
    "爸爸": "father",
    "父子": "father",
    "mother": "mother",
    "母亲": "mother",
    "妈妈": "mother",
    "母子": "mother",
    "parent": "parent",
    "父母": "parent",
    "son": "son",
    "儿子": "son",
    "daughter": "daughter",
    "女儿": "daughter",
    "child": "child",
    "孩子": "child",
    "spouse": "spouse",
    "配偶": "spouse",
    "husband": "husband",
    "丈夫": "husband",
    "wife": "wife",
    "妻子": "wife",
    "妻": "wife",
    "brother": "brother",
    "兄弟": "brother",
    "sister": "sister",
    "姐妹": "sister",
}

FAMILY_FIELD_RELATIONS = {
    "family.father": "father",
    "family.mother": "mother",
    "family.parent": "parent",
    "family.son": "son",
    "family.daughter": "daughter",
    "family.child": "child",
    "family.spouse": "spouse",
    "family.husband": "husband",
    "family.wife": "wife",
    "family.brother": "brother",
    "family.sister": "sister",
}

RELATION_LABELS = {
    "father": "父亲",
    "mother": "母亲",
    "parent": "父母",
    "son": "儿子",
    "daughter": "女儿",
    "child": "孩子",
    "spouse": "配偶",
    "husband": "丈夫",
    "wife": "妻子",
    "brother": "兄弟",
    "sister": "姐妹",
}


def canonical_relation_type(value: str) -> str:
    normalized = value.strip().casefold().replace("_", " ")
    return RELATION_TYPE_ALIASES.get(normalized, normalized.replace(" ", "_"))


def relation_type_for_family_field(field_path: str) -> str | None:
    return FAMILY_FIELD_RELATIONS.get(field_path.strip().casefold())


def kinship_placeholder_names(source_name: str, relation_type: str) -> tuple[str, ...]:
    label = RELATION_LABELS.get(canonical_relation_type(relation_type))
    source = source_name.strip()
    if not source or not label:
        return ()
    return (f"{source}{label}", f"{source}的{label}")


def is_kinship_placeholder_name(value: str) -> bool:
    name = value.strip()
    return any(
        len(name) > len(label) and name.endswith(label)
        for label in RELATION_LABELS.values()
    )
