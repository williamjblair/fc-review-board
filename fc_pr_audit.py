#!/usr/bin/env python3
"""Project the exact FC per-PR audit packet into a neutral board feed.

The source checkout is a public, commit-pinned distribution of advisory audit
records.  This adapter validates the upstream records with the upstream
validator, verifies their framed bytes and pair bindings, then emits a small
PR-number keyed projection.  It never executes a pull-request checkout and it
does not infer approval, merge readiness, or mathematical truth.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import unicodedata
from pathlib import Path
from types import ModuleType
from typing import Any


SOURCE_REPOSITORY = "https://github.com/williamjblair/formal-conjectures"
SOURCE_COMMIT = "50fb575fadfc710f2da66cba1d3909429f9ba25e"
SOURCE_TREE = "7213fa92375028e13797fc89f2cc300fc0568869"
VALIDATOR_PATH = "scripts/pr_audit.py"
VALIDATOR_SHA256 = "2c41ae2bd4fed8f9748ebf8c57630673ca2eb7ea3c690525ea292641590c3098"
COMPONENTS = {
    "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit.v1.schema.json": "b581b8970673fe90b749a54a0b2df9f0ea5d6221f90f49f67f2f03602b2efc45",
    "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit-observation.v1.schema.json": "5e7ae0ea2d00c5e224a38865b3866b11357a071e71bdc58cfb0d16d6a2a74e7d",
    VALIDATOR_PATH: VALIDATOR_SHA256,
}
FIXTURES = {
    "clean-source-faithful-min-modulus-4829": {
        "pr": 4829,
        "disposition": "clean",
        "core_root": "sha256:7a6318a1874a297e7003f20cf005f46285a6e92ab49571d95996fdbccd3a197f",
        "core_sha256": "feaf8dd36c7bc4361c67af09bea9af7f20051ee2f933d4234ffda5715be91f52",
        "observation_root": "sha256:4e1cb38e1937b8dc9010f219ff28b80aa8ebf2d7c9ffa94ffa2a8b46686c2892",
        "observation_sha256": "51e8597d930a90ae23f4379dd7ca67d23b173fe36f8b7874b2eb436aeb968c28",
        "projection_row_root": "sha256:57ee453b1401e5029e94facbc92d3353ff9ce4e2d4df047a830930d043ea4abc",
    },
    "conditional-erdos-427-4884": {
        "pr": 4884,
        "disposition": "inconclusive",
        "core_root": "sha256:e112acd89b801c121d8aebebd4756a481a9db7c2e9790a3a1fd19802b39ab37e",
        "core_sha256": "036d381ec4ede898da1d5b4b5ccb3b44e493809dfd971a0f78864db63219dbd5",
        "observation_root": "sha256:8570f2d6ac166e348d59bf550c365f35c587392ebe95e47314e36d1a8e5ba4e4",
        "observation_sha256": "0ec64c275820e858f917c34ddf2980bceb33c5a6b5252ddc9775a428e89136cb",
        "projection_row_root": "sha256:6a0ea7ea0d4c81d4043968cd684e46ee948f5cb2330f0fe4fcdddcf154f12fa0",
    },
    "fidelity-erdos-887-1237": {
        "pr": 1237,
        "disposition": "needs_revision",
        "core_root": "sha256:7b7414a06990c4f6ba41facaba6e6b9795da4890214caa5f8bc8ff85fada63c9",
        "core_sha256": "f5ab5dc0d3721b067fcdf46ea3664b12101b7999a484a09dc0ecd8accf4b34ae",
        "observation_root": "sha256:d5e1d4eb96e041905d0df3c7eb89aa4c28e0aa350c76aa2225089e0724266026",
        "observation_sha256": "2e380f07fddeb54c64bf33120930cdcfdddf8dbdd54e243258a6d25e90e2dc63",
        "projection_row_root": "sha256:f4dac505ea0538927232bcd4a327cfda68d134f3bdb873a899d388e8ac90c2b8",
    },
    "unavailable-rupert-3959": {
        "pr": 3959,
        "disposition": "unavailable",
        "core_root": "sha256:3213c7729a168255d79ca0956137ac89e999b82dbef66737599c5a4a1f05a77f",
        "core_sha256": "73c2b98ae0def8759b2948eb928d4c8412e67ab5541085149568c6b56c7c4f73",
        "observation_root": "sha256:58e97a1ee066aa947fd6a8222f865d56495506b6368233f6dc5c51e3f981ea41",
        "observation_sha256": "aecc170adba2ff0dc964ee4d0e165b91a5d36f2048290666f720b6c3054c44c8",
        "projection_row_root": "sha256:e46f354d88971c4fbf9a663319cdc96b3b4680fbfc80de36bfe0cd442841814b",
    },
    "vacuity-erdos-80-4830": {
        "pr": 4830,
        "disposition": "needs_revision",
        "core_root": "sha256:f79e447d1fe95944bf2e79c5d8f6793e861b45b821b7b7df3da3f6132e1e8854",
        "core_sha256": "da600a4bfb45749018a04d99592bc0a678da0f73dcdacd5705e5407d4998f233",
        "observation_root": "sha256:4aee375b2b6ad3501824013b978a60f08e77b821c05ba9e3c21de9d0d797024c",
        "observation_sha256": "8588ef0cd07a45e5b96723f932cab77104276c648323f5f25636875f4dce17c4",
        "projection_row_root": "sha256:ae6fc308fbe15a19f74e34a47110910220d2598c8609baa5509d6c772d5ae101",
    },
}
SCHEMA = "fc-review-board.pr-audit-projection.v1"
NONCLAIMS = [
    "not_an_acceptance_or_merge_decision",
    "not_a_claim_of_mathematical_truth",
    "not_a_repository_decision_or_standing",
    "not_an_independent_review_board_verdict",
]


class ProjectionError(ValueError):
    pass


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    """Return JCS bytes for this projection's integer-only I-JSON subset."""
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int) and not isinstance(value, bool):
        if not -(2**53 - 1) <= value <= 2**53 - 1:
            raise ProjectionError("integer outside canonical profile")
        return str(value).encode()
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise ProjectionError("non-NFC string in projection")
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    if isinstance(value, list):
        return b"[" + b",".join(_canonical(item) for item in value) + b"]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ProjectionError("projection object key is not a string")
        keys = sorted(value, key=lambda key: key.encode("utf-16-be"))
        return (
            b"{"
            + b",".join(_canonical(key) + b":" + _canonical(value[key]) for key in keys)
            + b"}"
        )
    raise ProjectionError("unsupported projection value")


