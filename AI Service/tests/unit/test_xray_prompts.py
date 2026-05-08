"""
Unit tests for X-ray vision prompts added to Domain/prompts.py.
Validates that all X-ray prompt variants follow the design contract:
  - All output JSON
  - All contain urgency_indicators
  - All forbid definitive diagnosis
"""
import pytest
from Domain.prompts import VISION_PROMPTS


class TestBoneXrayPrompt:
    @pytest.fixture
    def prompt(self):
        return VISION_PROMPTS["bone_xray"]

    def test_requests_json_output(self, prompt):
        assert "RESPOND WITH ONLY THIS JSON" in prompt

    def test_forbids_diagnosis(self, prompt):
        assert "Do NOT make a diagnosis" in prompt

    def test_has_fracture_fields(self, prompt):
        assert "fracture_present" in prompt
        assert "fracture_description" in prompt

    def test_has_musculoskeletal_fields(self, prompt):
        assert "alignment" in prompt
        assert "bone_density" in prompt
        assert "joint_space" in prompt
        assert "soft_tissue" in prompt

    def test_has_urgency_indicators(self, prompt):
        assert "urgency_indicators" in prompt

    def test_has_confidence_field(self, prompt):
        assert '"confidence":' in prompt or "confidence" in prompt


class TestAbdominalXrayPrompt:
    @pytest.fixture
    def prompt(self):
        return VISION_PROMPTS["abdominal_xray"]

    def test_requests_json_output(self, prompt):
        assert "RESPOND WITH ONLY THIS JSON" in prompt

    def test_forbids_diagnosis(self, prompt):
        assert "Do NOT make a diagnosis" in prompt

    def test_has_bowel_gas_fields(self, prompt):
        assert "bowel_gas_pattern" in prompt
        assert "free_air_suspected" in prompt

    def test_has_calcification_fields(self, prompt):
        assert "calcifications_present" in prompt
        assert "calcification_description" in prompt

    def test_has_foreign_bodies(self, prompt):
        assert "foreign_bodies" in prompt

    def test_has_urgency_indicators(self, prompt):
        assert "urgency_indicators" in prompt

    def test_has_confidence_field(self, prompt):
        assert '"confidence":' in prompt or "confidence" in prompt


class TestSkullXrayPrompt:
    @pytest.fixture
    def prompt(self):
        return VISION_PROMPTS["skull_xray"]

    def test_requests_json_output(self, prompt):
        assert "RESPOND WITH ONLY THIS JSON" in prompt

    def test_forbids_diagnosis(self, prompt):
        assert "Do NOT make a diagnosis" in prompt

    def test_has_fracture_fields(self, prompt):
        assert "fracture_present" in prompt
        assert "fracture_description" in prompt

    def test_has_skull_specific_fields(self, prompt):
        assert "skull_vault" in prompt
        assert "sellar_region" in prompt
        assert "sutures" in prompt

    def test_has_urgency_indicators(self, prompt):
        assert "urgency_indicators" in prompt

    def test_has_confidence_field(self, prompt):
        assert '"confidence":' in prompt or "confidence" in prompt


class TestSpineXrayPrompt:
    @pytest.fixture
    def prompt(self):
        return VISION_PROMPTS["spine_xray"]

    def test_requests_json_output(self, prompt):
        assert "RESPOND WITH ONLY THIS JSON" in prompt

    def test_forbids_diagnosis(self, prompt):
        assert "Do NOT make a diagnosis" in prompt

    def test_has_alignment_fields(self, prompt):
        assert "alignment" in prompt
        assert "vertebral_bodies" in prompt
        assert "disc_height" in prompt

    def test_has_osteophyte_fields(self, prompt):
        assert "osteophytes_present" in prompt
        assert "osteophyte_description" in prompt

    def test_has_fracture_fields(self, prompt):
        assert "fracture_present" in prompt
        assert "fracture_description" in prompt

    def test_has_urgency_indicators(self, prompt):
        assert "urgency_indicators" in prompt

    def test_has_confidence_field(self, prompt):
        assert '"confidence":' in prompt or "confidence" in prompt


class TestXrayPromptCoverage:
    """Ensure all 4 new X-ray prompts are registered and reachable."""

    @pytest.mark.parametrize("key", [
        "bone_xray",
        "abdominal_xray",
        "skull_xray",
        "spine_xray",
    ])
    def test_xray_prompt_exists(self, key):
        assert key in VISION_PROMPTS

    @pytest.mark.parametrize("key", [
        "bone_xray",
        "abdominal_xray",
        "skull_xray",
        "spine_xray",
    ])
    def test_xray_prompt_is_non_empty(self, key):
        assert len(VISION_PROMPTS[key]) > 100
