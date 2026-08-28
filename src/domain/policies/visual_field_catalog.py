from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

VISUAL_FIELD_CATALOG_VERSION: Literal["visual-field-catalog-v1"] = "visual-field-catalog-v1"
VisualFieldValueType = Literal["string"]


@dataclass(frozen=True, slots=True)
class VisualFieldCatalogEntry:
    field_path: str
    value_type: VisualFieldValueType
    description: str


def _entry(field_path: str, description: str) -> VisualFieldCatalogEntry:
    return VisualFieldCatalogEntry(
        field_path=field_path,
        value_type="string",
        description=description,
    )


# This tuple is the complete M2 v1 catalog. It contains exact leaf paths only: no wildcard
# root, alias, or novel-specific extension is accepted.
VISUAL_FIELD_CATALOG: tuple[VisualFieldCatalogEntry, ...] = (
    _entry("age", "Explicit human age, age range, or directly stated relative age."),
    _entry("age_stage", "Explicit visible life-stage label such as child or elderly."),
    _entry("skin.color", "Visible skin colour or skin tone outside face-only complexion."),
    _entry("skin.description", "Other directly visible skin surface description."),
    _entry("body.build", "Overall stature, physique, or body build."),
    _entry("body.height", "Explicit height or relative height."),
    _entry("body.hands", "Visible hand or finger form and appearance."),
    _entry("body.description", "Other directly visible body-form description."),
    _entry("hair.color", "Natural or currently visible hair colour."),
    _entry("hair.length", "Hair length."),
    _entry("hair.style", "Hair arrangement, cut, or hairstyle."),
    _entry("hair.texture", "Hair texture such as curly, straight, or coarse."),
    _entry("face.shape", "Geometric facial contour or face shape."),
    _entry("face.complexion", "Visible facial skin tone or complexion."),
    _entry("face.eye_color", "Eye or iris colour."),
    _entry("face.eyes", "Visible eye, eyelid, or gaze state; not inferred emotion."),
    _entry("face.eyebrows", "Visible eyebrow shape, colour, or density."),
    _entry("face.nose", "Visible nose shape or appearance."),
    _entry("face.mouth", "Visible mouth shape or stable mouth appearance."),
    _entry("face.lips", "Visible lip shape or colour."),
    _entry("face.description", "Directly narrated overall physical face description."),
    _entry("face.distinctive_mark", "Other localized, distinctive facial mark."),
    _entry("face.injury", "Current visible injury localized to the face."),
    _entry("clothing.type", "Garment kind."),
    _entry("clothing.color", "Garment colour, bound to a specific garment semantic unit."),
    _entry("clothing.material", "Garment fabric or substance."),
    _entry("clothing.condition", "Visible garment wear, damage, or physical condition."),
    _entry("clothing.coverage", "Explicit dressed, bare, exposed, or covered body region."),
    _entry("clothing.footwear", "Shoes, boots, or other worn footwear."),
    _entry("clothing.outerwear", "Coat, cloak, robe, or other explicit outer layer."),
    _entry("clothing.style", "Explicit overall clothing style; not a garment list."),
    _entry("accessories.headwear", "Independently worn hat, crown, veil, or headwear."),
    _entry("accessories.belt", "Worn belt, sash, or waist accessory."),
    _entry("accessories.earrings", "Worn earring or ear ornament."),
    _entry("accessories.wrist", "Worn wrist or forearm ornament."),
    _entry("accessories.gloves", "Worn gloves or hand covering."),
    _entry("accessories.insignia", "Worn or garment-bound badge, emblem, or insignia."),
    _entry("accessories.wig", "Worn wig or false hair item."),
    _entry("accessories.other", "Other explicitly worn accessory; never a held or nearby object."),
    _entry("cleanliness", "Directly stated cleanliness, dirt, stain, or washing state."),
    _entry("injuries.description", "Current visible bodily injury, including explicit location."),
    _entry("distinctive_marks.scar", "Scar tissue or explicit absence of scars."),
    _entry("distinctive_marks.tattoo", "Applied or inked body marking."),
    _entry("distinctive_marks.beard", "Facial hair or beard appearance."),
    _entry("distinctive_marks.claws", "Visible claw or talon body feature."),
    _entry("disguise.hair_color", "Hair colour specifically produced by a disguise."),
    _entry("disguise.description", "Other directly visible disguise appearance."),
)

VISUAL_FIELD_PATHS = frozenset(item.field_path for item in VISUAL_FIELD_CATALOG)

if len(VISUAL_FIELD_PATHS) != len(VISUAL_FIELD_CATALOG):
    raise RuntimeError("duplicate_visual_field_catalog_path")


def is_catalog_field(field_path: str) -> bool:
    return field_path in VISUAL_FIELD_PATHS


def visual_field_catalog_payload() -> list[dict[str, str]]:
    return [
        {
            "field_path": item.field_path,
            "value_type": item.value_type,
            "description": item.description,
        }
        for item in VISUAL_FIELD_CATALOG
    ]