def _content_root(value: Any) -> str:
    return "sha256:" + _sha256(_canonical(value))


def _git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def _assert_source(source: Path) -> None:
    if _git(source, "rev-parse", "HEAD") != SOURCE_COMMIT:
        raise ProjectionError("FC audit source commit does not match the pinned commit")
    if _git(source, "rev-parse", "HEAD^{tree}") != SOURCE_TREE:
        raise ProjectionError("FC audit source tree does not match the pinned tree")
    for relative, expected in COMPONENTS.items():
        path = source / relative
        if (
            not path.is_file()
            or path.is_symlink()
            or _sha256(path.read_bytes()) != expected
        ):
            raise ProjectionError(f"FC audit component drift: {relative}")


def _load_validator(source: Path) -> ModuleType:
    path = source / VALIDATOR_PATH
    spec = importlib.util.spec_from_file_location("fc_pinned_pr_audit", path)
    if spec is None or spec.loader is None:
        raise ProjectionError("cannot load the pinned FC audit validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(
    source: Path, validator: ModuleType, fixture: str, expected: dict[str, Any]
) -> dict[str, Any]:
    directory = source / "audit/pr-audit-v1/fixtures" / fixture
    core_path = directory / "expected-core.json"
    observation_path = directory / "expected-observation.json"
    core_raw = core_path.read_bytes()
    observation_raw = observation_path.read_bytes()
    if (
        _sha256(core_raw) != expected["core_sha256"]
        or _sha256(observation_raw) != expected["observation_sha256"]
    ):
        raise ProjectionError(f"FC audit framed bytes drift: {fixture}")
    core = validator.validate_core(
        validator.parse_json_bytes(core_raw, label=str(core_path))
    )
    observation = validator.validate_observation(
        validator.parse_json_bytes(observation_raw, label=str(observation_path))
    )
    pr = core["repository"]["pull_request"]
    disposition = core["disposition"]["advisory"]
    if pr["number"] != expected["pr"] or disposition != expected["disposition"]:
        raise ProjectionError(f"FC audit projected outcome drift: {fixture}")
    if (
        core["root"] != expected["core_root"]
        or observation["root"] != expected["observation_root"]
    ):
        raise ProjectionError(f"FC audit internal root drift: {fixture}")
    if observation["core"] != {
        "root": core["root"],
        "sha256": f"sha256:{expected['core_sha256']}",
    }:
        raise ProjectionError(f"FC audit core/observation pair mismatch: {fixture}")
    if observation["pull_request"]["number"] != pr["number"]:
        raise ProjectionError(f"FC audit pull-request pair mismatch: {fixture}")
    checks = [
        {
            "id": check["id"],
            "property": check["property"],
            "outcome": check["outcome"],
            "severity": check["severity"],
        }
        for check in core["checks"]
    ]
    return {
        "fixture": fixture,
        "source_url": (
            f"{SOURCE_REPOSITORY}/tree/{SOURCE_COMMIT}/"
            f"audit/pr-audit-v1/fixtures/{fixture}"
        ),
        "pull_request": {"number": pr["number"], "url": pr["url"]},
        "advisory_disposition": disposition,
        "basis_check_ids": core["disposition"]["basis_check_ids"],
        "checks": checks,
        "core": {"root": core["root"], "sha256": f"sha256:{expected['core_sha256']}"},
        "observation": {
            "root": observation["root"],
            "sha256": f"sha256:{expected['observation_sha256']}",
        },
        "nonclaims": sorted(set(core["disposition"]["nonclaims"] + NONCLAIMS)),
    }


