"""Pydantic-схемы (ТЗ раздел 13) + схемы вне §13 (SERP, LSI, review, desktop).

Нормализация legacy desktop-формата централизована в legacy_compat.py.
Выходной контракт пайплайна — строго §13.
"""

from .article_input import ArticleInput
from .brief import Brief, DataHandlingRules, KeywordsBlock
from .competitor import (
    CommonH2Title,
    CompetitorAnalysisReport,
    ContentGap,
    DataSensitivity,
    WordCountRange,
)
from .desktop_artifacts import SectionDraftArtifact, SectionReviewArtifact
from .factcheck import FactCheckReport, FactCheckResult, FactStatement
from .final_package import FaqItem, FinalPackage, SchemaBlock
from .misc import LSIResult, ReviewData, ReviewDataInner
from .outline import FaqSection, Outline, SectionSpec
from .qa import CriteriaScores, QAResult, QAWarnings
from .section import CriticFeedback, FullDraft, SectionAttempt, SectionFinal
from .serp import AggregatedData, HeadingsData, PageData, SerpBundle

__all__ = [
    # §13.1
    "ArticleInput",
    # §13.2
    "WordCountRange",
    "CommonH2Title",
    "ContentGap",
    "DataSensitivity",
    "CompetitorAnalysisReport",
    # §13.3
    "KeywordsBlock",
    "DataHandlingRules",
    "Brief",
    # §13.4
    "SectionSpec",
    "FaqSection",
    "Outline",
    # §13.5
    "SectionAttempt",
    "CriticFeedback",
    "SectionFinal",
    # §13.6
    "FullDraft",
    # §13.7 / 9.3
    "FactStatement",
    "FactCheckResult",
    "FactCheckReport",
    # §13.8
    "CriteriaScores",
    "QAWarnings",
    "QAResult",
    # §13.9
    "FaqItem",
    "SchemaBlock",
    "FinalPackage",
    # вне §13
    "SerpBundle",
    "PageData",
    "HeadingsData",
    "AggregatedData",
    "LSIResult",
    "ReviewData",
    "ReviewDataInner",
    "SectionDraftArtifact",
    "SectionReviewArtifact",
]
