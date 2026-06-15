"""Parse the student's ability lines into model tool-schemas + a dispatch map.

Syntax (one ability per line): 

name(param, param) : description

  - `name` : a function from the robot's API (see the Guide). This is also what the model calls.
  - `(params)` : optional; the param names the model will fill in.
  - `description` : the natural-language translation the model reads - the part students iterate on.

`name` must be one of the canonical API functions (``powers.BY_NAME``). 
The robot understands a fixed set of capabilities; an ability simply equips one 
and gives it a description. Lines starting with `#` (or blank) are ignored. Anything 
malformed becomes a friendly, line-numbered error - it never executes, so it can't crash.

The student's params map POSITIONALLY onto the function's params, so they can rename them (e.g. `pickup(thing)` sends `thing` to the API's object_id).
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .powers import BY_NAME

# name ( optional params ) : description
_LINE = re.compile(r"^\s*(\w+)\s*(?:\(([^)]*)\))?\s*:\s*(.+?)\s*$")


@dataclass
class Ability:
    name: str             # canonical API function name (also the executor primitive)
    params: List[str]     # student-chosen param names (positional)
    description: str


class AbilitySet:
    def __init__(self, abilities: Dict[str, Ability]):
        self.abilities = abilities

    def __bool__(self):
        return bool(self.abilities)

    def tool_of(self, name: str) -> str:
        """The executor primitive an ability runs (same as its canonical name)."""
        return name if name in self.abilities else ""

    def schemas(self) -> List[dict]:
        """Tool schemas sent to the model - one per equipped ability."""
        out = []
        for ab in self.abilities.values():
            power = BY_NAME[ab.name]
            props, required = {}, []
            # student param names inherit the API's param types/requiredness (positional)
            for i, pname in enumerate(ab.params):
                pp = power.params[i]
                props[pname] = {"type": pp.type}
                if pp.required:
                    required.append(pname)
            out.append({
                "type": "function",
                "function": {
                    "name": ab.name,
                    "description": ab.description,
                    "parameters": {"type": "object", "properties": props, "required": required},
                },
            })
        return out

    def execute(self, executor, name: str, args: dict) -> dict:
        """Map an ability call onto its API function and run it via the ToolExecutor."""
        ab = self.abilities.get(name)
        if not ab:
            return {"success": False, "message": f"Unknown ability '{name}'."}
        power = BY_NAME[ab.name]
        mapped = {}
        for i, pname in enumerate(ab.params):
            if pname in (args or {}):
                mapped[power.params[i].name] = args[pname]
        return executor.execute(power.tool, mapped)


def parse_abilities(text: str) -> Tuple[AbilitySet, List[str]]:
    """Return (AbilitySet of valid abilities, list of error strings)."""
    abilities: Dict[str, Ability] = {}
    errors: List[str] = []

    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Migration help: the old "-> POWER" syntax is gone.
        if "->" in line:
            errors.append(f"Line {n}: the `-> POWER` syntax was removed - just write name(params) : description. See the Guide.")
            continue
        m = _LINE.match(line)
        if not m:
            errors.append(f"Line {n}: expected  name(params) : description")
            continue
        name, param_str, desc = m.group(1), m.group(2) or "", m.group(3)
        params = [p.strip() for p in param_str.split(",") if p.strip()]

        if name not in BY_NAME:
            errors.append(f"Line {n}: '{name}' is not one of the robot's API functions. See the Guide.")
            continue
        p = BY_NAME[name]
        n_required = sum(1 for q in p.params if q.required)
        if len(params) < n_required:
            errors.append(f"Line {n}: '{name}' needs at least {n_required} param(s): {', '.join(q.name for q in p.params if q.required)}")
            continue
        if len(params) > len(p.params):
            errors.append(f"Line {n}: '{name}' takes at most {len(p.params)} param(s).")
            continue
        if name in abilities:
            errors.append(f"Line {n}: ability '{name}' already defined.")
            continue
        abilities[name] = Ability(name=name, params=params, description=desc)

    return AbilitySet(abilities), errors
