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
SOURCE_COMMIT = "4b5df9dcc7f7f3458b593aa816b7a2476d71f8e5"
SOURCE_TREE = "43a629d29b38811bb5dba76c409215ef980ea761"
VALIDATOR_PATH = "scripts/pr_audit.py"
VALIDATOR_SHA256 = "b3ec05cda3d1b45ee4c56bf47c8c9005531938feb43df373b6882d28c6a97d60"
COMPONENTS = {
    "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit.v1.schema.json": "9a9ae9692d05dac276d3dc04c0eff367b8e02bd41fe78033ff4c244167abd95d",
    "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit-observation.v1.schema.json": "5e7ae0ea2d00c5e224a38865b3866b11357a071e71bdc58cfb0d16d6a2a74e7d",
    VALIDATOR_PATH: VALIDATOR_SHA256,
}
FIXTURES = {
    "clean-candidate-dean-4878": {
        "pr": 4878,
        "disposition": "inconclusive",
        "core_root": "sha256:a52aee7bff94c1fff837e7e3cc4f7182bbe0c352e2ffeb85167863ac10bd1c80",
        "core_sha256": "4847737b7ab384c5b35be195b89de28e3aeb11615194c39e30d9264dfcdf9728",
        "observation_root": "sha256:ba34c4c71a517f4e462124c239db89138c35d1cbffe75bc63a55510a67465e69",
        "observation_sha256": "81e76e839a7e59d6ad8361043611d06214b561d4bee14d37fbdb8f0601c9564a",
        "projection_row_root": "sha256:758bcb452311e35b29200301ffed47aa97d697746ab4982b1f05cf8d2aeabd1c",
    },
    "conditional-erdos-427-4884": {
        "pr": 4884,
        "disposition": "inconclusive",
        "core_root": "sha256:69c88a3d5fddbc17f3af161bb2ad1341bf5786418f8d1afdf6212a8ed303dee2",
        "core_sha256": "6d0a0e04f13779755b363f62f4574bfb541f3b666b41f4dca7d86484d92ef764",
        "observation_root": "sha256:d46096bd9bd3f7086f58a1194f0e3c9b242b5a179d7ba09716d22fc4e8fead0a",
        "observation_sha256": "5d4baf2f6a4430951283cc0eb389c458c7084af4fa75e0db46888f9a1b3fda9c",
        "projection_row_root": "sha256:4a14d3e903d2ae3db2ae2d85429aeba4a02744c9a9491215e477518fc3c44ac8",
    },
    "fidelity-erdos-887-1237": {
        "pr": 1237,
        "disposition": "needs_revision",
        "core_root": "sha256:34306610b496d3b5afbe9fe01c3976aa72f62ab133b9877beb26af029535d0af",
        "core_sha256": "fa099da4957d14c4741b1cc49073b28743ddba6f581f3c516bccbc13a28185a2",
        "observation_root": "sha256:3b1aef0936751753cfc9b3fa7dad78e7d49555fe9e67ebb40af05003345bf16e",
        "observation_sha256": "f69ca868835ea6b8ea399e155f70eae5b431d015bcdca3f824a0148f108d83fa",
        "projection_row_root": "sha256:c47dfef85f305d7722f4850243f72a238c7679f42de0517b25d6bb776d088c8b",
    },
    "unavailable-rupert-3959": {
        "pr": 3959,
        "disposition": "unavailable",
        "core_root": "sha256:6e94bebf6986399bc22020ddfd8dc09ae1cc7bd6b714fc49c729b917e200b8c3",
        "core_sha256": "25db11dd10366895078ae515b6050e5480744ac2be19bfd42eb39ebb5e1e4a46",
        "observation_root": "sha256:77b96f3f0e7c87fcb69ef7b52559687ed6051b23d2c33249d647a0cd7c035436",
        "observation_sha256": "5fa29ef0d2a9d408a9ccba91059140ef9ef93954b147f3fd97c79f69e21a6ebe",
        "projection_row_root": "sha256:77cf24fc379a002d109276f96c6c6245406691b15ba2c62b59906761260b6b41",
    },
    "vacuity-erdos-80-4830": {
        "pr": 4830,
        "disposition": "needs_revision",
        "core_root": "sha256:4570618c246c2a6f28d46eab7e0a039f703656a1aaa3a73adc83fdbc009290fc",
        "core_sha256": "0b87f34de077b63e389cb1e968b3726f124b176dd698b37330f31be9bd6c525c",
        "observation_root": "sha256:4d23cb7035ae8586083112d619ffa9367f601a725cb51e340770d93c2283b989",
        "observation_sha256": "d65a6643c6b151581007cf528b6ab51d9cfa8b42642e9972e34053e5a12e9e58",
        "projection_row_root": "sha256:9b1866618bad34aad33228bd612c5d83deb74517f11ea2b23e162e6b3a370598",
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
