"""Tool executor - turns one model-chosen tool call into one AI2-THOR action.

This is the "robot SDK" boundary.

Distilled from the original ai2thor-lab PlanExecutor: object-ID resolution,
the per-tool dispatch, and navigate-then-look recovery
"""

import re
from typing import Any, Dict

from .agent import Agent
from .navigator import Navigator

# Tools that don't act on a specific visible object, so they skip the
# "is the target visible and close enough?" pre-check.
_SKIP_VISIBILITY_CHECK = {
    "navigate_to",
    "finish",
    "get_observation",
    "list_objects",
    "get_position",
    "get_object_metadata",
    "drop",
    "look_up",
    "look_down",
    "look_straight",
    "stand",
    "crouch",
    "move_forward",
    "move_back",
    "move_left",
    "move_right",
    "rotate_left",
    "rotate_right",
    "fill_with_liquid",
    "empty_liquid",
    "cook",  # act on the held object
}

# tool name -> AI2-THOR action for the simple "objectId" interactions.
_SIMPLE_OBJECT_ACTIONS = {
    "open": ("OpenObject", "Opened"),
    "close": ("CloseObject", "Closed"),
    "toggle_on": ("ToggleObjectOn", "Turned on"),
    "toggle_off": ("ToggleObjectOff", "Turned off"),
    "empty_liquid": ("EmptyLiquidFromObject", "Emptied"),
    "cook": ("CookObject", "Cooked"),
    "slice": ("SliceObject", "Sliced"),
    "clean": ("CleanObject", "Cleaned"),
    "dirty": ("DirtyObject", "Dirtied"),
    "break_object": ("BreakObject", "Broken"),
    "use_up": ("UseUpObject", "Used up"),
}


