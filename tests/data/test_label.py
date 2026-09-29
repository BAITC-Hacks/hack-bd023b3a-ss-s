"""SMOKE tests for `qorgan.data.label` — mocked Gemini client only, no network."""

import json
from types import SimpleNamespace

import pytest

from qorgan.data.label import LabelingError, label_corpus, label_dialogue
from qorgan.data.schema import Dialogue, Label, TacticTag, Utterance, spans_from_phrases


class FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


def _response(payload):
    return SimpleNamespace(text=json.dumps(payload), parsed=None)


def _dialogue(texts, *, did="d1", risk=0.9, tags=(), phrases=(), hard_negative=False):
    utterances = tuple(Utterance(speaker="caller", text=t) for t in texts)
    transcript = "\n".join(texts)
    return Dialogue(
        id=did,
        language="ru",
        utterances=utterances,
        label=Label(
            risk=risk,
            tactic_tags=tuple(TacticTag(id=t) for t in tags),
            trigger_spans=spans_from_phrases(phrases, transcript),
            is_hard_negative=hard_negative,
        ),
    )


def test_label_dialogue_returns_new_dialogue_with_model_label():
    dialogue = _dialogue(
        ["Продиктуйте код из SMS немедленно.", "Хорошо."], did="orig", tags=["urgency"]
    )
    client = FakeClient(
        [_response({"risk": 0.95, "tactic_tags": [{"id": "otp_request", "weight": 0.9}], "trigger_phrases": ["код из SMS"]})]
    )

    relabeled = label_dialogue(dialogue, client=client)

    assert isinstance(relabeled, Dialogue)
    assert relabeled is not dialogue
    assert relabeled.id == "orig"  # identity preserved
    assert relabeled.label.risk == 0.95
    assert relabeled.label.tactic_tags[0].id == "otp_request"
    assert relabeled.label.trigger_spans[0].text == "код из SMS"


def test_label_dialogue_drops_tags_not_in_taxonomy():
    dialogue = _dialogue(["Позвоните нам."])
    client = FakeClient(
        [_response({"risk": 0.5, "tactic_tags": [{"id": "not_a_real_tactic"}, {"id": "urgency"}], "trigger_phrases": []})]
    )

    relabeled = label_dialogue(dialogue, client=client)

    ids = [t.id for t in relabeled.label.tactic_tags]
    assert "not_a_real_tactic" not in ids
    assert "urgency" in ids


def test_label_dialogue_drops_hallucinated_trigger_phrase():
    dialogue = _dialogue(["Продиктуйте код из SMS."])
    client = FakeClient(
        [_response({"risk": 0.9, "tactic_tags": [], "trigger_phrases": ["код из SMS", "выдуманная фраза"]})]
    )

    relabeled = label_dialogue(dialogue, client=client)

    texts = [s.text for s in relabeled.label.trigger_spans]
    assert texts == ["код из SMS"]


def test_label_dialogue_preserves_hard_negative_flag():
    dialogue = _dialogue(["Обычный звонок."], hard_negative=True, risk=0.02)
    client = FakeClient([_response({"risk": 0.05, "tactic_tags": [], "trigger_phrases": []})])

    relabeled = label_dialogue(dialogue, client=client)

    assert relabeled.label.is_hard_negative is True


def test_label_dialogue_clamps_out_of_range_risk():
    dialogue = _dialogue(["Текст."])
    client = FakeClient([_response({"risk": 1.7, "tactic_tags": [], "trigger_phrases": []})])

    relabeled = label_dialogue(dialogue, client=client)

    assert relabeled.label.risk == 1.0


def test_label_dialogue_missing_risk_raises_labeling_error():
    dialogue = _dialogue(["Текст."])
    client = FakeClient([_response({"tactic_tags": [], "trigger_phrases": []})])

    with pytest.raises(LabelingError):
        label_dialogue(dialogue, client=client)


def test_label_prompt_enumerates_taxonomy_ids():
    from qorgan.taxonomy import get_taxonomy

    dialogue = _dialogue(["Текст."])
    client = FakeClient([_response({"risk": 0.5, "tactic_tags": [], "trigger_phrases": []})])
    label_dialogue(dialogue, client=client)

    system_instruction = client.models.calls[0]["config"]["system_instruction"]
    tactic_ids = get_taxonomy().tactic_ids()
    # Every valid tactic id must be listed so the model emits ids we actually keep.
    assert all(tid in system_instruction for tid in tactic_ids)


def test_label_corpus_labels_all_and_counts_calls():
    dialogues = [_dialogue(["Первый."], did="d1"), _dialogue(["Второй."], did="d2")]
    client = FakeClient([_response({"risk": 0.3, "tactic_tags": [], "trigger_phrases": []})])

    relabeled = label_corpus(dialogues, client=client)

    assert len(relabeled) == 2
    assert [d.id for d in relabeled] == ["d1", "d2"]
    assert len(client.models.calls) == 2


# --- resilience: labelling is another few-hundred-call run (ADR D53) -----------------------


_LABEL_PAYLOAD = {"risk": 0.95, "tactic_tags": [{"id": "otp_request", "weight": 0.9}], "trigger_phrases": []}


class _Flaky:
    """Fails `failures` times with a dropped connection, then answers."""

    def __init__(self, failures: int, response):
        self.remaining = failures
        self._response = response
        self.calls = 0
        self.models = self

    def generate_content(self, **_kwargs):
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise ConnectionError("Connection reset by peer")
        return self._response


def test_label_dialogue_retries_a_dropped_connection():
    client = _Flaky(2, _response(_LABEL_PAYLOAD))
    labeled = label_dialogue(_dialogue(["Назовите код."]), client=client)
    assert labeled.label.risk == 0.95
    assert client.calls == 3


def test_label_corpus_streams_and_skips_already_labeled():
    """A crashed labelling run must resume, not start the whole corpus again."""
    client = _Flaky(0, _response(_LABEL_PAYLOAD))
    first = _dialogue(["Назовите код."])
    second = first.model_copy(update={"id": "second"})
    seen: list[str] = []

    out = label_corpus([first, second], client=client, sink=lambda d: seen.append(d.id),
                       skip_ids={first.id})

    assert [d.id for d in out] == ["second"]
    assert seen == ["second"]
    assert client.calls == 1, "a skipped dialogue costs no API call"


def test_relabelling_never_turns_a_hard_negative_into_a_scam():
    """Hard negatives are legit BY CONSTRUCTION (generate.py forces risk 0.02, no tags).

    The labeller reads a transcript blind, and on a legitimate bank call that verifies an
    identity it happily returns risk 1.0 with tactic tags -- observed on 32 of 50 English
    negatives (ADR D54). Folding that in would poison the class FPR is measured on.
    """
    dialogue = _dialogue(["This is your bank, I need to verify your identity."], hard_negative=True, risk=0.02)
    client = FakeClient([_response({
        "risk": 1.0,
        "tactic_tags": [{"id": "impersonation_bank", "weight": 0.9}],
        "trigger_phrases": ["verify your identity"],
    })])

    relabeled = label_dialogue(dialogue, client=client)

    assert relabeled.label.is_hard_negative is True
    assert relabeled.label.risk <= 0.1, "a legit call must not be relabelled as a scam"
    assert relabeled.label.tactic_tags == ()
    assert relabeled.label.trigger_spans == ()
