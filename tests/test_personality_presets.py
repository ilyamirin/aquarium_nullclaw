from __future__ import annotations

from controlplane.domain.personality_presets import PERSONALITY_PRESETS


EXPECTED_KEYS = (
    "mara-field-operator",
    "viktor-hard-reviewer",
    "noa-scout",
    "sana-diplomat",
    "kiro-builder",
    "elin-mentor",
    "rook-wild-card",
)


def test_personality_preset_catalog_has_expected_keys_in_order() -> None:
    assert tuple(preset.key for preset in PERSONALITY_PRESETS) == EXPECTED_KEYS


def test_personality_preset_catalog_has_exactly_seven_unique_presets() -> None:
    keys = [preset.key for preset in PERSONALITY_PRESETS]

    assert len(PERSONALITY_PRESETS) == 7
    assert len(keys) == len(set(keys))


def test_personality_presets_have_required_non_empty_fields() -> None:
    required_fields = (
        "key",
        "display_name",
        "subtitle",
        "short_description",
        "best_for",
        "prompt",
    )

    for preset in PERSONALITY_PRESETS:
        for field_name in required_fields:
            assert getattr(preset, field_name).strip(), f"{preset.key}.{field_name} must be non-empty"


def test_personality_preset_prompts_are_russian_role_templates() -> None:
    for preset in PERSONALITY_PRESETS:
        assert preset.prompt.startswith("Ты — "), f"{preset.key} must start with a Russian role opening"
        assert "Твой рабочий процесс:" in preset.prompt
        assert "Стиль:" in preset.prompt
