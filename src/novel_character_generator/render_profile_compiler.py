"""Compatibility API: legacy cards are projections of CharacterSnapshot."""
from .character_snapshot import (
    FACT_APPLICABILITY_POLICY_VERSION,
    RENDER_PROFILE_COMPILER_POLICY_VERSION,
    RENDER_PROFILE_REQUESTS_VERSION,
    RENDER_READY_CHARACTER_PROFILES_VERSION,
    PROFILE_STATUSES, APPLICABILITY_STATUSES, WARNING_CODES,
    _project_relation_outcomes,
    build_render_ready_character_profiles,
    run_render_ready_character_profiles,
)
