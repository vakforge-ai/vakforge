from vakforge.locales import get_pack
from vakforge.recommend import Constraints, recommend

HI = get_pack("hi-Latn-IN")
US = get_pack("en-US")


def summary(**over):
    base = {
        "counts": {"document": 0, "table": 0, "chat": 0, "audio": 0, "other": 0},
        "profiled": None,  # defaults to counts below, as a real report has both
        "document_words": 0,
        "chat_messages": 0,
        "audio_hours": 0.0,
        "two_channel_audio_files": 0,
        "languages": {},
        "pii": {},
        "tool_candidates": [],
    }
    base.update(over)
    if base["profiled"] is None:
        base["profiled"] = base["counts"]
    return base


def test_documents_only_means_retrieval_never_fine_tune():
    # Facts in weights go stale and raise hallucination, so no amount of documents moves
    # this verdict. It is blocked, not "not yet".
    r = recommend(summary(counts={"document": 3}, document_words=4000), US)
    assert r.primary_problem == "knowledge"
    assert r.fine_tune == "blocked"
    assert r.recipe is None
    assert [x.route for x in r.routes] == ["retrieval"]
    assert "retrieval" in r.fine_tune_reason
    assert r.evidence_confidence == "measured"
    assert "2312.05934" in r.evidence


def test_a_lot_of_documents_does_not_unblock_knowledge():
    lots = recommend(summary(counts={"document": 5000}, document_words=9_000_000), US)
    assert lots.fine_tune == "blocked"


def test_tables_and_chats_sit_below_the_tool_corpus_target():
    r = recommend(
        summary(
            counts={"table": 1, "chat": 1},
            chat_messages=900,
            tool_candidates=["lookup_orders_by_order_id"],
        ),
        US,
    )
    assert r.primary_problem == "tools"
    # 900 turns clears the floor but is two orders of magnitude off the published corpora.
    assert r.fine_tune == "baseline_first"
    assert r.recipe == "lfm25-audio"
    assert "24 GB" in r.recipe_reason and "Colab" in r.recipe_reason
    assert r.have == 900 and r.need == 8000 and r.need_unit == "turns"


def test_the_target_is_labelled_with_how_well_supported_it_is():
    tools = recommend(
        summary(counts={"chat": 1}, chat_messages=300), US, Constraints(goals=("tools",), gpu="24")
    )
    workflow = recommend(
        summary(counts={"chat": 1}, chat_messages=300), US, Constraints(goals=("workflow",))
    )
    # 8k is the scale of the published corpora, not a measured minimum for one company's
    # tools, so it is "reported" rather than "measured".
    assert tools.evidence_confidence == "reported"
    assert "not a measured minimum" in tools.evidence
    assert workflow.evidence_confidence == "heuristic"  # 600 is ours, and says so
    assert "neither validates 600" in workflow.evidence


def test_data_gap_step_quotes_the_gap_and_its_confidence():
    r = recommend(
        summary(counts={"chat": 1}, chat_messages=300), US, Constraints(goals=("workflow",))
    )
    assert r.fine_tune == "baseline_first"
    assert any("data gap: 300 of ~600 conversation turns" in s for s in r.next_steps)
    assert any("heuristic" in s for s in r.next_steps)


def test_a_handful_of_turns_is_below_the_floor():
    r = recommend(summary(counts={"chat": 1}, chat_messages=3), US, Constraints(gpu="24"))
    assert r.fine_tune == "blocked"
    assert "below the 200 conversation turns floor" in r.fine_tune_reason


def test_enough_turns_makes_it_a_candidate_and_still_asks_for_the_baseline():
    r = recommend(
        summary(counts={"chat": 1}, chat_messages=2000),
        US,
        Constraints(goals=("workflow",), gpu="24"),
    )
    assert r.fine_tune == "candidate"
    assert "baseline" in r.fine_tune_reason
    assert r.next_steps[0].startswith("measure the base model")
    assert any("compare base vs tuned" in s for s in r.next_steps)


def test_no_conversations_means_nothing_to_train_on():
    r = recommend(summary(counts={"table": 1}, tool_candidates=["lookup_orders_by_order_id"]), US)
    assert r.fine_tune == "blocked"
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


def test_duplex_is_a_model_choice_not_a_training_budget():
    # The company-scale case: 20 hours of two-channel calls. The old rule called this
    # enough to train duplex; PersonaPlex used ~1,217 h of real audio, so it is not.
    r = recommend(
        summary(counts={"audio": 40}, audio_hours=20, two_channel_audio_files=40),
        US,
        Constraints(gpu="80", duplex=True),
    )
    assert r.primary_problem == "duplex"
    assert r.fine_tune == "blocked"
    assert "already interrupts" in r.fine_tune_reason
    assert "1,217" in r.evidence
    # A recipe is still named, because the user does need a duplex-capable base model.
    assert r.recipe == "moshi-lora"