class ToolExecutor:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.navigator = Navigator(agent.controller)
        self.navigator.build_reachable_map()

    # -- object id resolution -------------------------------------------------

    def _resolve_object_id(self, raw_id: str) -> str:
        """Map a possibly-shortened id (e.g. 'Mug', 'Apple') to a real object id."""
        if not raw_id:
            return raw_id
        objects = self.agent.controller.last_event.metadata["objects"]

        # exact id
        for obj in objects:
            if obj["objectId"] == raw_id:
                return raw_id
        raw_lower = raw_id.strip().lower()
        # case-insensitive / partial full-id match
        if "|" in raw_id:
            for obj in objects:
                if (
                    raw_lower == obj["objectId"].lower()
                    or raw_lower in obj["objectId"].lower()
                ):
                    return obj["objectId"]
        # by object type (prefer visible)
        type_matches = [o for o in objects if o["objectType"].lower() == raw_lower]
        if not type_matches:
            type_matches = [o for o in objects if raw_lower in o["objectType"].lower()]
        if type_matches:
            type_matches.sort(
                key=lambda o: (not o.get("visible", False), o.get("distance", 1e9))
            )
            return type_matches[0]["objectId"]
        return raw_id

    def _resolve_args(self, arguments: Dict) -> Dict:
        resolved = dict(arguments)
        for key in ("object_id", "receptacle_id"):
            if key in resolved:
                resolved[key] = self._resolve_object_id(resolved[key])
        return resolved

    def _object_state(self, object_id: str) -> Dict[str, Any]:
        for obj in self.agent.get_all_objects():
            if obj["id"] == object_id:
                return obj
        return {}

    def _target_reachable(self, object_id: str) -> tuple:
        obj = self._object_state(object_id)
        if not obj:
            return False, f"Object {object_id} not found in scene."
        if not obj.get("visible", False):
            return (
                False,
                f"{object_id.split('|')[0]} is not visible. Try navigating closer or rotating.",
            )
        if obj.get("distance", float("inf")) > 2.0:
            return (
                False,
                f"{object_id.split('|')[0]} is too far ({obj.get('distance'):.1f}m). Navigate closer first.",
            )
        return True, "ok"

    def _recover_by_looking(self, object_id: str) -> bool:
        """After navigating, rotate / look down to bring the target into view."""
        for look in (None, "LookDown", "LookDown"):
            if look:
                self.agent.controller.step(action=look)
            for _ in range(4):
                ev = self.agent.controller.step(action="RotateRight", degrees=90)
                if not ev.metadata["lastActionSuccess"]:
                    continue
                obj = self._object_state(object_id)
                if obj and obj.get("visible", False):
                    return True
        self.agent.controller.step(action="LookUp")
        self.agent.controller.step(action="LookUp")
        return False

    # main entry

    def execute(self, tool_name: str, arguments: Dict = None) -> Dict:
        """Run one tool. Returns ``{"success": bool, "message": str}``."""
        arguments = self._resolve_args(arguments or {})
        target_id = arguments.get("object_id") or arguments.get("receptacle_id")

        try:
            # observation tools return text instead of acting
            if tool_name == "get_observation":
                return {
                    "success": True,
                    "message": self.agent.get_context_description(),
                }
            if tool_name == "list_objects":
                objs = self.agent.get_visible_objects()
                listing = (
                    "\n".join(
                        f"- {o['name']} (id: {o['id']}) at {o['distance']:.1f}m"
                        for o in objs
                    )
                    or "Nothing visible."
                )
                return {"success": True, "message": listing}
            if tool_name == "get_position":
                return {
                    "success": True,
                    "message": str(self.agent.get_agent_position()),
                }
            if tool_name == "get_object_metadata":
                return {"success": True, "message": str(self._object_state(target_id))}
            if tool_name == "finish":
                return {
                    "success": True,
                    "message": arguments.get("message", "Task complete."),
                }

            # pre-action visibility / distance check for object interactions
            if tool_name not in _SKIP_VISIBILITY_CHECK:
                if not target_id:
                    return {
                        "success": False,
                        "message": f"{tool_name} needs an object id.",
                    }
                ok, msg = self._target_reachable(target_id)
                if not ok:
                    return {"success": False, "message": msg}
                obj = self._object_state(target_id)
                if tool_name == "open" and obj.get("isOpen"):
                    return {"success": True, "message": "Already open."}
                if tool_name == "close" and not obj.get("isOpen"):
                    return {"success": True, "message": "Already closed."}
                if tool_name == "pickup" and self.agent.held_object == target_id:
                    return {"success": True, "message": "Already holding it."}

            # navigation (pathfinding helper)
            if tool_name == "navigate_to":
                success, msg = self.navigator.navigate_to_object(
                    self.agent, arguments["object_id"]
                )
                if success:
                    obj = self._object_state(arguments["object_id"])
                    if not obj or not obj.get("visible", False):
                        if not self._recover_by_looking(arguments["object_id"]):
                            return {
                                "success": False,
                                "message": f"Reached the area but can't see {arguments['object_id'].split('|')[0]}.",
                            }
                return {"success": success, "message": msg}

            # pickup / drop / place
            if tool_name == "pickup":
                ev = self.agent.controller.step(
                    action="PickupObject", objectId=arguments["object_id"]
                )
                if ev.metadata["lastActionSuccess"]:
                    self.agent.held_object = arguments["object_id"]
                    return {"success": True, "message": "Picked up."}
                return {
                    "success": False,
                    "message": ev.metadata.get("errorMessage", "Pickup failed."),
                }

            if tool_name == "drop":
                ev = self.agent.controller.step(action="DropHandObject")
                if ev.metadata["lastActionSuccess"]:
                    self.agent.held_object = None
                    return {"success": True, "message": "Dropped."}
                return {
                    "success": False,
                    "message": ev.metadata.get("errorMessage", "Drop failed."),
                }

            if tool_name == "place_on":
                ev = self.agent.controller.step(
                    action="PutObject",
                    objectId=arguments["receptacle_id"],
                    forceAction=True,
                    placeStationary=True,
                )
                if ev.metadata["lastActionSuccess"]:
                    self.agent.held_object = None
                    return {"success": True, "message": "Placed."}
                return {
                    "success": False,
                    "message": ev.metadata.get("errorMessage", "Place failed."),
                }

            if tool_name == "fill_with_liquid":
                ev = self.agent.controller.step(
                    action="FillObjectWithLiquid",
                    objectId=arguments["object_id"],
                    fillLiquid=arguments.get("liquid", "water"),
                )
                ok = ev.metadata["lastActionSuccess"]
                return {
                    "success": ok,
                    "message": "Filled."
                    if ok
                    else ev.metadata.get("errorMessage", "Failed."),
                }

            # uniform single-object actions
            if tool_name in _SIMPLE_OBJECT_ACTIONS:
                action, ok_msg = _SIMPLE_OBJECT_ACTIONS[tool_name]
                ev = self.agent.controller.step(
                    action=action, objectId=arguments["object_id"]
                )
                ok = ev.metadata["lastActionSuccess"]
                return {
                    "success": ok,
                    "message": ok_msg
                    if ok
                    else ev.metadata.get("errorMessage", "Failed."),
                }

            # movement / look / stance - reuse the natural-language parser path
            cmd = {
                "look_up": "look up",
                "look_down": "look down",
                "look_straight": "look straight",
                "crouch": "crouch",
                "stand": "stand",
                "rotate_left": f"rotate left {arguments.get('degrees', 15)}",
                "rotate_right": f"rotate right {arguments.get('degrees', 15)}",
                "move_forward": f"forward {arguments.get('distance', 0.25)}",
                "move_back": f"back {arguments.get('distance', 0.25)}",
                "move_left": f"left {arguments.get('distance', 0.25)}",
                "move_right": f"right {arguments.get('distance', 0.25)}",
            }.get(tool_name)
            if cmd is not None:
                ok = self.agent.execute_command(cmd)
                return {"success": ok, "message": "Done." if ok else "Movement failed."}

            return {"success": False, "message": f"Unknown tool: {tool_name}"}

        except Exception as e:  # never let one bad call kill the loop
            return {"success": False, "message": f"Error: {e}"}
