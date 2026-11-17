from app.gemini import GeminiRouter


def test_does_not_try_unknown_models():
    router = GeminiRouter("", ("gemini-2.5-flash-lite", "gemini-2.5-flash-lite", "another-paid-model"))
    assert router.model_ids == ("gemini-2.5-flash-lite",)
    scored = router.evaluate({"timestamp":1, "heuristic_score":.66})
    assert scored["model_used"] == "local-heuristic"
    assert scored["score"] == .66