def test_duplex_recipe_still_needs_two_channel_recordings():
    mono = recommend(
        summary(counts={"audio": 40}, audio_hours=20, two_channel_audio_files=0),
        US,
        Constraints(gpu="80", duplex=True),
    )
    assert mono.recipe is None and "stereo" in mono.recipe_reason


def test_raw_audio_hours_are_never_counted_as_conversation_turns():
    # The reproduced failure: two hours of untouched recordings became exactly 600
    # workflow turns and a `candidate`, with no transcript, diarization or labels.
    r = recommend(
        summary(counts={"audio": 8}, audio_hours=2.0),
        US,
        Constraints(goals=("workflow",), gpu="24"),
    )
    assert r.have == 0
    assert r.fine_tune == "blocked"
    assert any("transcribed and diarized" in u for u in r.uncounted)
    assert any("not counted yet" in s for s in r.next_steps)


def test_audio_evidence_cannot_reach_candidate_while_unverified():
    # 40 h clears the 20 h recognition target, but duration alone proves nothing about
    # transcripts, speaker labels or consent, so the verdict stops short of candidate.
    r = recommend(
        summary(counts={"audio": 200}, audio_hours=40.0),
        US,
        Constraints(goals=("recognition",), gpu="24"),
    )
    assert r.have == 40.0
    assert r.fine_tune == "baseline_first"
    assert "nothing has verified it is usable" in r.fine_tune_reason


def test_chat_messages_are_real_turns_and_do_reach_candidate():
    # Parsed chat messages are genuine conversation turns, so they are counted in full.
    r = recommend(
        summary(counts={"chat": 4}, chat_messages=2000),
        US,
        Constraints(goals=("workflow",), gpu="24"),
    )
    assert r.have == 2000
    assert r.have_from == "2000 parsed chat messages"
    assert r.uncounted == []
    assert r.fine_tune == "candidate"


def test_unprofiled_files_do_not_infer_goals():
    # Audio that was discovered but never read proves nothing about the user's intent.
    found_only = summary(counts={"audio": 10}, profiled={"audio": 0})
    assert "recognition" not in recommend(found_only, US).goals


def test_voice_cloning_is_measured_in_seconds_not_hours():
    # VALL-E clones from a 3-second prompt, so half an hour of audio is far past the bar.
    # It still does not reach `candidate`: total duration says nothing about whether the
    # audio is one speaker, recorded consistently, who consented to their voice being used.
    r = recommend(
        summary(counts={"audio": 3}, audio_hours=0.5),
        US,
        Constraints(goals=("voice",), gpu="48"),
    )
    assert r.need_unit == "seconds"
    assert r.have == 1800
    assert r.fine_tune == "baseline_first"
    assert any("one consented speaker" in u for u in r.uncounted)
    assert "consent for that speaker's voice" in r.evidence


def test_recognition_recommends_biasing_before_collecting_hours():
    r = recommend(
        summary(counts={"audio": 5}, audio_hours=2),
        US,
        Constraints(goals=("recognition",), gpu="24"),
    )
    assert r.need_unit == "hours"
    assert r.fine_tune == "blocked"  # 2 h is under the 10 h floor
    assert any("bias the recogniser" in s for s in r.next_steps)


def test_audio_route_leads_with_contextual_biasing():
    r = recommend(summary(counts={"audio": 5}, audio_hours=2, two_channel_audio_files=5), US)
    routes = {x.route for x in r.routes}
    assert "contextual biasing, then recognition" in routes
    assert "duplex model choice" in routes


def test_consent_checklist_from_pack_and_pii():
    r = recommend(summary(counts={"audio": 3}, audio_hours=0.5, pii={"phone": 4, "aadhaar": 1}), HI)
    assert any("notice_required" in c for c in r.consent)
    assert any("phone, aadhaar" in c for c in r.consent)
    assert any("Digital Personal Data Protection" in c for c in r.consent)


def test_explicit_goals_override_inference():
    r = recommend(summary(counts={"document": 2}), US, Constraints(goals=("workflow",), gpu="24"))
    assert r.primary_problem == "workflow"
    assert r.fine_tune == "blocked"  # no conversations yet
    assert r.to_dict()["goals"] == ["workflow"]
