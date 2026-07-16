import scoring


def test_scoring_uses_hybrid_relevance_not_raw_cosine(monkeypatch):
    monkeypatch.setattr(scoring, "split_criteria", lambda text: ["24/7 support"])
    monkeypatch.setattr(scoring, "split_text", lambda text: ["24/7 support included"])
    monkeypatch.setattr(
        scoring,
        "semantic_matches",
        lambda criteria, passages, top_k=1: [
            [
                {
                    "text": "24/7 support included",
                    "similarity": 0.25,
                    "relevance": 0.45,
                }
            ]
        ],
    )

    result = scoring.score_vendor("proposal", "criterion")
    assert result["score"] == 87
    assert result["criteria_results"][0]["similarity"] == 0.25
    assert result["criteria_results"][0]["relevance"] == 0.45
