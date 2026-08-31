from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .chunking import build_document_chunk_manifest
from .document_evidence import run_document_evidence_aggregation
from .errors import ContractValidationError, ProviderError
from .grounding import ground_m1_result
from .identity_batch import prepare_document_identity, run_document_identity
from .m1 import M1OrchestrationEnvelope, M1Orchestrator
from .m1_batch import run_m1_document
from .m2_batch import run_m2_from_m1_run
from .n3_batch import run_n3_promotion_from_m2_run
from .providers import DeepSeekCallTrace, DeepSeekProvider
from .promotion_replay import replay_promotion_grounding


def _read_utf8_text(path: Path) -> str:
    """Decode UTF-8 without Python's universal-newline normalization."""
    with path.open("r", encoding="utf-8", newline="") as source:
        return source.read()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="novel_character_generator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe = subparsers.add_parser(
        "probe-deepseek-m1",
        help="Run one explicit DeepSeek M1 call and print the grounded packet.",
    )
    source = probe.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="A short UTF-8 Chunk supplied on the command line.")
    source.add_argument("--input-file", type=Path, help="A UTF-8 file containing exactly one Chunk.")
    probe.add_argument("--source-version", default="manual-probe-v1")
    probe.add_argument("--show-trace", action="store_true")
    batch = subparsers.add_parser(
        "run-deepseek-m1",
        help="Run resumable DeepSeek M1 extraction over a UTF-8 document.",
    )
    batch.add_argument("--input-file", type=Path, required=True)
    batch.add_argument("--output-dir", type=Path, required=True)
    batch.add_argument("--chunk-size", type=int, default=8000)
    batch.add_argument("--overlap-characters", type=int, default=500)
    batch.add_argument("--source-version")
    batch.add_argument("--show-progress", action="store_true")
    m2_batch = subparsers.add_parser(
        "run-deepseek-m2-from-m1-run",
        help="Replay current N2 from a saved M1 run and execute resumable M2 attribution.",
    )
    m2_batch.add_argument("--input-file", type=Path, required=True)
    m2_batch.add_argument("--source-run-dir", type=Path, required=True)
    m2_batch.add_argument("--output-dir", type=Path, required=True)
    m2_batch.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Optional local dotenv file; only DEEPSEEK_* names are loaded and existing env wins.",
    )
    m2_batch.add_argument("--show-progress", action="store_true")
    n3_batch = subparsers.add_parser(
        "run-deepseek-n3-promotion-from-m2-run",
        help="Replay N2, resolve N3, and execute resumable remaining-describe promotion.",
    )
    n3_batch.add_argument("--input-file", type=Path, required=True)
    n3_batch.add_argument("--source-m1-run-dir", type=Path, required=True)
    n3_batch.add_argument("--source-m2-run-dir", type=Path, required=True)
    n3_batch.add_argument("--output-dir", type=Path, required=True)
    n3_batch.add_argument("--env-file", type=Path, default=Path(".env"))
    n3_batch.add_argument("--show-progress", action="store_true")
    document = subparsers.add_parser(
        "build-document-character-evidence",
        help="Convert grounded Chunk facts to absolute document spans and deduplicate overlap copies.",
    )
    document.add_argument("--input-file", type=Path, required=True)
    document.add_argument("--source-m1-run-dir", type=Path, required=True)
    document.add_argument("--source-m2-run-dir", type=Path, required=True)
    document.add_argument("--source-n3-run-dir", type=Path, required=True)
    document.add_argument("--output-file", type=Path, required=True)
    replay = subparsers.add_parser(
        "replay-promotion-grounding",
        help="Re-ground saved promotion model outputs under the current deterministic policy.",
    )
    replay.add_argument("--source-run-dir", type=Path, required=True)
    replay.add_argument("--output-dir", type=Path, required=True)
    identity = subparsers.add_parser(
        "prepare-document-identity",
        help="Build local identity nodes and bounded M3 tasks without calling a Provider.",
    )
    identity.add_argument("--input-file", type=Path, required=True)
    identity.add_argument("--source-n2-packets-file", type=Path, required=True)
    identity.add_argument("--source-n3-run-dir", type=Path, required=True)
    identity.add_argument("--document-evidence-file", type=Path, required=True)
    identity.add_argument("--output-dir", type=Path, required=True)
    identity.add_argument("--max-candidates-per-node", type=int, default=2)
    identity.add_argument("--context-radius", type=int, default=240)
    identity.add_argument("--max-contexts-per-node", type=int, default=4)
    identity.add_argument("--max-bridge-characters", type=int, default=1200)
    identity_run = subparsers.add_parser(
        "run-deepseek-document-identity",
        help="Execute resumable M3 identity decisions and build the document character registry.",
    )
    identity_run.add_argument("--input-file", type=Path, required=True)
    identity_run.add_argument("--source-n2-packets-file", type=Path, required=True)
    identity_run.add_argument("--source-n3-run-dir", type=Path, required=True)
    identity_run.add_argument("--document-evidence-file", type=Path, required=True)
    identity_run.add_argument("--output-dir", type=Path, required=True)
    identity_run.add_argument("--env-file", type=Path, default=Path(".env"))
    identity_run.add_argument("--max-candidates-per-node", type=int, default=2)
    identity_run.add_argument("--context-radius", type=int, default=240)
    identity_run.add_argument("--max-contexts-per-node", type=int, default=4)
    identity_run.add_argument("--max-bridge-characters", type=int, default=1200)
    identity_run.add_argument("--show-progress", action="store_true")
    return parser


def _read_probe_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    return _read_utf8_text(args.input_file)


