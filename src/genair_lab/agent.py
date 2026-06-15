import cv2
from ai2thor.controller import Controller

from .parser import CommandParser


class Agent:
    def __init__(self, scene="FloorPlan1", width=800, height=600):
        print(f"[*] Initializing iTHOR in {scene} with resolution {width}x{height}...")
        self.controller = Controller(
            scene=scene,
            width=width,
            height=height,
            gridSize=0.1,
            snapToGrid=False,
            rotateStepDegrees=15,
        )
        self.held_object = None
        self.parser = CommandParser(self)
        print("[+] Ready!")

    def stop(self):
        """Stop the controller and close the window."""
        print("[*] Stopping AI2-THOR controller...")
        self.controller.stop()

    def get_visible_objects(self):
        """Get visible objects with ALL properties"""
        objects = self.controller.last_event.metadata["objects"]
        visible = []

        for obj in objects:
            if obj["visible"]:
                visible.append(
                    {
                        "name": obj["objectType"],
                        "id": obj["objectId"],
                        "distance": obj["distance"],
                        # Basic interaction
                        "pickupable": obj.get("pickupable", False),
                        "moveable": obj.get("moveable", False),
                        "openable": obj.get("openable", False),
                        "toggleable": obj.get("toggleable", False),
                        "receptacle": obj.get("receptacle", False),
                        # Advanced interaction
                        "canFillWithLiquid": obj.get("canFillWithLiquid", False),
                        "sliceable": obj.get("sliceable", False),
                        "cookable": obj.get("cookable", False),
                        "breakable": obj.get("breakable", False),
                        "dirtyable": obj.get("dirtyable", False),
                        "canBeUsedUp": obj.get("canBeUsedUp", False),
                        # States
                        "isOpen": obj.get("isOpen", False),
                        "isToggled": obj.get("isToggled", False),
                        "isFilledWithLiquid": obj.get("isFilledWithLiquid", False),
                        "isSliced": obj.get("isSliced", False),
                        "isCooked": obj.get("isCooked", False),
                        "isBroken": obj.get("isBroken", False),
                        "isDirty": obj.get("isDirty", False),
                        "isUsedUp": obj.get("isUsedUp", False),
                    }
                )
        return visible

    def get_all_objects(self):
        """Get ALL objects in the scene regardless of visibility (for planning)"""
        objects = self.controller.last_event.metadata["objects"]
        all_objs = []

        for obj in objects:
            all_objs.append(
                {
                    "name": obj["objectType"],
                    "id": obj["objectId"],
                    "distance": obj["distance"],
                    "position": obj["position"],
                    "visible": obj["visible"],
                    # Basic interaction
                    "pickupable": obj.get("pickupable", False),
                    "moveable": obj.get("moveable", False),
                    "openable": obj.get("openable", False),
                    "toggleable": obj.get("toggleable", False),
                    "receptacle": obj.get("receptacle", False),
                    # Advanced interaction
                    "canFillWithLiquid": obj.get("canFillWithLiquid", False),
                    "sliceable": obj.get("sliceable", False),
                    "cookable": obj.get("cookable", False),
                    "breakable": obj.get("breakable", False),
                    "dirtyable": obj.get("dirtyable", False),
                    "canBeUsedUp": obj.get("canBeUsedUp", False),
                    # States
                    "isOpen": obj.get("isOpen", False),
                    "isToggled": obj.get("isToggled", False),
                    "isFilledWithLiquid": obj.get("isFilledWithLiquid", False),
                    "isSliced": obj.get("isSliced", False),
                    "isCooked": obj.get("isCooked", False),
                    "isBroken": obj.get("isBroken", False),
                    "isDirty": obj.get("isDirty", False),
                    "isUsedUp": obj.get("isUsedUp", False),
                    # Receptacle info
                    "receptacleObjectIds": obj.get("receptacleObjectIds", []),
                    "parentReceptacles": obj.get("parentReceptacles") or [],
                }
            )
        return all_objs

    def get_scene_metadata(self):
        """Get full scene metadata including all objects for the Planner"""
        meta = self.controller.last_event.metadata["agent"]
        return {
            "agent": {
                "position": meta["position"],
                "rotation": meta["rotation"]["y"],
                "horizon": meta["cameraHorizon"],
                "standing": meta.get("isStanding", True),
                "held_object": self.held_object,
            },
            "objects": self.get_all_objects(),
        }

    def execute_command(self, command):
        """Execute command"""
        print(f"\n[CMD] {command}")

        action_dict = self.parser.parse_command(command)

        if "error" in action_dict:
            print(f"[!] {action_dict['error']}")
            return False

        # Extract metadata
        action_name = action_dict["action"]
        repeat = action_dict.pop("repeat", 1)
        is_placing = action_dict.pop("placing", False)
        placing_on = action_dict.pop("placing_on", None)
        filling_liquid = action_dict.pop("filling", None)

        print(f"  [>] Executing: {action_name}", end="")

        if is_placing and placing_on:
            held_name = self.held_object if self.held_object else "object"
            print(f" - placing {held_name} on {placing_on}")
        elif filling_liquid:
            obj_name = action_dict["objectId"]
            print(f" - filling {obj_name} with {filling_liquid}")
        elif "objectId" in action_dict:
            obj_name = action_dict["objectId"]
            print(f" on {obj_name}")
        elif "degrees" in action_dict:
            print(f" ({action_dict['degrees']} degrees)")
        elif "moveMagnitude" in action_dict:
            print(f" ({action_dict['moveMagnitude']}m)")
        else:
            print()

        # Execute
        success = True
        for i in range(repeat):
            event = self.controller.step(**action_dict)
            if not event.metadata["lastActionSuccess"]:
                success = False
                break

        if success:
            print("  [+] Success!")

            # Track held object - FIXED for break/slice
            if action_dict.get("action") == "PickupObject":
                self.held_object = action_dict.get("objectId")
                print(f"  [HOLD] Now holding: {self.held_object.split('|')[0]}")
            elif action_dict.get("action") in ["DropHandObject", "PutObject"]:
                if self.held_object:
                    print(f"  [DROP] Released: {self.held_object.split('|')[0]}")
                self.held_object = None
            elif action_dict.get("action") in ["BreakObject", "SliceObject"]:
                # Breaking/slicing held objects removes them from hand
                if self.held_object and action_dict.get("objectId") == self.held_object:
                    print(
                        f"  [TRANSFORM] {self.held_object.split('|')[0]} destroyed/sliced - no longer holding"
                    )
                    self.held_object = None

            # Show agent state
            meta = self.controller.last_event.metadata["agent"]
            print(
                f"  [POS] Position: ({meta['position']['x']:.2f}, {meta['position']['z']:.2f})"
            )
            print(
                f"  [ROT] Rotation: {meta['rotation']['y']:.1f} deg, Horizon: {meta['cameraHorizon']:.1f} deg"
            )

            # self.display_frame()
            return True
        else:
            print(
                f"  [!] Failed: {self.controller.last_event.metadata['errorMessage']}"
            )
            return False

    def display_frame(self):
        """Display view"""
        frame = self.controller.last_event.frame
        meta = self.controller.last_event.metadata["agent"]

        info = f"Pos: ({meta['position']['x']:.1f}, {meta['position']['z']:.1f}) | "
        info += f"Rot: {meta['rotation']['y']:.0f}deg | "
        info += f"Horizon: {meta['cameraHorizon']:.0f}deg"

        img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        cv2.putText(img, info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        if self.held_object:
            held_text = f"Holding: {self.held_object.split('|')[0]}"
            cv2.putText(
                img,
                held_text,
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
            )

        try:
            cv2.imshow("iTHOR Complete Control", img)
            cv2.waitKey(1)
        except Exception:
            # Skip display if windowing system is not available
            pass

    def get_context_description(self):
        """Generate a text description of current state for LLM consumption"""
        visible = self.get_visible_objects()
        relevant = [
            o for o in visible if o["pickupable"] or o["receptacle"] or o["toggleable"]
        ]

        meta = self.controller.last_event.metadata["agent"]
        desc = "Current Observation:\n"
        desc += (
            f"Location: ({meta['position']['x']:.2f}, {meta['position']['z']:.2f})\n"
        )
        desc += f"Rotation: {meta['rotation']['y']:.1f} deg, Horizon: {meta['cameraHorizon']:.1f} deg\n"
        desc += f"Holding: {self.held_object.split('|')[0] if self.held_object else 'nothing'}\n"
        desc += "Visible Objects:\n"
        for obj in relevant:
            state = []
            if obj["isOpen"]:
                state.append("OPEN")
            if obj["isToggled"]:
                state.append("ON")
            if obj["isSliced"]:
                state.append("SLICED")
            if obj["isCooked"]:
                state.append("COOKED")
            if obj["isBroken"]:
                state.append("BROKEN")
            if obj["isFilledWithLiquid"]:
                state.append("FILLED")
            state_str = f"[{', '.join(state)}]" if state else ""
            desc += f"- {obj['name']} (ID: {obj['id']}) {state_str} at {obj['distance']:.1f}m\n"
        return desc

    def get_full_scene_context(self, scene_type: str = "") -> str:
        """Generate a full scene context description including ALL objects."""
        all_objects = self.get_all_objects()
        # Only include interactable objects to keep context focused
        interactable = [
            o
            for o in all_objects
            if o["pickupable"] or o["receptacle"] or o["toggleable"] or o["openable"]
        ]

        meta = self.controller.last_event.metadata["agent"]
        scene_name = self.controller.last_event.metadata.get("sceneName", "Unknown")

        desc = f"Scene: {scene_type or scene_name}\n"
        desc += f"Holding: {self.held_object.split('|')[0] if self.held_object else 'nothing'}\n"
        desc += f"All interactable objects in the scene:\n"
        for obj in interactable:
            desc += f"- {obj['name']} ({'visible' if obj['visible'] else 'nearby'}, "
            desc += f"pickupable={obj['pickupable']}, openable={obj['openable']})\n"
        return desc

    def get_agent_position(self):
        """Return current agent position as dict"""
        meta = self.controller.last_event.metadata["agent"]
        return {
            "x": meta["position"]["x"],
            "y": meta["position"]["y"],
            "z": meta["position"]["z"],
            "rotation": meta["rotation"]["y"],
            "horizon": meta["cameraHorizon"],
            "standing": meta.get("isStanding", True),
        }

    def get_action_result(self):
        """Return structured result of last action"""
        meta = self.controller.last_event.metadata
        return {
            "success": meta["lastActionSuccess"],
            "error": meta.get("errorMessage", None)
            if not meta["lastActionSuccess"]
            else None,
            "position": self.get_agent_position(),
            "held_object": self.held_object.split("|")[0] if self.held_object else None,
        }