def build_projection(source: Path) -> dict[str, Any]:
    source = source.resolve(strict=True)
    _assert_source(source)
    validator = _load_validator(source)
    rows = [
        _record(source, validator, fixture, expected)
        for fixture, expected in FIXTURES.items()
    ]
    rows.sort(key=lambda row: row["pull_request"]["number"])
    if len({row["pull_request"]["number"] for row in rows}) != len(rows):
        raise ProjectionError(
            "FC audit projection has duplicate pull-request identities"
        )
    without_root = {
        "schema": SCHEMA,
        "authority_effect": "none",
        "source": {
            "repository": SOURCE_REPOSITORY,
            "commit": SOURCE_COMMIT,
            "tree": SOURCE_TREE,
            "validator_sha256": f"sha256:{VALIDATOR_SHA256}",
        },
        "coverage": {"complete": True, "expected": 5, "observed": len(rows)},
        "rows": rows,
        "nonclaims": NONCLAIMS,
    }
    return {**without_root, "root": _content_root(without_root)}


def validate_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "authority_effect",
        "source",
        "coverage",
        "rows",
        "nonclaims",
        "root",
    }:
        raise ProjectionError("invalid FC audit projection shape")
    if value["schema"] != SCHEMA or value["authority_effect"] != "none":
        raise ProjectionError("invalid FC audit projection boundary")
    source = value["source"]
    if source != {
        "repository": SOURCE_REPOSITORY,
        "commit": SOURCE_COMMIT,
        "tree": SOURCE_TREE,
        "validator_sha256": f"sha256:{VALIDATOR_SHA256}",
    }:
        raise ProjectionError("invalid FC audit projection source")
    rows = value["rows"]
    if not isinstance(rows, list) or len(rows) != 5:
        raise ProjectionError("invalid FC audit projection coverage")
    numbers = [row.get("pull_request", {}).get("number") for row in rows]
    if numbers != sorted(FIXTURES[name]["pr"] for name in FIXTURES) or len(
        numbers
    ) != len(set(numbers)):
        raise ProjectionError("invalid FC audit projection inventory")
    expected_by_pr = {item["pr"]: (name, item) for name, item in FIXTURES.items()}
    for row in rows:
        number = row["pull_request"]["number"]
        fixture, expected = expected_by_pr[number]
        if set(row) != {
            "fixture",
            "source_url",
            "pull_request",
            "advisory_disposition",
            "basis_check_ids",
            "checks",
            "core",
            "observation",
            "nonclaims",
        }:
            raise ProjectionError("invalid FC audit projection row shape")
        if row["fixture"] != fixture or row["source_url"] != (
            f"{SOURCE_REPOSITORY}/tree/{SOURCE_COMMIT}/"
            f"audit/pr-audit-v1/fixtures/{fixture}"
        ):
            raise ProjectionError("invalid FC audit projection fixture identity")
        if row["pull_request"] != {
            "number": number,
            "url": f"https://github.com/google-deepmind/formal-conjectures/pull/{number}",
        }:
            raise ProjectionError("invalid FC audit projection pull-request identity")
        if row.get("advisory_disposition") != expected["disposition"]:
            raise ProjectionError("invalid FC audit projection outcome")
        if row["core"] != {
            "root": expected["core_root"],
            "sha256": f"sha256:{expected['core_sha256']}",
        } or row["observation"] != {
            "root": expected["observation_root"],
            "sha256": f"sha256:{expected['observation_sha256']}",
        }:
            raise ProjectionError("invalid FC audit projection record binding")
        checks = row["checks"]
        if (
            not isinstance(checks, list)
            or not checks
            or any(
                not isinstance(check, dict)
                or set(check) != {"id", "property", "outcome", "severity"}
                or not all(
                    isinstance(check[field], str) and check[field] for field in check
                )
                or check["outcome"]
                not in {"pass", "fail", "inconclusive", "error", "unavailable"}
                for check in checks
            )
        ):
            raise ProjectionError("invalid FC audit projection checks")
        check_ids = [check["id"] for check in checks]
        if len(check_ids) != len(set(check_ids)):
            raise ProjectionError("invalid FC audit projection duplicate check")
        basis = row["basis_check_ids"]
        if (
            not isinstance(basis, list)
            or not basis
            or not set(basis).issubset(set(check_ids))
        ):
            raise ProjectionError("invalid FC audit projection disposition basis")
        if not set(NONCLAIMS).issubset(set(row.get("nonclaims", []))):
            raise ProjectionError("invalid FC audit projection nonclaims")
        if _content_root(row) != expected["projection_row_root"]:
            raise ProjectionError("invalid FC audit projection row root")
    coverage = value["coverage"]
    if coverage != {"complete": True, "expected": 5, "observed": 5}:
        raise ProjectionError("invalid FC audit projection completeness")
    if value["nonclaims"] != NONCLAIMS:
        raise ProjectionError("invalid FC audit projection top-level nonclaims")
    without_root = {key: item for key, item in value.items() if key != "root"}
    if value["root"] != _content_root(without_root):
        raise ProjectionError("invalid FC audit projection root")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("pr_audits.json"))
    args = parser.parse_args()
    projection = build_projection(args.source)
    validate_projection(projection)
    args.output.write_text(
        json.dumps(
            projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    )
    print(
        json.dumps(
            {"ok": True, "schema": SCHEMA, "rows": 5, "root": projection["root"]}
        )
    )


if __name__ == "__main__":
    main()
