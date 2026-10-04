from copy import deepcopy
import pytest
from training_data_lab.data import demo_example, encode_example, validate_example


def test_assistant_tool_calls_and_final_answer_are_supervised_but_tool_result_is_not():
    data = encode_example(demo_example(), pad_to=1024)
    assert len(data.input_ids) == len(data.labels) == len(data.attention_mask) == 1024
    role = None
    for token, token_id, label in zip(data.tokens, data.input_ids, data.labels):
        if token in {"<user>", "<assistant>", "<tool>", "<system>", "<tools>"}:
            role = token
            assert label == -100
        elif token in {"<bos>", "<pad>"}:
            assert label == -100
        else:
            assert label == (token_id if role == "<assistant>" else -100)
    assert data.tokens.count("<bos>") == 1
    assert sum(label == 2 for label in data.labels) == 2  # Both assistant EOS tokens.


@pytest.mark.parametrize("bad", ["missing-result", "unknown-tool", "extra-argument", "wrong-call-id"])
def test_tool_data_contract_rejects_bad_examples(bad):
    example = deepcopy(demo_example())
    if bad == "missing-result":
        del example["messages"][2]
    elif bad == "unknown-tool":
        example["messages"][1]["tool_calls"][0]["function"]["name"] = "unknown"
    elif bad == "extra-argument":
        example["messages"][1]["tool_calls"][0]["function"]["arguments"]["debug"] = True
    else:
        example["messages"][2]["tool_call_id"] = "unknown"
    with pytest.raises(ValueError):
        validate_example(example)


def test_overlength_is_rejected_not_silently_truncated():
    with pytest.raises(ValueError, match="超长"):
        encode_example(demo_example(), max_length=10)


def test_tool_schema_and_result_call_id_are_present_but_not_supervised():
    encoded = encode_example(demo_example())
    context = "".join(token for token, label in zip(encoded.tokens, encoded.labels) if label == -100)
    assert "<tools>" in context and '"required":["metric"]' in context
    assert '"tool_call_id": "call-1"' in context


def test_empty_assistant_target_is_not_a_training_example():
    with pytest.raises(ValueError, match="assistant"):
        validate_example({"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": ""}]})
