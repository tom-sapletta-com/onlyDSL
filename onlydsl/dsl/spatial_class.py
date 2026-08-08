from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .common import ControlDslError, extract_one


class SpatialClass(str, Enum):
    PHYSICAL = "physical"
    CYBER = "cyber"
    LOGICAL = "logical"
    HYBRID = "hybrid"


PHYSICAL_CLASSES = {SpatialClass.PHYSICAL, SpatialClass.HYBRID}
KNOWN_REQUIREMENTS = {"position", "size", "orientation", "constraints", "clearance", "parent-zone", "logical-endpoint", "runtime-status"}


@dataclass(frozen=True, slots=True)
class SpatialTypeContract:
    subject_type: str
    spatial_class: SpatialClass
    require: frozenset[str] = field(default_factory=frozenset)
    optional: frozenset[str] = field(default_factory=frozenset)
    forbid: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class SpatialComponent:
    component_id: str
    subject_type: str


@dataclass(slots=True)
class SpatialClassDocument:
    id: str
    types: dict[str, SpatialTypeContract]
    components: dict[str, SpatialComponent]

    def classify(self, component_id: str) -> SpatialClass:
        component = self.components.get(component_id)
        if not component or component.subject_type not in self.types:
            raise ControlDslError(f"component {component_id!r} has no spatial type contract")
        return self.types[component.subject_type].spatial_class

    def geometry_subjects(self) -> set[str]:
        return {component_id for component_id, component in self.components.items() if self.types[component.subject_type].spatial_class in PHYSICAL_CLASSES}

    def required_checks(self, component_id: str) -> frozenset[str]:
        component = self.components[component_id]
        return self.types[component.subject_type].require


def _parse_type(lines: list[str], index: int) -> tuple[SpatialTypeContract, int]:
    subject_type = lines[index].split(None, 1)[1]
    spatial_class = None
    requirements = {"REQUIRE": set(), "OPTIONAL": set(), "FORBID": set()}
    index += 1
    while index < len(lines) and lines[index] != "END_TYPE":
        key, _, value = lines[index].partition(" ")
        if key == "CLASS":
            try:
                spatial_class = SpatialClass(value)
            except ValueError as exc:
                raise ControlDslError(f"invalid spatial class {value!r}") from exc
        elif key in requirements:
            if value not in KNOWN_REQUIREMENTS:
                raise ControlDslError(f"unknown spatial requirement {value!r}")
            requirements[key].add(value)
        else:
            raise ControlDslError(f"unknown TYPE directive {key!r}")
        index += 1
    if spatial_class is None:
        raise ControlDslError(f"TYPE {subject_type} requires CLASS")
    require, optional, forbid = (requirements[key] for key in ("REQUIRE", "OPTIONAL", "FORBID"))
    if (require & forbid) or (optional & forbid):
        raise ControlDslError(f"TYPE {subject_type} has contradictory requirements")
    if spatial_class not in PHYSICAL_CLASSES and ({"position", "size", "orientation"} & require):
        raise ControlDslError(f"non-physical TYPE {subject_type} cannot require physical pose")
    return SpatialTypeContract(subject_type, spatial_class, frozenset(require), frozenset(optional), frozenset(forbid)), index


def _parse_component(line: str) -> SpatialComponent:
    parts = line.split()
    if len(parts) != 4 or parts[2] != "TYPE":
        raise ControlDslError("COMPONENT syntax is COMPONENT <id> TYPE <type>")
    return SpatialComponent(parts[1], parts[3])


def parse_spatial_class(markdown: str) -> SpatialClassDocument:
    lines = [line.strip() for line in extract_one(markdown, "spatialclassdsl").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("SPATIAL_MODEL ") or lines[-1] != "END_SPATIAL_MODEL":
        raise ControlDslError("invalid SpatialClassDSL envelope")
    model_id = lines[0].split(None, 1)[1]
    types: dict[str, SpatialTypeContract] = {}
    components: dict[str, SpatialComponent] = {}
    index = 1
    while index < len(lines) - 1:
        line = lines[index]
        if line.startswith("TYPE "):
            contract, index = _parse_type(lines, index)
            types[contract.subject_type] = contract
        elif line.startswith("COMPONENT "):
            component = _parse_component(line)
            components[component.component_id] = component
        else:
            raise ControlDslError(f"unknown SpatialClassDSL directive {line!r}")
        index += 1
    missing = sorted({component.subject_type for component in components.values()} - types.keys())
    if missing:
        raise ControlDslError("components reference unknown types: " + ", ".join(missing))
    return SpatialClassDocument(model_id, types, components)


def render_spatial_class(document: SpatialClassDocument) -> str:
    rows = ["```spatialclassdsl", f"SPATIAL_MODEL {document.id}"]
    for contract in document.types.values():
        rows.extend([f"TYPE {contract.subject_type}", f"  CLASS {contract.spatial_class.value}"])
        rows.extend(f"  REQUIRE {value}" for value in sorted(contract.require))
        rows.extend(f"  OPTIONAL {value}" for value in sorted(contract.optional))
        rows.extend(f"  FORBID {value}" for value in sorted(contract.forbid))
        rows.append("END_TYPE")
    rows.extend(f"COMPONENT {item.component_id} TYPE {item.subject_type}" for item in document.components.values())
    rows.extend(["END_SPATIAL_MODEL", "```"])
    return "\n".join(rows)


def spatial_class_from_twin(twin: dict, *, model_id: str | None = None) -> SpatialClassDocument:
    """Create a read-only control-plane projection from downstream Twin properties."""
    types: dict[str, SpatialTypeContract] = {}
    components: dict[str, SpatialComponent] = {}

    def walk(items: list[dict]) -> None:
        for item in items:
            component_id = str(item.get("id", ""))
            subject_type = str(item.get("type", "unknown"))
            properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
            try:
                spatial_class = SpatialClass(str(properties.get("spatialClass", "physical")))
            except ValueError as exc:
                raise ControlDslError(f"component {component_id!r} has invalid spatialClass") from exc
            contract_id = f"{subject_type}__{spatial_class.value}"
            split = lambda name: frozenset(value for value in str(properties.get(name, "")).split("|") if value)
            contract = SpatialTypeContract(contract_id, spatial_class, split("spatialRequire"), split("spatialOptional"), split("spatialForbid"))
            if not (contract.require | contract.optional | contract.forbid) <= KNOWN_REQUIREMENTS:
                raise ControlDslError(f"component {component_id!r} contains an unknown spatial requirement")
            previous = types.get(contract_id)
            if previous is not None and previous != contract:
                raise ControlDslError(f"Twin type contract {contract_id!r} is inconsistent between components")
            types[contract_id] = contract
            components[component_id] = SpatialComponent(component_id, contract_id)
            walk(item.get("children", []) if isinstance(item.get("children"), list) else [])

    walk(twin.get("components", []) if isinstance(twin.get("components"), list) else [])
    if not components:
        raise ControlDslError("Twin contains no components for SpatialClassDSL projection")
    return SpatialClassDocument(model_id or str(twin.get("id", "twin")), types, components)
