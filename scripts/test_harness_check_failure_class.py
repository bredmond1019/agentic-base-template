#!/usr/bin/env python3
"""Fixture test for `failureClass` on a harness check (BT.ticket.harness-check-failure-class).

Validates check-shaped fixtures against `$defs.check` in
`.claude/workflows/harness.schema.json` — read directly off disk, never re-typed — using a
small hand-rolled JSON-Schema subset validator. `jsonschema` is NOT installed anywhere in
this fleet (see `scripts/check_block_records.py`'s own docstring on the same point): a
validator that imports it validates nothing and reports false success. The subset covers
exactly what `$defs.check` and `$defs.rule` use: `type`, `properties`,
`additionalProperties: false`, `required`, `enum`, `items`, `$ref`, `pattern`, `minLength`,
and the `allOf`/`if`/`then` conditional-required blocks.

RED-FIRST (task 1 of this spec): run against the UNMODIFIED schema, where `failureClass` does
not yet exist in `$defs.check.properties`. `valid_fixable` and `valid_escalate` are expected to
fail here (additionalProperties: false refuses the unknown key) — that failure, captured
verbatim, is the `observed_red.evidence` task 4 registers. Task 2 adds the property; re-running
this script afterwards must exit 0.

Six named cases:
  - valid_fixable            a check with failureClass: "fixable" validates
  - valid_escalate           a check with failureClass: "escalate" validates
  - absent_is_valid          a check with no failureClass key validates
  - out_of_enum_refused      a check with failureClass: "retry" is refused
  - misspelled_key_refused   a check with failureclass (wrong case) is refused
  - own_harness_still_validates   adding failureClass does not regress this repo's own
    planning/harness.json or the scaffold harness stub — every already-live check with a
    failureClass value would still be one of the schema's enum values, and none currently
    sets the key (see that case's own docstring for why this is narrower than full
    $defs.check conformance)

Run: python3 scripts/test_harness_check_failure_class.py
"""

from __future__ import annotations

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(REPO_ROOT, ".claude", "workflows", "harness.schema.json")
OWN_HARNESS_PATH = os.path.join(REPO_ROOT, "planning", "harness.json")
SCAFFOLD_HARNESS_PATH = os.path.join(REPO_ROOT, "scaffold", "planning", "harness.json")


class SchemaError(Exception):
    """Raised (and caught) when a fixture fails validation. Message is the human-readable
    reason, mirroring what a real validator would report."""


def load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


_PY_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
}


def _check_type(value, expected_type: str, path: str) -> None:
    py_type = _PY_TYPES.get(expected_type)
    if py_type is None:
        return
    # bool is a subclass of int in Python; JSON Schema treats them as distinct. Only matters
    # for "integer"/"number", where a real bool value should not silently pass.
    if expected_type in ("integer", "number") and isinstance(value, bool):
        raise SchemaError(f"{path}: expected {expected_type}, got boolean")
    if not isinstance(value, py_type):
        raise SchemaError(f"{path}: expected {expected_type}, got {type(value).__name__}")


