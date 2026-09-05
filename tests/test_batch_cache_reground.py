import json

import pytest

from novel_character_generator.errors import ContractValidationError
from novel_character_generator.m1_batch import run_m1_document
from novel_character_generator.m2_batch import run_m2_from_m1_run
from test_m1_batch import EchoEvidenceProvider
from test_m2_batch import QueueProvider, FailIfCalledProvider, write_source_run


def test_m1_resume_revalidates_model_output_instead_of_using_cached_grounding(tmp_path):
    run_m1_document(document_text="abcdefgh", provider=EchoEvidenceProvider(),
                    output_dir=tmp_path, chunk_size=8, overlap_characters=0)
    path = next((tmp_path / "chunks").glob("*.json"))
    record = json.loads(path.read_text("utf-8"))
    record["grounded_packet"] = {"corrupt": "must not be trusted"}
    path.write_text(json.dumps(record), encoding="utf-8")
    provider = EchoEvidenceProvider()
    result = run_m1_document(document_text="abcdefgh", provider=provider,
                             output_dir=tmp_path, chunk_size=8, overlap_characters=0)
    assert result["resumed_chunks"] == 1 and provider.calls == 0
    assert "grounded_mentions" in json.loads(path.read_text("utf-8"))["grounded_packet"]


def test_m1_model_change_fails_before_missing_chunk_call(tmp_path):
    run_m1_document(document_text="abcdefgh", provider=EchoEvidenceProvider(),
                    output_dir=tmp_path, chunk_size=4, overlap_characters=0)
    first, _ = sorted((tmp_path / "chunks").glob("*.json"))
    first.unlink()
    provider = EchoEvidenceProvider()
    provider.cache_identity = {"provider": "new-model"}
    with pytest.raises(ContractValidationError, match="fingerprint"):
        run_m1_document(document_text="abcdefgh", provider=provider,
                        output_dir=tmp_path, chunk_size=4, overlap_characters=0)
    assert provider.calls == 0


def test_m2_resume_regrounds_and_model_change_is_rejected(tmp_path):
    text = "萧熏儿睫毛修长。少女眼睛美丽。萧炎身形瘦削。"
    source, output = tmp_path / "source", tmp_path / "output"
    write_source_run(source, text)
    run_m2_from_m1_run(document_text=text, source_run_dir=source,
                       provider=QueueProvider({"belongs_to_target": []}, {"belongs_to_target": []}),
                       output_dir=output)
    paths = sorted((output / "tasks").glob("*.json"))
    record = json.loads(paths[0].read_text("utf-8"))
    record["grounded_result"] = {"corrupt": True}
    paths[0].write_text(json.dumps(record), encoding="utf-8")
    summary = run_m2_from_m1_run(document_text=text, source_run_dir=source,
                                 provider=FailIfCalledProvider(), output_dir=output)
    assert summary["resumed_tasks"] == 2
    assert json.loads(paths[0].read_text("utf-8"))["grounded_result"]["grounded_belongs_to_target"] == []
    paths[0].unlink()
    changed = QueueProvider({"belongs_to_target": []})
    changed.cache_identity = {"provider": "changed-model"}
    with pytest.raises(ContractValidationError, match="fingerprint"):
        run_m2_from_m1_run(document_text=text, source_run_dir=source, provider=changed, output_dir=output)
    assert changed.requests == []
