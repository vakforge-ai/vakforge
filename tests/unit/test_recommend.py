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


def d(rec):
    """The decision for the report's primary goal — what the old flat fields used to hold."""
    return rec.decision(rec.primary_problem)


def test_documents_only_means_retrieval_never_fine_tune():
    # Facts in weights go stale and raise hallucination, so no amount of documents moves
    # this verdict. It is blocked, not "not yet".
    r = recommend(summary(counts={"document": 3}, document_words=4000), US)
    assert r.primary_problem == "knowledge"
    assert d(r).eligibility == "blocked"
    assert d(r).recipe is None
    assert [x.route for x in r.routes] == ["retrieval"]
    assert "retrieval" in d(r).reason
    assert d(r).confidence == "measured"
    assert "2312.05934" in d(r).evidence


def test_every_goal_gets_its_own_decision():
    # The reproduced failure: with --goal tools --goal recognition, recognition appeared in
    # `goals` and then received no eligibility, no bar, no evidence and no recipe of its own.
    r = recommend(
        summary(counts={"chat": 2, "audio": 30}, chat_messages=900, audio_hours=25),
        US,
        Constraints(goals=("tools", "recognition"), gpu="24"),
    )
    assert [x.goal for x in r.goal_decisions] == ["tools", "recognition"]

    tools, recognition = r.goal_decisions
    # Different units, different bars, different evidence — and separately reached verdicts.
    assert (tools.unit, recognition.unit) == ("turns", "hours")
    assert (tools.have, recognition.have) == (900, 25)
    assert tools.need != recognition.need
    assert tools.evidence != recognition.evidence
    for decision in (tools, recognition):
        assert decision.eligibility in {"blocked", "baseline_first", "candidate"}
        assert decision.reason and decision.evidence

    # And the plan names both, rather than only whichever goal happened to sort first.
    assert any(s.startswith("tools:") for s in r.next_steps)
    assert any(s.startswith("recognition") for s in r.next_steps)


def test_the_project_verdict_is_the_best_any_goal_reached():
    # knowledge can never be trained; workflow here can. The project is not "blocked"
    # just because one of its goals is.
    r = recommend(
        summary(counts={"chat": 2, "document": 1}, chat_messages=2000, document_words=500),
        US,
        Constraints(goals=("knowledge", "workflow"), gpu="24"),
    )
    assert r.decision("knowledge").eligibility == "blocked"
    assert r.decision("workflow").eligibility == "candidate"
    assert r.fine_tune == "candidate"
    assert "workflow" in r.fine_tune_reason


def test_a_lot_of_documents_does_not_unblock_knowledge():
    lots = recommend(summary(counts={"document": 5000}, document_words=9_000_000), US)
    assert d(lots).eligibility == "blocked"


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
    assert d(r).eligibility == "baseline_first"
    assert d(r).recipe == "lfm25-audio"
    assert "24 GB" in d(r).recipe_reason and "Colab" in d(r).recipe_reason
    assert d(r).have == 900 and d(r).need == 8000 and d(r).unit == "turns"


def test_the_target_is_labelled_with_how_well_supported_it_is():
    tools = recommend(
        summary(counts={"chat": 1}, chat_messages=300), US, Constraints(goals=("tools",), gpu="24")
    )
    workflow = recommend(
        summary(counts={"chat": 1}, chat_messages=300), US, Constraints(goals=("workflow",))
    )
    # 8k is the scale of the published corpora, not a measured minimum for one company's
    # tools, so it is "reported" rather than "measured".
    assert d(tools).confidence == "reported"
    assert "not a measured minimum" in d(tools).evidence
    assert d(workflow).confidence == "heuristic"  # 600 is ours, and says so
    assert "neither validates 600" in d(workflow).evidence


def test_data_gap_step_quotes_the_gap_and_its_confidence():
    r = recommend(
        summary(counts={"chat": 1}, chat_messages=300), US, Constraints(goals=("workflow",))
    )
    assert d(r).eligibility == "baseline_first"
    assert any("workflow: 300 of ~600 conversation turns" in s for s in r.next_steps)
    assert any("heuristic" in s for s in r.next_steps)


def test_a_handful_of_turns_is_below_the_floor():
    r = recommend(summary(counts={"chat": 1}, chat_messages=3), US, Constraints(gpu="24"))
    assert d(r).eligibility == "blocked"
    assert "below the 200 conversation turns floor" in d(r).reason


def test_enough_turns_makes_it_a_candidate_and_still_asks_for_the_baseline():
    r = recommend(
        summary(counts={"chat": 1}, chat_messages=2000),
        US,
        Constraints(goals=("workflow",), gpu="24"),
    )
    assert d(r).eligibility == "candidate"
    assert "baseline" in d(r).reason
    assert r.next_steps[0].startswith("measure the base model")
    assert any("compare base vs tuned" in s for s in r.next_steps)


def test_no_conversations_means_nothing_to_train_on():
    r = recommend(summary(counts={"table": 1}, tool_candidates=["lookup_orders_by_order_id"]), US)
    assert d(r).eligibility == "blocked"
    assert "synth" in d(r).reason


def test_hinglish_marks_lfm25_understand_only():
    r = recommend(
        summary(counts={"chat": 1}, chat_messages=800, languages={"hi-Latn": 20, "en-IN": 10}),
        HI,
        Constraints(gpu="24"),
    )
    assert d(r).recipe == "lfm25-audio"
    assert d(r).recipe_support == "understand_only"
    assert "speech output stays English" in d(r).recipe_reason
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
    assert d(r).eligibility == "blocked"
    assert "already interrupts" in d(r).reason
    assert "1,217" in d(r).evidence
    # A recipe is still named, because the user does need a duplex-capable base model.
    assert d(r).recipe == "moshi-lora"


