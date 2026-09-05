import json
from pathlib import Path
from unittest.mock import patch

import pytest

from novel_character_generator.errors import ContractValidationError
from novel_character_generator.identity import build_identity_preparation
from novel_character_generator.identity_batch import run_document_identity
from novel_character_generator.text import SourceSpan
from test_identity import _node, _document_nodes


@pytest.mark.parametrize("change", ["model", "missing_fingerprint"])
def test_identity_preflights_later_cache_before_calling_missing_task(tmp_path, change):
    text = "萧炎甲。萧炎乙。萧炎丙。"
    nodes = [_node(index=i + 1, label="萧炎", text=text,
                   context_span=SourceSpan(i * 4, i * 4 + 3)) for i in range(3)]
    preparation = build_identity_preparation(
        local_nodes=_document_nodes(text, *nodes), document_text=text,
    )
    assert len(preparation.envelopes) >= 2

    class Provider:
        cache_identity = {"model": "baseline"}

        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            return {"identity_relation": "uncertain", "label_relation": None,
                    "identity_evidence_quotes": []}

    arguments = dict(document_text=text, source_n2_packets_file=Path("n2.json"),
                     source_n3_run_dir=Path("n3"), document_evidence_file=Path("facts.json"),
                     output_dir=tmp_path)
    with patch("novel_character_generator.identity_batch._load_preparation",
               return_value=(preparation, {})):
        assert run_document_identity(provider=Provider(), **arguments)["complete"]
        paths = sorted((tmp_path / "tasks").glob("*.json"),
                       key=lambda p: json.loads(p.read_text("utf-8"))["task_index"])
        paths[0].unlink()
        provider = Provider()
        if change == "model":
            provider.cache_identity = {"model": "replacement"}
        else:
            record = json.loads(paths[-1].read_text("utf-8"))
            record.pop("request_fingerprint")
            paths[-1].write_text(json.dumps(record), encoding="utf-8")
        before = paths[-1].read_bytes()
        with pytest.raises(ContractValidationError, match="fingerprint"):
            run_document_identity(provider=provider, **arguments)
        assert provider.calls == 0
        assert paths[-1].read_bytes() == before