def resolve_ref(ref: str, root_schema: dict) -> dict:
    if not ref.startswith("#/"):
        raise SchemaError(f"unsupported $ref: {ref}")
    node = root_schema
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate(value, schema: dict, root_schema: dict, path: str = "$") -> None:
    """Validate `value` against `schema` (a subset of draft-07), raising SchemaError on the
    first violation. `root_schema` is the whole document, needed to resolve `$ref`. Always
    strict (`additionalProperties: false` enforced) — the only fixtures this validates are
    the five synthetic ones this script constructs itself; the sixth case
    (`own_harness_still_validates`) deliberately does not route real, already-committed
    check objects through this strict path — see that case's own docstring for why."""
    if "$ref" in schema:
        validate(value, resolve_ref(schema["$ref"], root_schema), root_schema, path)
        return

    if "enum" in schema and value not in schema["enum"]:
        raise SchemaError(f"{path}: {value!r} is not one of {schema['enum']!r}")

    if "type" in schema:
        _check_type(value, schema["type"], path)

    if "pattern" in schema and isinstance(value, str):
        import re

        if not re.match(schema["pattern"], value):
            raise SchemaError(f"{path}: {value!r} does not match pattern {schema['pattern']!r}")

    if "minLength" in schema and isinstance(value, str):
        if len(value) < schema["minLength"]:
            raise SchemaError(f"{path}: length {len(value)} < minLength {schema['minLength']}")

    if isinstance(value, dict) and schema.get("type") == "object":
        properties = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                raise SchemaError(f"{path}: missing required property {req!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    raise SchemaError(f"{path}: additional property {key!r} not permitted")
        for key, subvalue in value.items():
            if key in properties:
                validate(subvalue, properties[key], root_schema, f"{path}.{key}")

    if isinstance(value, list) and schema.get("type") == "array" and "items" in schema:
        for i, item in enumerate(value):
            validate(item, schema["items"], root_schema, f"{path}[{i}]")

    for clause in schema.get("allOf", []):
        if "if" in clause:
            if _matches(value, clause["if"]):
                validate(value, clause.get("then", {}), root_schema, path)
        else:
            validate(value, clause, root_schema, path)


def _matches(value, if_schema: dict) -> bool:
    """Best-effort evaluation of a draft-07 `if` clause, restricted to the shapes
    `$defs.check.allOf` actually uses: `properties.<k>.const` plus an optional
    `required: [<k>]`, or `not: {required: [...]}` / `anyOf: [...]`."""
    if "not" in if_schema:
        return not _matches(value, if_schema["not"])
    if "anyOf" in if_schema:
        return any(_matches(value, sub) for sub in if_schema["anyOf"])
    for req in if_schema.get("required", []):
        if not isinstance(value, dict) or req not in value:
            return False
    for key, subschema in if_schema.get("properties", {}).items():
        if not isinstance(value, dict) or key not in value:
            return False
        if "const" in subschema and value[key] != subschema["const"]:
            return False
    return True


def validate_check(check_obj: dict, schema: dict) -> None:
    check_def = schema["$defs"]["check"]
    validate(check_obj, check_def, schema)


BASE_CHECK = {
    "name": "example-check",
    "command": "true",
    "purpose": "A minimal fixture check used to test failureClass validation.",
    "gates": True,
}


def case_valid_fixable(schema: dict) -> None:
    check = dict(BASE_CHECK, failureClass="fixable")
    validate_check(check, schema)


def case_valid_escalate(schema: dict) -> None:
    check = dict(BASE_CHECK, failureClass="escalate")
    validate_check(check, schema)


def case_absent_is_valid(schema: dict) -> None:
    validate_check(dict(BASE_CHECK), schema)


def case_out_of_enum_refused(schema: dict) -> None:
    check = dict(BASE_CHECK, failureClass="retry")
    try:
        validate_check(check, schema)
    except SchemaError:
        return
    raise AssertionError("expected failureClass: 'retry' to be refused, but it validated")


def case_misspelled_key_refused(schema: dict) -> None:
    check = dict(BASE_CHECK)
    check["failureclass"] = "escalate"
    try:
        validate_check(check, schema)
    except SchemaError:
        return
    raise AssertionError(
        "expected the misspelled key 'failureclass' to be refused by "
        "additionalProperties: false, but it validated"
    )


def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def case_own_harness_still_validates(schema: dict) -> None:
    """Adding `failureClass` to the schema must not regress any already-committed check in
    this repo's own harness.json or the scaffold stub.

    This is deliberately narrower than full `$defs.check` conformance: as traced for task 1,
    no validator in this repo has ever run full schema validation over these files (only
    `test_harness_schema_realpath.py`'s `$schema`/`$id` pointer check exists), so several
    already-live checks carry pre-existing, unrelated gaps against a strict reading of the
    schema (e.g. a stray top-level `evidence` key, an `observed_red` missing `note`) that
    this ticket did not introduce and must not repair — out of scope, and not this ticket's
    finding to fix. What "still validates" means here, and the only thing genuinely at risk
    from this ticket's change: every real check's `failureClass` (if one is ever set) is one
    of the schema's own enum values, and every check is still a plain check object with a
    name. Neither of `out_of_scope`'s exclusions ("setting failureClass on any existing
    check") is exercised today — none of the 112 live checks carries the key yet — so this
    also proves the addition is inert until a check opts in.
    """
    check_schema = schema["$defs"]["check"]
    allowed_failure_classes = check_schema["properties"].get("failureClass", {}).get("enum")

    for label, path in (
        ("planning/harness.json", OWN_HARNESS_PATH),
        ("scaffold/planning/harness.json", SCAFFOLD_HARNESS_PATH),
    ):
        data = _load_json(path)
        checks = data.get("validation", {}).get("checks", [])
        if not checks:
            raise AssertionError(f"{label}: no validation.checks[] found — cannot be a valid fixture")
        for i, check in enumerate(checks):
            if not isinstance(check, dict) or not check.get("name"):
                raise AssertionError(f"{label} checks[{i}]: not a check object with a name")
            if "failureClass" in check:
                if allowed_failure_classes is None:
                    raise AssertionError(
                        f"{label} checks[{i}] ({check['name']!r}): carries failureClass but the "
                        "schema does not define the property yet"
                    )
                if check["failureClass"] not in allowed_failure_classes:
                    raise AssertionError(
                        f"{label} checks[{i}] ({check['name']!r}): failureClass "
                        f"{check['failureClass']!r} is not one of {allowed_failure_classes!r}"
                    )


CASES = [
    ("valid_fixable", case_valid_fixable),
    ("valid_escalate", case_valid_escalate),
    ("absent_is_valid", case_absent_is_valid),
    ("out_of_enum_refused", case_out_of_enum_refused),
    ("misspelled_key_refused", case_misspelled_key_refused),
    ("own_harness_still_validates", case_own_harness_still_validates),
]


def main() -> int:
    schema = load_schema()
    failures = 0
    for name, fn in CASES:
        try:
            fn(schema)
        except (SchemaError, AssertionError) as exc:
            print(f"FAIL {name}: {exc}")
            failures += 1
        except Exception as exc:  # noqa: BLE001 - surface anything unexpected, never swallow
            print(f"ERROR {name}: {exc!r}")
            failures += 1
        else:
            print(f"PASS {name}")

    total = len(CASES)
    if failures:
        print(f"\n{total - failures}/{total} cases passed, {failures} failed.")
        return 1
    print(f"\n{total}/{total} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
