"""
Shared utilities used by all prompt sub-modules.
"""

_VI_CHARS = frozenset(
    "àáâãèéêìíòóôõùúăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ"
    "ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ"
)


def _detect_language(text: str) -> str:
    """Returns 'vi' if text contains Vietnamese diacritics, otherwise 'en'."""
    return "vi" if any(c in _VI_CHARS for c in text) else "en"


def _lang_instruction(user_text: str) -> str:
    lang = _detect_language(user_text)
    if lang == "vi":
        return "QUAN TRỌNG: Người dùng viết bằng Tiếng Việt. Trả lời hoàn toàn bằng TIẾNG VIỆT."
    return "IMPORTANT: The user wrote in English. Respond entirely in ENGLISH."


def _rag_block(context: str) -> str:
    """Wrap a RAG context string for injection into prompts.
    Returns empty string if context is empty so prompts stay clean."""
    if not context:
        return ""
    return f"\n\n{context}\n"
