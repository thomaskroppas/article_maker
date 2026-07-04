"""Агенты пайплайна (шаги 2–5 в T-6; секции/QA — далее)."""

from .analysis import AnalysisStageResult, run_analysis_stage
from .base import BaseAgent
from .brief import BriefAgent, build_data_handling_rules, compute_target_word_count
from .cache import AgentCache
from .competitor import CompetitorAnalysisAgent, compute_ranges
from .content_gaps import filter_content_gaps
from .critic import CriticAgent
from .editor import EditorAgent
from .faq_writer import FaqWriterAgent, insert_faq, run_faq_stage
from .json_parse import extract_json
from .lsi import LSIAgent
from .markdown_builder import assemble_draft, has_faq_in_sections
from .outline import OutlineAgent
from .section_pipeline import SectionResult, run_section
from .sections_stage import SectionsStageResult, run_sections_stage
from .text_utils import count_words, extract_summary
from .writer import WriterAgent

__all__ = [
    "BaseAgent",
    "AgentCache",
    "extract_json",
    "CompetitorAnalysisAgent",
    "compute_ranges",
    "LSIAgent",
    "BriefAgent",
    "compute_target_word_count",
    "build_data_handling_rules",
    "OutlineAgent",
    "filter_content_gaps",
    "run_analysis_stage",
    "AnalysisStageResult",
    # T-8 — секции, сборка, FAQ
    "WriterAgent",
    "CriticAgent",
    "EditorAgent",
    "run_section",
    "SectionResult",
    "run_sections_stage",
    "SectionsStageResult",
    "assemble_draft",
    "has_faq_in_sections",
    "FaqWriterAgent",
    "run_faq_stage",
    "insert_faq",
    "extract_summary",
    "count_words",
]