def _probe_deepseek_m1(args: argparse.Namespace) -> int:
    text = _read_probe_text(args)
    traces: list[DeepSeekCallTrace] = []
    provider = DeepSeekProvider.from_env(trace_sink=traces.append)
    manifest = build_document_chunk_manifest(
        text,
        source_document_version_id=args.source_version,
        chunk_size=len(text),
        overlap_characters=0,
        chunking_policy_version="manual-probe-single-chunk-v1",
    )
    envelope = M1OrchestrationEnvelope.from_manifest_entry(
        source_document_version_id=manifest.source_document_version_id,
        chunking_policy_version=manifest.chunking_policy_version,
        entry=manifest.chunks[0],
        document_text=text,
    )
    bound = M1Orchestrator(provider).run(envelope)
    grounded = ground_m1_result(bound)
    print(json.dumps(grounded.to_packet_dict(), ensure_ascii=False, indent=2))
    if args.show_trace and traces:
        print(
            json.dumps(traces[-1].to_dict(), ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
    return 0


def _run_deepseek_m1(args: argparse.Namespace) -> int:
    document_text = _read_utf8_text(args.input_file)
    traces: list[DeepSeekCallTrace] = []
    provider = DeepSeekProvider.from_env(trace_sink=traces.append)
    summary = run_m1_document(
        document_text=document_text,
        provider=provider,
        output_dir=args.output_dir,
        chunk_size=args.chunk_size,
        overlap_characters=args.overlap_characters,
        source_document_version_id=args.source_version,
        traces=traces,
        progress=(lambda message: print(message, file=sys.stderr)) if args.show_progress else None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["complete"] else 1


def _load_deepseek_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ContractValidationError(f"invalid env file assignment at line {line_number}")
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name.startswith("DEEPSEEK_"):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def _run_deepseek_m2_from_m1_run(args: argparse.Namespace) -> int:
    document_text = _read_utf8_text(args.input_file)
    _load_deepseek_env_file(args.env_file)
    traces: list[DeepSeekCallTrace] = []
    provider = DeepSeekProvider.from_env(trace_sink=traces.append)
    summary = run_m2_from_m1_run(
        document_text=document_text,
        source_run_dir=args.source_run_dir,
        provider=provider,
        output_dir=args.output_dir,
        traces=traces,
        progress=(lambda message: print(message, file=sys.stderr)) if args.show_progress else None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["complete"] else 1


def _run_deepseek_n3_promotion_from_m2_run(args: argparse.Namespace) -> int:
    document_text = _read_utf8_text(args.input_file)
    _load_deepseek_env_file(args.env_file)
    traces: list[DeepSeekCallTrace] = []
    provider = DeepSeekProvider.from_env(trace_sink=traces.append)
    summary = run_n3_promotion_from_m2_run(
        document_text=document_text,
        source_m1_run_dir=args.source_m1_run_dir,
        source_m2_run_dir=args.source_m2_run_dir,
        provider=provider,
        output_dir=args.output_dir,
        traces=traces,
        progress=(lambda message: print(message, file=sys.stderr)) if args.show_progress else None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["complete"] else 1


def _build_document_character_evidence(args: argparse.Namespace) -> int:
    summary = run_document_evidence_aggregation(
        document_text=_read_utf8_text(args.input_file),
        source_m1_run_dir=args.source_m1_run_dir,
        source_m2_run_dir=args.source_m2_run_dir,
        source_n3_run_dir=args.source_n3_run_dir,
        output_file=args.output_file,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _replay_promotion_grounding(args: argparse.Namespace) -> int:
    summary = replay_promotion_grounding(
        source_run_dir=args.source_run_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _prepare_document_identity(args: argparse.Namespace) -> int:
    summary = prepare_document_identity(
        document_text=_read_utf8_text(args.input_file),
        source_n2_packets_file=args.source_n2_packets_file,
        source_n3_run_dir=args.source_n3_run_dir,
        document_evidence_file=args.document_evidence_file,
        output_dir=args.output_dir,
        max_candidates_per_node=args.max_candidates_per_node,
        context_radius=args.context_radius,
        max_contexts_per_node=args.max_contexts_per_node,
        max_bridge_characters=args.max_bridge_characters,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _run_deepseek_document_identity(args: argparse.Namespace) -> int:
    _load_deepseek_env_file(args.env_file)
    traces: list[DeepSeekCallTrace] = []
    provider = DeepSeekProvider.from_env(trace_sink=traces.append)
    summary = run_document_identity(
        document_text=_read_utf8_text(args.input_file),
        source_n2_packets_file=args.source_n2_packets_file,
        source_n3_run_dir=args.source_n3_run_dir,
        document_evidence_file=args.document_evidence_file,
        provider=provider,
        output_dir=args.output_dir,
        max_candidates_per_node=args.max_candidates_per_node,
        context_radius=args.context_radius,
        max_contexts_per_node=args.max_contexts_per_node,
        max_bridge_characters=args.max_bridge_characters,
        traces=traces,
        progress=(lambda message: print(message, file=sys.stderr)) if args.show_progress else None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["complete"] else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "probe-deepseek-m1":
            return _probe_deepseek_m1(args)
        if args.command == "run-deepseek-m1":
            return _run_deepseek_m1(args)
        if args.command == "run-deepseek-m2-from-m1-run":
            return _run_deepseek_m2_from_m1_run(args)
        if args.command == "run-deepseek-n3-promotion-from-m2-run":
            return _run_deepseek_n3_promotion_from_m2_run(args)
        if args.command == "build-document-character-evidence":
            return _build_document_character_evidence(args)
        if args.command == "replay-promotion-grounding":
            return _replay_promotion_grounding(args)
        if args.command == "prepare-document-identity":
            return _prepare_document_identity(args)
        if args.command == "run-deepseek-document-identity":
            return _run_deepseek_document_identity(args)
    except (OSError, ContractValidationError, ProviderError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
