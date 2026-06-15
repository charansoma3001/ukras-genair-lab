import heapq
import math
from typing import Dict, List, Optional, Tuple


class Navigator:
    def __init__(self, controller, grid_size=0.25):
        self.controller = controller
        self.grid_size = grid_size
        self.reachable_positions = None
        self.position_to_grid = {}
        self.grid_to_position = {}

    def build_reachable_map(self):
        """Get reachable positions from AI2-THOR and build grid mapping"""
        event = self.controller.step(action="GetReachablePositions")
        if not event.metadata["lastActionSuccess"]:
            return False

        self.reachable_positions = event.metadata["reachablePositions"]

        for pos in self.reachable_positions:
            grid_x = round(pos["x"] / self.grid_size)
            grid_z = round(pos["z"] / self.grid_size)
            grid_key = (grid_x, grid_z)
            self.position_to_grid[(pos["x"], pos["z"])] = grid_key
            if grid_key not in self.grid_to_position:
                self.grid_to_position[grid_key] = (pos["x"], pos["z"])

        return True

    def _heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> float:
        """Euclidean distance heuristic for A*"""
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    def _get_neighbors(self, node: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Get valid neighboring grid cells"""
        x, z = node
        neighbors = []
        for dx, dz in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            new_node = (x + dx, z + dz)
            if new_node in self.grid_to_position:
                neighbors.append(new_node)
        return neighbors

    def _reconstruct_path(
        self, came_from: Dict, current: Tuple[int, int]
    ) -> List[Tuple[int, int]]:
        """Reconstruct path from A* search"""
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        return path[::-1]

    def find_path(
        self, start_pos: Tuple[float, float], end_pos: Tuple[float, float]
    ) -> Optional[List[Tuple[float, float]]]:
        """Find path between two positions using A*"""
        if not self.reachable_positions:
            self.build_reachable_map()

        start_grid = (
            round(start_pos[0] / self.grid_size),
            round(start_pos[1] / self.grid_size),
        )
        end_grid = (
            round(end_pos[0] / self.grid_size),
            round(end_pos[1] / self.grid_size),
        )

        if start_grid not in self.grid_to_position:
            start_grid = self._find_nearest_grid(start_pos)
        if end_grid not in self.grid_to_position:
            end_grid = self._find_nearest_grid(end_pos)

        if start_grid is None or end_grid is None:
            return None

        open_set = []
        heapq.heappush(open_set, (0, start_grid))
        came_from = {}
        g_score = {start_grid: 0}
        f_score = {start_grid: self._heuristic(start_grid, end_grid)}

        while open_set:
            _, current = heapq.heappop(open_set)

            if current == end_grid:
                grid_path = self._reconstruct_path(came_from, current)
                return [self.grid_to_position[g] for g in grid_path]

            for neighbor in self._get_neighbors(current):
                tentative_g = g_score[current] + 1

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + self._heuristic(
                        neighbor, end_grid
                    )
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))

        return None

    def _find_nearest_grid(self, pos: Tuple[float, float]) -> Optional[Tuple[int, int]]:
        """Find nearest reachable grid cell to a position"""
        if not self.reachable_positions:
            return None

        min_dist = float("inf")
        nearest = None

        for p in self.reachable_positions:
            dist = math.sqrt((p["x"] - pos[0]) ** 2 + (p["z"] - pos[1]) ** 2)
            if dist < min_dist:
                min_dist = dist
                nearest = (
                    round(p["x"] / self.grid_size),
                    round(p["z"] / self.grid_size),
                )

        return nearest

    def _find_interaction_positions(self, object_id: str) -> List[dict]:
        """Find positions where the agent can interact with the object.

        Uses AI2-THOR's GetInteractablePoses (from ref-planner) to get exact
        positions with rotation and camera angles. Falls back to distance-based
        candidates if the API returns nothing.

        Returns list of dicts: {x, z, rotation, horizon} or {x, z} for fallback.
        """
        # Try GetInteractablePoses with progressively more camera horizons and both standings (crouch/stand)
        for horizons in [[0], [0, 30], [0, 30, -30], [0, 30, -30, 60]]:
            event = self.controller.step(
                action="GetInteractablePoses",
                objectId=object_id,
                standings=[True, False],
                horizons=horizons,
            )
            poses = event.metadata.get("actionReturn")
            if poses:
                # Return as list of dicts with full pose info
                result = []
                for p in poses:
                    result.append(
                        {
                            "x": p["x"],
                            "y": p["y"],
                            "z": p["z"],
                            "rotation": p["rotation"],
                            "horizon": p["horizon"],
                            "standing": p["standing"],
                        }
                    )
                return result

        # Fallback: distance-based candidates (old approach)
        target_pos = self._get_object_position(object_id)
        if target_pos is None:
            return []

        if not self.reachable_positions:
            self.build_reachable_map()

        INTERACTION_RANGE = 2.0

        candidates = []
        for p in self.reachable_positions:
            dist = math.sqrt(
                (p["x"] - target_pos[0]) ** 2 + (p["z"] - target_pos[1]) ** 2
            )
            if dist <= INTERACTION_RANGE:
                candidates.append((dist, {"x": p["x"], "z": p["z"]}))

        if not candidates:
            all_positions = []
            for p in self.reachable_positions:
                dist = math.sqrt(
                    (p["x"] - target_pos[0]) ** 2 + (p["z"] - target_pos[1]) ** 2
                )
                all_positions.append((dist, {"x": p["x"], "z": p["z"]}))
            all_positions.sort(key=lambda c: c[0])
            return [pos for _, pos in all_positions[:5]]

        candidates.sort(key=lambda c: c[0])
        return [pos for _, pos in candidates]

    def _is_object_interactable(self, object_id: str) -> bool:
        """Check if an object is visible and within interaction distance."""
        objects = self.controller.last_event.metadata["objects"]
        for obj in objects:
            if obj["objectId"] == object_id:
                # Increased distance threshold to 2.0m as interactive poses can be slightly further than 1.5m
                return (
                    obj.get("visible", False)
                    and obj.get("distance", float("inf")) <= 2.0
                )
        return False

    def _center_object_in_frame(self, object_id: str):
        """
        After navigation, teleport the camera to precisely face the target both
        horizontally (yaw) and vertically (pitch/horizon).
        """
        try:
            agent_meta = self.controller.last_event.metadata["agent"]
            agent_pos = agent_meta["position"]
            agent_height = agent_pos["y"] + (
                0.675 if agent_meta.get("isStanding", True) else 0.45
            )

            objects = self.controller.last_event.metadata["objects"]
            target = next((o for o in objects if o["objectId"] == object_id), None)
            if not target:
                return

            obj_pos = target["position"]

            dx = obj_pos["x"] - agent_pos["x"]
            dz = obj_pos["z"] - agent_pos["z"]
            horizontal_dist = math.sqrt(dx * dx + dz * dz)

            if horizontal_dist < 0.01:
                return

            # Horizontal: compute bearing to object
            # math.atan2(dx, dz) gives angle in the XZ plane; AI2-THOR yaw 0=north (+z)
            target_yaw = math.degrees(math.atan2(dx, dz)) % 360

            # Vertical: compute horizon (pitch)
            dy = agent_height - obj_pos["y"]
            target_horizon = math.degrees(math.atan2(dy, horizontal_dist))
            target_horizon = max(-60.0, min(60.0, target_horizon))

            current_yaw = agent_meta["rotation"]["y"] % 360
            current_horizon = agent_meta["cameraHorizon"]
            yaw_diff = abs((target_yaw - current_yaw + 180) % 360 - 180)
            horizon_diff = abs(target_horizon - current_horizon)

            print(
                f"  [CAM] Centering {object_id.split('|')[0]}: yaw {current_yaw:.1f}°->{target_yaw:.1f}° (Δ{yaw_diff:.1f}°), horizon {current_horizon:.1f}°->{target_horizon:.1f}° (Δ{horizon_diff:.1f}°)"
            )

            if yaw_diff < 3.0 and horizon_diff < 3.0:
                return  # Already centered

            # Teleport to exact facing angle - precise, no drift
            self.controller.step(
                action="Teleport",
                position=agent_pos,
                rotation=dict(x=0, y=target_yaw, z=0),
                horizon=target_horizon,
                standing=agent_meta.get("isStanding", True),
            )

        except Exception as e:
            print(f"  [CAM] Could not center object in frame: {e}")

    def navigate_to_object(self, agent, object_id: str) -> Tuple[bool, str]:
        """Navigate to a position where we can interact with the target object.

        Uses GetInteractablePoses when available (exact position + rotation + horizon).
        Falls back to distance-based candidates otherwise.
        """
        # Rebuild reachable map to account for any moved objects
        self.build_reachable_map()

        # Check if we can already interact without moving
        if self._is_object_interactable(object_id):
            print(
                f"  [NAV] Already within interaction range of {object_id.split('|')[0]}"
            )
            self._center_object_in_frame(object_id)
            return True, f"Already near {object_id}"

        # Get candidate interaction positions
        candidates = self._find_interaction_positions(object_id)
        if not candidates:
            print(
                f"  [NAV] No interaction positions found for {object_id.split('|')[0]}"
            )
            return False, f"Object {object_id} not found or not accessible"

        agent_pos = agent.get_agent_position()
        start_pos = (agent_pos["x"], agent_pos["z"])

        # Try each candidate position
        for attempt, pose in enumerate(candidates[:10]):
            target_pos = (pose["x"], pose["z"])
            path = self.find_path(start_pos, target_pos)
            if path is None:
                continue

            if attempt > 0:
                print(f"  [NAV] Trying alternate position #{attempt + 1}...")

            print(
                f"  [NAV] Pathfinding to interaction position near {object_id.split('|')[0]}..."
            )
            print(f"  [NAV] Path: {len(path) - 1} steps")

            success = self._execute_path(agent, path, object_id)
            if success:
                # If we have exact pose from GetInteractablePoses, teleport to it for precision
                if "rotation" in pose:
                    print(
                        f"  [NAV] Applying exact pose: pos=({pose['x']:.2f}, {pose['y']:.2f}, {pose['z']:.2f}), rot={pose['rotation']:.1f}, horiz={pose['horizon']:.1f}, stand={pose['standing']}"
                    )
                    self.controller.step(
                        action="Teleport",
                        position=dict(x=pose["x"], y=pose["y"], z=pose["z"]),
                        rotation=dict(x=0, y=pose["rotation"], z=0),
                        horizon=pose["horizon"],
                        standing=pose["standing"],
                    )

                # has_exact_pose: GetInteractablePoses gave us a verified horizon
                has_exact_pose = "rotation" in pose

                # Verify object is interactable after positioning
                if self._is_object_interactable(object_id):
                    # Always center - GetInteractablePoses guarantees interactability, not centering
                    self._center_object_in_frame(object_id)
                    return True, f"Navigated to {object_id}"

                # Vertical scanning recovery step
                if self._vertical_recovery(object_id):
                    self._center_object_in_frame(object_id)
                    return True, f"Navigated to {object_id}"

                # Fallback to rotation recovery
                recovered = self._rotation_recovery(object_id)
                if recovered:
                    self._center_object_in_frame(object_id)
                    return True, f"Navigated to {object_id}"

            # Reset for next attempt
            agent_pos = agent.get_agent_position()
            start_pos = (agent_pos["x"], agent_pos["z"])

        print(
            f"  [NAV] All candidate positions exhausted for {object_id.split('|')[0]}"
        )
        return False, f"Could not navigate to {object_id}"

    def _set_agent_rotation(self, agent, target_rotation: float):
        """Rotate the agent to face the exact target rotation."""
        agent_pos = agent.get_agent_position()
        current = agent_pos["rotation"] % 360
        target = target_rotation % 360
        diff = (target - current + 180) % 360 - 180

        if abs(diff) < 1:
            return

        rot_action = "RotateRight" if diff > 0 else "RotateLeft"
        steps = round(abs(diff) / 15)
        for _ in range(steps):
            self.controller.step(action=rot_action)

    def _set_camera_horizon(self, target_horizon: float):
        """Set the camera to the exact horizon angle."""
        current = self.controller.last_event.metadata["agent"]["cameraHorizon"]
        diff = target_horizon - current
        if abs(diff) < 1:
            return

        action = "LookDown" if diff > 0 else "LookUp"
        self.controller.step(action=action, degrees=abs(diff))

    def _set_agent_standing(self, standing: bool):
        """Set the agent to standing or crouching stance."""
        current_standing = self.controller.last_event.metadata["agent"].get(
            "isStanding", True
        )
        if current_standing == standing:
            return

        if standing:
            self.controller.step(action="Stand")
        else:
            self.controller.step(action="Crouch")

    def _vertical_recovery(self, object_id: str) -> bool:
        """Try adjusting camera horizon and stance to find the target object."""
        print(
            f"  [RECOVERY] Target {object_id.split('|')[0]} not visible. Attempting vertical recovery..."
        )

        # Strategy: Try different horizons for both standing and crouching
        horizons_to_try = [30, 60, 0, -30]
        standings_to_try = [True, False]

        agent_meta = self.controller.last_event.metadata["agent"]
        pos = agent_meta["position"]
        rot = agent_meta["rotation"]

        for standing in standings_to_try:
            for horizon in horizons_to_try:
                # Use Teleport for quick horizon/standing adjustment while keeping same position/rotation
                self.controller.step(
                    action="Teleport",
                    position=pos,
                    rotation=rot,
                    horizon=horizon,
                    standing=standing,
                )
                if self._is_object_interactable(object_id):
                    print(
                        f"  [RECOVERY] Found target at horizon {horizon} and standing={standing}!"
                    )
                    return True
        return False

    def _rotation_recovery(self, object_id: str) -> bool:
        """Try rotating in place to find the target object."""
        print(
            f"  [RECOVERY] Target {object_id.split('|')[0]} not visible. Attempting rotation recovery..."
        )

        agent_meta = self.controller.last_event.metadata["agent"]
        pos = agent_meta["position"]
        horizon = agent_meta["cameraHorizon"]
        standing = agent_meta.get("isStanding", True)

        for angle in range(0, 360, 45):
            self.controller.step(
                action="Teleport",
                position=pos,
                rotation=dict(x=0, y=angle, z=0),
                horizon=horizon,
                standing=standing,
            )
            if self._is_object_interactable(object_id):
                print(f"  [RECOVERY] Found target at rotation {angle}!")
                return True
        return False

    def _execute_path(self, agent, path, object_id: str) -> bool:
        """Walk a path. Returns True if we reach the end or the target becomes interactable."""
        agent_pos = agent.get_agent_position()

        for i, (x, z) in enumerate(path[1:], 1):
            current_x, current_z = agent_pos["x"], agent_pos["z"]

            dx = x - current_x
            dz = z - current_z

            angle = math.degrees(math.atan2(dx, dz))
            rotation_diff = (angle - agent_pos["rotation"] + 180) % 360 - 180

            if abs(rotation_diff) > 15:
                rot_action = "RotateRight" if rotation_diff > 0 else "RotateLeft"
                rot_steps = int(abs(rotation_diff) / 15)
                for _ in range(rot_steps):
                    event = self.controller.step(action=rot_action)
                    if not event.metadata["lastActionSuccess"]:
                        # Rotation blocked - try teleporting rotation in place
                        agent_meta = self.controller.last_event.metadata["agent"]
                        target_rot = (
                            agent_meta["rotation"]["y"]
                            + (15 if rotation_diff > 0 else -15)
                        ) % 360
                        event = self.controller.step(
                            action="Teleport",
                            x=agent_meta["position"]["x"],
                            y=agent_meta["position"]["y"],
                            z=agent_meta["position"]["z"],
                            rotation=dict(x=0, y=target_rot, z=0),
                        )
                        if not event.metadata["lastActionSuccess"]:
                            print(
                                f"  [NAV] Rotation blocked at step {i}, skipping to next candidate"
                            )
                            break  # break rotation loop, fall through to move
                else:
                    # All rotations succeeded - continue to move
                    pass

            event = self.controller.step(
                action="MoveAhead", moveMagnitude=self.grid_size
            )
            if not event.metadata["lastActionSuccess"]:
                # Check if target is already interactable
                if self._is_object_interactable(object_id):
                    print(
                        f"  [NAV] Movement blocked at step {i}, but target is already interactable. Proceeding."
                    )
                    return True

                # Try rotating at current position
                for _ in range(4):
                    self.controller.step(action="RotateRight", degrees=90)
                    if self._is_object_interactable(object_id):
                        print(
                            f"  [NAV] Movement blocked at step {i}, but found target after rotating. Proceeding."
                        )
                        return True

                return False  # This path failed, try next candidate

            agent_pos = agent.get_agent_position()
            print(f"  [NAV] Step {i}: ({agent_pos['x']:.2f}, {agent_pos['z']:.2f})")

        print(f"  [NAV] Arrived near {object_id.split('|')[0]}")
        return True

    def _get_object_position(self, object_id: str):
        """Get position of an object from metadata"""
        objects = self.controller.last_event.metadata["objects"]
        for obj in objects:
            if obj["objectId"] == object_id:
                pos = obj.get("position")
                if pos:
                    return (pos["x"], pos["z"])
        return None

    def get_steps_to_target(
        self, start_pos: Tuple[float, float], end_pos: Tuple[float, float]
    ) -> List[Dict]:
        """Get list of action steps to reach target (for LLM planning)"""
        path = self.find_path(start_pos, end_pos)
        if path is None:
            return []

        steps = []
        current_rotation = 0

        for i in range(len(path) - 1):
            x, z = path[i]
            next_x, next_z = path[i + 1]

            dx = next_x - x
            dz = next_z - z
            angle = math.degrees(math.atan2(dx, dz))

            rotation_diff = int((angle - current_rotation + 180) % 360 - 180)

            if abs(rotation_diff) > 15:
                rot_action = "RotateRight" if rotation_diff > 0 else "RotateLeft"
                rot_steps = abs(rotation_diff) // 15
                steps.append({"action": rot_action, "repeat": rot_steps})

            steps.append({"action": "MoveAhead", "moveMagnitude": self.grid_size})
            current_rotation = angle

        return steps
