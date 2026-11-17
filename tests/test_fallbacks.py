import copy
import json
from pathlib import Path
from src.extractor import SchemaExtractor


def test_reflection_succeeds_second_attempt(tmp_path, valid_invoice):
    bad = copy.deepcopy(valid_invoice)
    bad["currency"] = "CAD"
    prompts = []
    def responder(source, correction):
        prompts.append(correction)
        return json.dumps(bad if len(prompts) == 1 else valid_invoice)
    result = SchemaExtractor(responder=responder, dlq_dir=tmp_path).extract_with_retry("sample invoice")
    assert result.execution_status == "REPAIRED_VIA_REFLECTION"
    assert result.attempts_used == 2
    assert "currency" in prompts[1]
    assert len(result.corrective_prompts) == 1


def test_dlq_hard_failure_after_three_attempts(tmp_path):
    extractor = SchemaExtractor(responder=lambda source, correction: '{"bad": 1}', dlq_dir=tmp_path)
    result = extractor.extract_with_retry("irrecoverable nonsense", max_retries=3)
    assert result.execution_status == "DLQ_FAILED"
    assert result.attempts_used == 3
    assert result.validated_data is None
    saved = json.loads(Path(result.dlq_path).read_text())
    assert saved["status"] == "DLQ_FAILED"
    assert saved["errors"]


def test_disable_reflection_only_one_provider_attempt(tmp_path):
    calls = []
    def responder(source, correction):
        calls.append(1)
        return '{}'
    result = SchemaExtractor(responder=responder, dlq_dir=tmp_path).extract_with_retry(
        "nonsense", max_retries=3, reflection_enabled=False)
    assert result.execution_status == "DLQ_FAILED"
    assert result.attempts_used == 1
    assert len(calls) == 1


def test_reflection_prompt_bounded(tmp_path):
    from src.fallback import build_reflection_prompt
    text = build_reflection_prompt("x" * 20000, "y" * 10000, ValueError("invalid"))
    assert len(text) < 11000


def test_simulated_first_error_then_reflection(tmp_path, valid_invoice):
    result = SchemaExtractor(
        responder=lambda source, correction: json.dumps(valid_invoice), dlq_dir=tmp_path
    ).extract_with_retry("valid sample", simulate_first_error=True)
    assert result.execution_status == "REPAIRED_VIA_REFLECTION"
    assert result.attempts_used == 2
    assert any("Demo injection" in item for item in result.events)
    assert result.corrective_prompts
