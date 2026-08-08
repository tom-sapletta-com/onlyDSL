from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .common import ControlDslError, extract_one

PARAMETER_TYPES = {"decimal", "integer", "boolean", "string"}
QUALITIES = {"observed", "measured", "derived", "declared"}


@dataclass(frozen=True, slots=True)
class ParameterContract:
    name: str
    subject_type: str
    value_type: str
    unit: str
    quality: str
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    allowed: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class ParameterValidation:
    ok: bool
    code: str
    message: str


@dataclass(slots=True)
class ParameterContractDocument:
    id: str
    parameters: dict[tuple[str, str], ParameterContract]

    def validate(self, *, name: str, subject_type: str, value: Any, unit: str, quality: str) -> ParameterValidation:
        contract = self.parameters.get((subject_type, name))
        if contract is None:
            return ParameterValidation(False, "PARAMETER_CONTRACT_MISSING", f"no contract for {subject_type}.{name}")
        if unit == "mixed":
            return ParameterValidation(False, "PARAMETER_UNIT_MIXED_FORBIDDEN", "UNIT mixed is never a domain contract")
        if unit != contract.unit:
            return ParameterValidation(False, "PARAMETER_UNIT_MISMATCH", f"expected {contract.unit}, got {unit}")
        if quality != contract.quality:
            return ParameterValidation(False, "PARAMETER_QUALITY_MISMATCH", f"expected {contract.quality}, got {quality}")
        type_ok = {
            "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "decimal": isinstance(value, (int, float, Decimal)) and not isinstance(value, bool) and (not isinstance(value, float) or math.isfinite(value)),
            "string": isinstance(value, str),
        }[contract.value_type]
        if not type_ok:
            return ParameterValidation(False, "PARAMETER_TYPE_MISMATCH", f"expected {contract.value_type}")
        if contract.allowed and value not in contract.allowed:
            return ParameterValidation(False, "PARAMETER_VALUE_NOT_ALLOWED", f"{value!r} is outside ALLOWED")
        if contract.value_type in {"decimal", "integer"}:
            numeric = Decimal(str(value))
            if contract.minimum is not None and numeric < contract.minimum:
                return ParameterValidation(False, "PARAMETER_BELOW_MINIMUM", f"{numeric} < {contract.minimum}")
            if contract.maximum is not None and numeric > contract.maximum:
                return ParameterValidation(False, "PARAMETER_ABOVE_MAXIMUM", f"{numeric} > {contract.maximum}")
        return ParameterValidation(True, "PARAMETER_VALID", "value satisfies the exact contract")


def parse_parameter_contracts(markdown: str) -> ParameterContractDocument:
    lines = [line.strip() for line in extract_one(markdown, "parametercontractdsl").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("PARAMETER_CONTRACTS ") or lines[-1] != "END_PARAMETER_CONTRACTS":
        raise ControlDslError("invalid ParameterContractDSL envelope")
    result = ParameterContractDocument(lines[0].split(None, 1)[1], {})
    index = 1
    while index < len(lines) - 1:
        if not lines[index].startswith("PARAMETER "):
            raise ControlDslError(f"expected PARAMETER, got {lines[index]!r}")
        name = lines[index].split(None, 1)[1]
        fields: dict[str, str] = {}
        index += 1
        while index < len(lines) and lines[index] != "END_PARAMETER":
            key, _, value = lines[index].partition(" ")
            if key not in {"SUBJECT_TYPE", "TYPE", "UNIT", "QUALITY", "RANGE", "ALLOWED"} or key in fields:
                raise ControlDslError(f"invalid or duplicate parameter field {key!r}")
            fields[key] = value
            index += 1
        missing = {"SUBJECT_TYPE", "TYPE", "UNIT", "QUALITY"} - fields.keys()
        if missing:
            raise ControlDslError(f"parameter {name} missing: {', '.join(sorted(missing))}")
        if fields["TYPE"] not in PARAMETER_TYPES or fields["QUALITY"] not in QUALITIES:
            raise ControlDslError(f"parameter {name} has invalid TYPE or QUALITY")
        if fields["UNIT"] == "mixed":
            raise ControlDslError("UNIT mixed is forbidden; split heterogeneous observations")
        minimum = maximum = None
        if "RANGE" in fields:
            try:
                range_value = json.loads(fields["RANGE"], parse_float=Decimal, parse_int=Decimal)
                if not isinstance(range_value, list) or len(range_value) != 2:
                    raise ValueError
                minimum, maximum = Decimal(range_value[0]), Decimal(range_value[1])
            except (ValueError, TypeError, InvalidOperation, json.JSONDecodeError) as exc:
                raise ControlDslError("RANGE must be [minimum, maximum]") from exc
            if minimum > maximum:
                raise ControlDslError("RANGE minimum cannot exceed maximum")
        allowed: tuple[Any, ...] = ()
        if "ALLOWED" in fields:
            parsed = json.loads(fields["ALLOWED"])
            if not isinstance(parsed, list):
                raise ControlDslError("ALLOWED must be a JSON list")
            allowed = tuple(parsed)
        contract = ParameterContract(name, fields["SUBJECT_TYPE"], fields["TYPE"], fields["UNIT"], fields["QUALITY"], minimum, maximum, allowed)
        key = (contract.subject_type, contract.name)
        if key in result.parameters:
            raise ControlDslError(f"duplicate parameter contract {key}")
        result.parameters[key] = contract
        index += 1
    return result


def render_parameter_contracts(document: ParameterContractDocument) -> str:
    rows = ["```parametercontractdsl", f"PARAMETER_CONTRACTS {document.id}"]
    for item in document.parameters.values():
        rows.extend([f"PARAMETER {item.name}", f"  SUBJECT_TYPE {item.subject_type}", f"  TYPE {item.value_type}", f"  UNIT {item.unit}"])
        if item.minimum is not None:
            rows.append(f"  RANGE [{item.minimum}, {item.maximum}]")
        if item.allowed:
            rows.append("  ALLOWED " + json.dumps(item.allowed, ensure_ascii=False))
        rows.extend([f"  QUALITY {item.quality}", "END_PARAMETER"])
    rows.extend(["END_PARAMETER_CONTRACTS", "```"])
    return "\n".join(rows)
