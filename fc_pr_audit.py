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
SOURCE_COMMIT = "7ef98fa9394b78cda403a40b994b34bb77dd523a"
SOURCE_TREE = "bf7b593931d9924e25d5c6ff6da5d504c5dcf953"
VALIDATOR_PATH = "scripts/pr_audit.py"
VALIDATOR_SHA256 = "f18be0d9db226e2a5545309287212d49a652d111d032483886f98d4c9f897a66"
COMPONENTS = {
    "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit.v1.schema.json": "b5a1b21bbddb3faa8bc81f07f328ff9c523d0744b41a61492441fffe281722bf",
    "audit/pr-audit-v1/schemas/formal-conjectures.pr-audit-observation.v1.schema.json": "5e7ae0ea2d00c5e224a38865b3866b11357a071e71bdc58cfb0d16d6a2a74e7d",
    VALIDATOR_PATH: VALIDATOR_SHA256,
}
FIXTURES = {
    "clean-candidate-dean-4878": {
        "pr": 4878,
        "disposition": "inconclusive",
        "core_root": "sha256:d65141b5031c4be8f3e4a811f24ea1aea7161a9ba2e1a79bdf05741f89515726",
        "core_sha256": "7a9b16a8b78829d7eda0b61d0d6a1233c4d45808f9d6f9030f1f0108b003cb23",
        "observation_root": "sha256:de8905d8e29026110867f239b70980533e452a195b6471007134d7817fc897a2",
        "observation_sha256": "5f88700f4156f8abd9b732e4e3e5502dc14d0bf56514abebf7f52f4ed7ec1ee3",
        "projection_row_root": "sha256:7832e465c0666a98e93fa7bdf04f3db8818a45b9e831f81c638b82409080a501",
    },
    "conditional-erdos-427-4884": {
        "pr": 4884,
        "disposition": "inconclusive",
        "core_root": "sha256:d8c3bd3cffafe682d642650e5887f9dac11e6834ece33987cada69613ab55c91",
        "core_sha256": "ddc92a9b88d87201d3a7314c301e06b870d0866da9b23ddc272e3ce97ce107cd",
        "observation_root": "sha256:923d3111a338add0e2708ef36f897d14074a4bc61914150cf9881019e103a844",
        "observation_sha256": "0db5936eb77a71708cffc0cd9a1a1145f73bf2eb1ff00a709721afdacf5291af",
        "projection_row_root": "sha256:f5a6bfba6211fb191fcb39f41835a989a85c2f94bc7fd10ca8d11610c0c3e2b9",
    },
    "fidelity-erdos-887-1237": {
        "pr": 1237,
        "disposition": "needs_revision",
        "core_root": "sha256:920395cfd8cbed423777c48307e69332209dae2fc7c20f6f86c24316cacbec78",
        "core_sha256": "31cb417a28a2b03760b96c2a4a6ea4ae4654b2dae9b1a018b68a47b4b277bb34",
        "observation_root": "sha256:97a26bdc8fcd1db002d4e38bff00595b2d6af144b12b2df1dc671a2824d47033",
        "observation_sha256": "b340ac212b699d6cc350225fc76f8b636f8dc2ebbb4ef307301be2be9bbf80d7",
        "projection_row_root": "sha256:94e8cf9d6e2ed7259c398a0b8cc7a2963dc679af92408c045f70b6f983ef70f4",
    },
    "unavailable-rupert-3959": {
        "pr": 3959,
        "disposition": "unavailable",
        "core_root": "sha256:83e98c162649e8591782f46396ec954fd98cb27a2b0f6e1098cb0f6d0ca4db88",
        "core_sha256": "e037df28dfc7a61d5928ba7f79d185397c01d45f2cc94b05a77c325871571a50",
        "observation_root": "sha256:1abe7bf50c325af82a3147d192d2a1ea6c7cf5642f5821e4049b939d0def2719",
        "observation_sha256": "f16d91e9993598fc9fabf2264f0a0527f9fd0df94bcb7203233883f950fef8a8",
        "projection_row_root": "sha256:448538c49200f79181976aa9b6de2b86900dee433608ee5252aa8c939b8da237",
    },
    "vacuity-erdos-80-4830": {
        "pr": 4830,
        "disposition": "needs_revision",
        "core_root": "sha256:4413e916af0182a397000372ab3af223868ee6217bd38b12ad6c3e2887019e37",
        "core_sha256": "82a15f505aac7b189b8dc8959beda3a89ca41cc4ccdde10a1eff67202d4734cd",
        "observation_root": "sha256:74cbd32b7760517bcab78f699584731f23d1569766e6151481a061a60bc91e61",
        "observation_sha256": "f031d928b573f87d23acb69be62275d574ebedb30be8b7eaa75bd3a5ee76a9e8",
        "projection_row_root": "sha256:98978b0f17a958ffcc23ffdde8c7113726e12e0981c2e606f7762bc9875743f5",
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
