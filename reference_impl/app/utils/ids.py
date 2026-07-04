import uuid


def generate_article_id() -> str:
    return str(uuid.uuid4())


def generate_section_id(index: int) -> str:
    return f"s{index + 1}"
