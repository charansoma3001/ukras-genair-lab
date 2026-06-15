"""The fixed palette of POWERS - the safe building blocks students equip.

Each power is a real AI2-THOR capability (plus a couple of clearly-marked
helpers like NAVIGATE). A student "ability" binds a name they choose to one of
these powers. Students never write executable code - they pick from this palette
- so nothing they type can crash the robot.

Each power maps to a primitive the ToolExecutor already implements (`tool`), and
declares its parameters so we can (a) show them in the palette, (b) build the
schema sent to the model, and (c) validate ability lines.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Param:
    name: str
    type: str = "string"  # "string" | "number"
    required: bool = True


@dataclass
class Power:
    token: str  # the internal AI2-THOR action, e.g. PickupObject
    tool: str  # the ToolExecutor primitive it runs
    group: str  # palette grouping
    description: str  # default human description
    params: List[Param] = field(default_factory=list)


_OBJ = lambda: [Param("object_id", "string", True)]

POWERS_LIST: List[Power] = [
    # MOVE
    Power(
        "NAVIGATE",
        "navigate_to",
        "MOVE",
        "Walk over to an object (uses pathfinding).",
        _OBJ(),
    ),
    Power(
        "MoveAhead",
        "move_forward",
        "MOVE",
        "Take a step forward.",
        [Param("distance", "number", False)],
    ),
    Power(
        "MoveBack",
        "move_back",
        "MOVE",
        "Take a step backward.",
        [Param("distance", "number", False)],
    ),
    Power(
        "MoveLeft",
        "move_left",
        "MOVE",
        "Strafe left.",
        [Param("distance", "number", False)],
    ),
    Power(
        "MoveRight",
        "move_right",
        "MOVE",
        "Strafe right.",
        [Param("distance", "number", False)],
    ),
    Power(
        "RotateLeft",
        "rotate_left",
        "MOVE",
        "Turn to the left.",
        [Param("degrees", "number", False)],
    ),
    Power(
        "RotateRight",
        "rotate_right",
        "MOVE",
        "Turn to the right.",
        [Param("degrees", "number", False)],
    ),
    Power("LookUp", "look_up", "MOVE", "Tilt the camera up."),
    Power("LookDown", "look_down", "MOVE", "Tilt the camera down."),
    Power("Stand", "stand", "MOVE", "Stand up."),
    Power("Crouch", "crouch", "MOVE", "Crouch down."),
    # INTERACT
    Power("PickupObject", "pickup", "INTERACT", "Pick up a visible object.", _OBJ()),
    Power("DropHandObject", "drop", "INTERACT", "Drop whatever you're holding."),
    Power(
        "PutObject",
        "place_on",
        "INTERACT",
        "Put the held object onto/into a receptacle.",
        [Param("receptacle_id", "string", True)],
    ),
    Power(
        "OpenObject",
        "open",
        "INTERACT",
        "Open a cabinet, fridge, drawer or microwave.",
        _OBJ(),
    ),
    Power("CloseObject", "close", "INTERACT", "Close an open container.", _OBJ()),
    Power(
        "ToggleObjectOn",
        "toggle_on",
        "INTERACT",
        "Turn something on (light, faucet, ...).",
        _OBJ(),
    ),
    Power("ToggleObjectOff", "toggle_off", "INTERACT", "Turn something off.", _OBJ()),
    Power(
        "SliceObject",
        "slice",
        "INTERACT",
        "Slice a sliceable object (needs a knife held).",
        _OBJ(),
    ),
    Power("CookObject", "cook", "INTERACT", "Cook a cookable object.", _OBJ()),
    Power(
        "BreakObject", "break_object", "INTERACT", "Break a breakable object.", _OBJ()
    ),
    Power(
        "FillObjectWithLiquid",
        "fill_with_liquid",
        "INTERACT",
        "Fill an object with a liquid.",
        [Param("object_id", "string", True), Param("liquid", "string", True)],
    ),
    Power(
        "EmptyLiquidFromObject",
        "empty_liquid",
        "INTERACT",
        "Empty liquid out of an object.",
        _OBJ(),
    ),
    Power("CleanObject", "clean", "INTERACT", "Clean a dirty object.", _OBJ()),
    Power("DirtyObject", "dirty", "INTERACT", "Make an object dirty.", _OBJ()),
    Power(
        "UseUpObject",
        "use_up",
        "INTERACT",
        "Use up a consumable (toilet paper, ...).",
        _OBJ(),
    ),
    # SENSE
    Power(
        "ListObjects",
        "list_objects",
        "SENSE",
        "List the objects you can currently see.",
    ),
    Power(
        "GetObjectMetadata",
        "get_object_metadata",
        "SENSE",
        "Inspect one object's full state.",
        _OBJ(),
    ),
    Power("GetPosition", "get_position", "SENSE", "Report where you are standing."),
    # DONE
    Power(
        "Finish",
        "finish",
        "DONE",
        "Say the command is complete.",
        [Param("message", "string", False)],
    ),
]

POWERS = {p.token: p for p in POWERS_LIST}

# The student-facing API is keyed by the friendly canonical name
BY_NAME = {p.tool: p for p in POWERS_LIST}


def signature(p: Power) -> str:
    """e.g. ``pickup(object_id)`` or ``drop()`` - the canonical API signature."""
    args = ", ".join(q.name for q in p.params)
    return f"{p.tool}({args})" if p.params else f"{p.tool}()"


def palette() -> list:
    """Serializable API reference for the UI / docs generator."""
    return [
        {
            "name": p.tool,
            "signature": signature(p),
            "group": p.group,
            "description": p.description,
            "params": [
                {"name": q.name, "type": q.type, "required": q.required}
                for q in p.params
            ],
            # a ready-to-edit ability line in the new DSL
            "example": f"{signature(p)} : {p.description}",
        }
        for p in POWERS_LIST
    ]
