from embedding_client import MIN_RELEVANCE, semantic_matches, split_text


def answer_question(question: str, rfp_text: str) -> str:
    """Return the most relevant RFP evidence for a natural-language question."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string.")
    if not isinstance(rfp_text, str) or not rfp_text.strip():
        raise ValueError("rfp_text must be a non-empty string.")

    passages = split_text(rfp_text, max_chars=240)
    matches = semantic_matches([question.strip()], passages, top_k=3)[0]
    relevant = [match for match in matches if match["similarity"] >= MIN_RELEVANCE]
    if not relevant:
        return "No sufficiently relevant answer was found in the supplied RFP text."

    unique_passages: list[str] = []
    for match in relevant:
        if match["text"] not in unique_passages:
            unique_passages.append(match["text"])
    return "Relevant RFP evidence: " + " ".join(unique_passages)