def test_a_duplex_base_is_named_even_when_the_data_cannot_adapt_it():
    # Choosing a model that can already hold a duplex conversation and having data to
    # adapt it are two different questions. Answering "no recipe" to the first because
    # the second failed left the user with nothing to build on.
    mono = recommend(
        summary(counts={"audio": 40}, audio_hours=20, two_channel_audio_files=0),
        US,
        Constraints(gpu="80", duplex=True),
    )
    duplex = mono.decision("duplex")
    assert duplex.recipe == "moshi-lora"
    assert any("separate channels" in b for b in duplex.blockers)
    assert any("blocked on" in s and "separate channels" in s for s in mono.next_steps)


def test_raw_audio_hours_are_never_counted_as_conversation_turns():
    # The reproduced failure: two hours of untouched recordings became exactly 600
    # workflow turns and a `candidate`, with no transcript, diarization or labels.
    r = recommend(
        summary(counts={"audio": 8}, audio_hours=2.0),
        US,
        Constraints(goals=("workflow",), gpu="24"),
    )
    assert d(r).have == 0
    assert d(r).eligibility == "blocked"
    assert any("transcribed and diarized" in u for u in d(r).uncounted)
    assert any("not counted yet" in s for s in r.next_steps)


def test_audio_evidence_cannot_reach_candidate_while_unverified():
    # 40 h clears the 20 h recognition target, but duration alone proves nothing about
    # transcripts, speaker labels or consent, so the verdict stops short of candidate.
    r = recommend(
        summary(counts={"audio": 200}, audio_hours=40.0),
        US,
        Constraints(goals=("recognition",), gpu="24"),
    )
    assert d(r).have == 40.0
    assert d(r).eligibility == "baseline_first"
    assert "nothing has verified it is usable" in d(r).reason


def test_chat_messages_are_real_turns_and_do_reach_candidate():
    # Parsed chat messages are genuine conversation turns, so they are counted in full.
    r = recommend(
        summary(counts={"chat": 4}, chat_messages=2000),
        US,
        Constraints(goals=("workflow",), gpu="24"),
    )
    assert d(r).have == 2000
    assert d(r).have_from == "2000 parsed chat messages"
    assert d(r).uncounted == []
    assert d(r).eligibility == "candidate"


def test_a_folder_with_nothing_usable_says_so_instead_of_guessing_knowledge():
    # One table with no id column: the old fallback named "knowledge" as the problem and
    # explained that facts belong in retrieval, for a folder with no documents in it.
    r = recommend(summary(counts={"table": 1}), US)
    assert r.primary_problem is None
    assert r.goals == [] and r.goal_decisions == []
    assert r.fine_tune == "blocked" and "nothing here is evidence" in r.fine_tune_reason
    [route] = r.routes
    assert route.source == "nothing usable yet" and "found 1 table" in route.why
    assert r.next_steps[0].startswith("nothing here is evidence yet")


def test_large_counts_are_written_out_not_in_scientific_notation():
    # A million-row export was reported as "2.00265e+06 conversation turns".
    r = recommend(summary(counts={"chat": 1}, chat_messages=2002646), HI)
    text = " ".join([d(r).reason, *r.next_steps])
    assert "2002646" in text and "e+06" not in text


def test_files_that_could_not_be_read_get_no_route():
    # Two PDFs, skipped: the verdict said "no usable evidence" while a route still said
    # "documents -> retrieval".
    r = recommend(summary(counts={"document": 2}, profiled={"document": 0}), US)
    [route] = r.routes
    assert route.source == "nothing usable yet"
    assert "2 files could not be read" in route.why
    assert "id column" not in route.why  # nothing was read, so no column is to blame


def test_an_empty_folder_is_nothing_yet():
    r = recommend(summary(), US)
    assert r.primary_problem is None
    assert [x.source for x in r.routes] == ["nothing yet"]


def test_unprofiled_files_do_not_infer_goals():
    # Audio that was discovered but never read proves nothing about the user's intent.
    found_only = summary(counts={"audio": 10}, profiled={"audio": 0})
    assert "recognition" not in recommend(found_only, US).goals


def test_voice_is_measured_in_seconds_not_hours():
    # Seconds, not hours — but the bar still does not reach `candidate` on half an hour of
    # audio, because total duration says nothing about whether it is one speaker, recorded
    # consistently, who agreed to their voice being used.
    r = recommend(
        summary(counts={"audio": 3}, audio_hours=0.5),
        US,
        Constraints(goals=("voice",), gpu="48"),
    )
    assert d(r).unit == "seconds"
    assert d(r).have == 1800
    assert d(r).eligibility == "baseline_first"
    assert any("one consented speaker" in u for u in d(r).uncounted)


def test_the_voice_bar_does_not_pass_off_a_zero_shot_prompt_as_training_data():
    # VALL-E's 3 seconds is an inference prompt to a model pretrained on 60k hours. It is
    # not a measured minimum for adapting a voice model, and labelling it `measured`
    # claimed evidence the citation does not carry.
    voice = recommend(
        summary(counts={"audio": 3}, audio_hours=0.5), US, Constraints(goals=("voice",))
    ).decision("voice")
    assert voice.confidence == "heuristic"
    assert "inference-time prompt" in voice.evidence
    assert "no published work establishes a minimum" in voice.evidence


def test_recognition_recommends_biasing_before_collecting_hours():
    r = recommend(
        summary(counts={"audio": 5}, audio_hours=2),
        US,
        Constraints(goals=("recognition",), gpu="24"),
    )
    assert d(r).unit == "hours"
    assert d(r).eligibility == "blocked"  # 2 h is under the 10 h floor
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
    assert d(r).eligibility == "blocked"  # no conversations yet
    assert r.to_dict()["goals"] == ["workflow"]
