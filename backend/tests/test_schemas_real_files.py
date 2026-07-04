"""T-2: схемы валидируются против РЕАЛЬНЫХ файлов fixtures/ и reference_article/.

ТЗ раздел 13 + CLAUDE.md «Тестовая дисциплина»: если схема не принимает реальный
файл — ошибка в схеме. Legacy desktop-формат нормализуется в schemas.legacy_compat.
"""

from __future__ import annotations

import glob
import json
import os

import pytest

from app import schemas
from app.paths import fixtures_dir, reference_dir

# Резолвер работает и локально, и в контейнере (каталоги смонтированы в /app).
FIXTURES = str(fixtures_dir())
REF = str(reference_dir())


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- fixtures/ → схема ---
FIXTURE_MAP = {
    "brief_example.json": schemas.Brief,
    "competitor_analysis_example.json": schemas.CompetitorAnalysisReport,
    "lsi_example.json": schemas.LSIResult,
    "outline_example.json": schemas.Outline,
    "serp_bundle_example.json": schemas.SerpBundle,
    "review_data_example.json": schemas.ReviewData,
}


@pytest.mark.parametrize("filename,model", FIXTURE_MAP.items())
def test_fixture_parses(filename, model):
    data = _load(os.path.join(FIXTURES, filename))
    obj = model.model_validate(data)
    assert obj is not None


def test_all_fixtures_covered():
    present = {os.path.basename(p) for p in glob.glob(os.path.join(FIXTURES, "*.json"))}
    assert present == set(FIXTURE_MAP), (
        f"Непокрытые fixtures: {present - set(FIXTURE_MAP)}"
    )


# --- reference_article/ (верхний уровень) → схема ---
REF_MAP = {
    "article_input.json": schemas.ArticleInput,
    "serp_bundle.json": schemas.SerpBundle,
    "competitor_analysis_report.json": schemas.CompetitorAnalysisReport,
    "brief.json": schemas.Brief,
    "outline.json": schemas.Outline,
    "full_draft.json": schemas.FullDraft,
    "final_package.json": schemas.FinalPackage,
    "qa_result.json": schemas.QAResult,
}


@pytest.mark.parametrize("filename,model", REF_MAP.items())
def test_reference_top_level_parses(filename, model):
    data = _load(os.path.join(REF, filename))
    obj = model.model_validate(data)
    assert obj is not None


def test_all_reference_top_level_covered():
    present = {os.path.basename(p) for p in glob.glob(os.path.join(REF, "*.json"))}
    assert present == set(REF_MAP), f"Непокрытые reference JSON: {present - set(REF_MAP)}"


# --- reference_article/sections/ (desktop-артефакты) ---
def _section_model(name: str):
    if "_review_" in name:
        return schemas.SectionReviewArtifact
    if name.endswith("_final.json"):
        return schemas.SectionFinal
    if name.endswith("_draft.json") or "_patched_" in name:
        return schemas.SectionDraftArtifact
    return None


SECTION_FILES = sorted(glob.glob(os.path.join(REF, "sections", "*.json")))


@pytest.mark.parametrize("path", SECTION_FILES, ids=[os.path.basename(p) for p in SECTION_FILES])
def test_reference_section_parses(path):
    name = os.path.basename(path)
    model = _section_model(name)
    assert model is not None, f"Не сопоставлена схема для {name}"
    obj = model.model_validate(_load(path))
    assert obj.section_id


def test_sections_directory_nonempty():
    assert SECTION_FILES, "sections/ пуст — нечего валидировать"
