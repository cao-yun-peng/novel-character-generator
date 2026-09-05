import hashlib
import json

import pytest

from novel_character_generator.attribution_replay import replay_m2_grounding
from novel_character_generator.errors import ContractValidationError
from novel_character_generator.m2_batch import run_m2_from_m1_run
from novel_character_generator.n3_batch import _load_m2_results
from test_m2_batch import QueueProvider, write_source_run


TEXT = "萧熏儿睫毛修长。少女眼睛美丽。萧炎身形瘦削。"


def prepare(root):
    m1, m2 = root / "m1", root / "m2"
    write_source_run(m1, TEXT)
    run_m2_from_m1_run(document_text=TEXT, source_run_dir=m1, output_dir=m2,
        provider=QueueProvider({"belongs_to_target": []}, {"belongs_to_target": []}))
    return m1, m2


def test_explicit_replay_is_read_only_and_resume_uses_saved_outputs(tmp_path):
    m1, m2 = prepare(tmp_path)
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*.json")}
    output = tmp_path / "replayed"
    for _ in range(2):
        summary = replay_m2_grounding(document_text=TEXT, source_m1_run_dir=m1,
                                     source_m2_run_dir=m2, output_dir=output)
        assert summary["complete"] and summary["new_provider_calls"] == 0
        assert summary["replayed_model_outputs"] == 2
    assert summary["resumed_tasks"] == 2
    assert hashes == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}
    assert len(_load_m2_results(output)) == 1


def test_replay_rejects_wrong_association_before_output_and_n3_rejects_old_policy(tmp_path):
    m1, m2 = prepare(tmp_path)
    path = m2 / "m2-grounded-results.json"
    values = json.loads(path.read_text("utf-8"))
    values[0]["grounded_result"].pop("grounding_policy_version")
    path.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(ContractValidationError, match="policy"):
        _load_m2_results(m2)
    models = m2 / "m2-model-outputs.json"
    records = json.loads(models.read_text("utf-8"))
    records[0]["task_cache_key"] = "0" * 64
    models.write_text(json.dumps(records), encoding="utf-8")
    output = tmp_path / "replayed"
    with pytest.raises(ContractValidationError, match="association"):
        replay_m2_grounding(document_text=TEXT, source_m1_run_dir=m1, source_m2_run_dir=m2, output_dir=output)
    assert not output.exists()
    with pytest.raises(ContractValidationError, match="separate"):
        replay_m2_grounding(document_text=TEXT, source_m1_run_dir=m1, source_m2_run_dir=m2, output_dir=m2)
