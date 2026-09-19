from vakforge.locales import get_pack
from vakforge.recommend import Constraints, recommend

HI = get_pack("hi-Latn-IN")
US = get_pack("en-US")


def summary(**over):
    base = {
        "counts": {"document": 0, "table": 0, "chat": 0, "audio": 0, "other": 0},
        "document_words": 0,
        "chat_messages": 0,
        "audio_hours": 0.0,
        "stereo_audio_files": 0,
        "languages": {},
        "pii": {},
        "tool_candidates": [],
    }
    base.update(over)
    return base


def test_documents_only_means_retrieval_not_fine_tune():
    r = recommend(summary(counts={"document": 3}, document_words=4000), US)
    assert r.primary_problem == "knowledge"
    assert r.fine_tune is False
    assert r.recipe is None
    assert [x.route for x in r.routes] == ["retrieval"]
    assert "stale" in r.fine_tune_reason


def test_tables_and_chats_without_gpu_defer_training_to_colab():
    r = recommend(
        summary(
            counts={"table": 1, "chat": 1},
            chat_messages=900,
            tool_candidates=["lookup_orders_by_order_id"],
        ),
        US,
    )
    assert r.primary_problem == "tools"
    assert r.fine_tune is True
    assert r.recipe == "lfm25-audio"
    assert "24 GB" in r.recipe_reason and "Colab" in r.recipe_reason
    assert r.turns_have == 900 and r.turns_need == 600


def test_data_gap_triggers_synth_step():
    r = recommend(summary(counts={"chat": 1}, chat_messages=300), US, Constraints(gpu="24"))
    assert r.fine_tune is True
    assert any("data gap: 300 of ~600" in s for s in r.next_steps)


def test_a_handful_of_turns_is_not_enough_to_train():
    r = recommend(summary(counts={"chat": 1}, chat_messages=3), US, Constraints(gpu="24"))
    assert r.fine_tune is False
    assert "only 3 conversation turns" in r.fine_tune_reason
    assert any("data gap: 3 of ~600" in s for s in r.next_steps)


def test_no_conversations_means_no_fine_tune_yet():
    r = recommend(summary(counts={"table": 1}, tool_candidates=["lookup_orders_by_order_id"]), US)
    assert r.fine_tune is False
    assert "synth" in r.fine_tune_reason


def test_hinglish_marks_lfm25_understand_only():
    r = recommend(
        summary(counts={"chat": 1}, chat_messages=800, languages={"hi-Latn": 20, "en-IN": 10}),
        HI,
        Constraints(gpu="24"),
    )
    assert r.recipe == "lfm25-audio"
    assert r.recipe_support == "understand_only"
    assert "speech output stays English" in r.recipe_reason
    assert "language" in r.goals


def test_duplex_needs_stereo_and_hours():
    mono = recommend(
        summary(counts={"audio": 40}, audio_hours=20, stereo_audio_files=0),
        US,
        Constraints(gpu="80", duplex=True),
    )
    assert mono.recipe is None and "stereo" in mono.recipe_reason
    stereo = recommend(
        summary(counts={"audio": 40}, audio_hours=20, stereo_audio_files=40),
        US,
        Constraints(gpu="80", duplex=True),
    )
    assert stereo.recipe == "moshi-lora" and stereo.fine_tune is True
    thin = recommend(
        summary(counts={"audio": 2}, audio_hours=1, stereo_audio_files=2),
        US,
        Constraints(gpu="80", duplex=True),
    )
    assert thin.fine_tune is False and "10+ hours" in thin.fine_tune_reason


def test_consent_checklist_from_pack_and_pii():
    r = recommend(summary(counts={"audio": 3}, audio_hours=0.5, pii={"phone": 4, "aadhaar": 1}), HI)
    assert any("notice_required" in c for c in r.consent)
    assert any("phone, aadhaar" in c for c in r.consent)
    assert any("Digital Personal Data Protection" in c for c in r.consent)


def test_explicit_goals_override_inference():
    r = recommend(summary(counts={"document": 2}), US, Constraints(goals=("workflow",), gpu="24"))
    assert r.primary_problem == "workflow"
    assert r.fine_tune is False  # no conversations yet
    assert r.to_dict()["goals"] == ["workflow"]
