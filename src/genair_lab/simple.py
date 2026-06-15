"""The main loop.

    1. Build the messages: the system prompt, what the robot sees, and the
       user's command.
    2. Ask the model to choose one tool to run next.
    3. Run it in the simulator.
    4. Show the model the new observation.
    5. Repeat until the model calls `finish` or we hit the step limit.

If the robot misunderstands a command, the fix is usually in the system prompt.
"""

import json
import time
from typing import Callable, Dict


def run_command(
    command: str,
    *,
    agent,
    executor,
    abilities,
    llm: Callable,
    system_prompt: str,
    emit: Callable = lambda *a, **k: None,
    should_stop: Callable = lambda: False,
    max_steps: int = 12,
    step_delay: float = 1.0,
    history=(),
) -> Dict:
    """Drive the robot to carry out one natural-language command.

    Args:
        command:        what the user typed.
        agent:          the AI2-THOR Agent (gives us observations).
        executor:       ToolExecutor that runs one tool in the simulator.
        llm:            OpenAI-compatible client callable (messages, tools) -> response.
        system_prompt:  the editable prompt that teaches the model how to behave.
        emit:           callback(event_type, message, data) for the live UI.
        max_steps:      give up after this many model turns.
        abilities:      the AbilitySet the student equipped (defines the tools).
        step_delay:     pause between actions so a human can watch them happen.
        history:        compact one-line recaps of earlier commands this session,
                        so the robot remembers what it just did (e.g. "put it back").

    Returns a result dict that includes a ``summary`` - a one-line recap of this
    command, to be appended to ``history`` for the next one.
    """
    tools = abilities.schemas()
    if not tools:
        emit("ERROR", "No abilities equipped - add some in the Abilities tab.")
        return {"success": False, "steps": 0, "no_abilities": True}

    # Durable context: what happened earlier this session + where things are +
    # the command. Observations are added separately (below) so we can prune the
    # stale ones before each model call.
    recap = ""
    if history:
        recap = (
            "Earlier this session (most recent last):\n"
            + "\n".join(f"  - {h}" for h in history)
            + "\n\n"
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"{recap}"
                f"{_scene_inventory(agent)}\n\n"
                f"User command: {command}\n\n"
                "Choose one action at a time. Call `finish` when the command is done."
            ),
        },
    ]

    # Track which messages are observations (newest last). The model is stateless
    # so we resend the conversation every turn - but an observation from 8 steps
    # ago describes a room that has since changed. We keep the action trail intact
    # (so it remembers what it tried) and collapse all but the latest observation.
    obs_indices = []

    def observe():
        messages.append({"role": "user", "content": agent.get_context_description()})
        obs_indices.append(len(messages) - 1)

    observe()  # first look around

    # Successful actions, kept for the next command's memory.
    trail = []

    def summary(status):
        acts = "; ".join(trail) if trail else "no actions"
        return f'"{command}" -> {acts} ({status})'

    for step in range(1, max_steps + 1):
        # 0. Let the user interrupt between steps.
        if should_stop():
            emit("TASK_STOPPED", "Stopped by user.")
            return {
                "success": False,
                "steps": step,
                "stopped": True,
                "summary": summary("stopped by user"),
            }

        # 1. Ask the model what to do next (with stale observations pruned).
        try:
            response = llm(
                _prune(messages, obs_indices),
                tools,
                on_thinking_done=lambda: emit("THINKING_DONE", ""),
            )
            msg = response.choices[0].message
        except Exception as e:
            emit("ERROR", f"Model call failed: {e}")
            return {"success": False, "steps": step, "error": str(e)}

        # 2. If the model just talked (no tool), relay it and stop.
        if not msg.tool_calls:
            text = (msg.content or "").strip() or "(the model returned no action)"
            emit("ROBOT_SPEECH", text)
            return {
                "success": True,
                "steps": step,
                "talked": True,
                "summary": summary(f"said: {text[:80]}"),
            }

        # Record the assistant turn (must precede its tool results in the history).
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        # 3. Run each tool the model chose this turn.
        finished = False
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            is_finish = abilities.tool_of(name) == "finish"
            if not is_finish:
                emit(
                    "STEP_STARTED",
                    f"{name}({_fmt_args(args)})",
                    {"step": step, "tool": name, "arguments": args},
                )

            result = abilities.execute(executor, name, args)
            time.sleep(step_delay)  # let the human see it

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(result),
                }
            )

            if is_finish:
                # one line, not three - finish is the task result, not a step
                emit("TASK_COMPLETE", result["message"])
                finished = True
            elif result["success"]:
                emit("STEP_COMPLETED", result["message"], {"step": step, "tool": name})
                trail.append(f"{name}({_fmt_args(args)})")
            else:
                emit("STEP_FAILED", result["message"], {"step": step, "tool": name})

        if finished:
            return {"success": True, "steps": step, "summary": summary("done")}

        # 4. Show the model the updated observation for the next turn.
        observe()

    emit("TASK_FAILED", f"Stopped after {max_steps} steps without calling finish.")
    return {
        "success": False,
        "steps": max_steps,
        "summary": summary("gave up at the step limit"),
    }


def _prune(messages, obs_indices):
    """Return the history to send the model, with stale observations collapsed.

    We resend the whole conversation each turn (the API is stateless), but only
    the LATEST observation reflects the room as it is now - older ones describe a
    room that has since moved on, so they just burn context and can confuse the
    model. We keep the system prompt, the command, and the full action trail (so
    it remembers what it already tried), and replace every observation except the
    most recent with a one-liner.
    """
    if len(obs_indices) <= 1:
        return messages
    stale = set(obs_indices[:-1])
    return [
        {"role": "user", "content": "[earlier observation omitted]"}
        if i in stale
        else m
        for i, m in enumerate(messages)
    ]


def _scene_inventory(agent) -> str:
    """Summarise the room so the model knows where things are - like a robot that
    remembers its own home.

    The key trick (mirrors the original ai2thor-lab planner): for each item, look at
    its ``parentReceptacles``. If it sits inside an OPENABLE container, tell the model
    exactly which container holds it, with that container's id. The model can then go
    straight to the right cupboard and open it - no blind searching.
    """
    objs = agent.get_all_objects()
    by_id = {o["id"]: o for o in objs}

    def container_of(o):
        for p in o.get("parentReceptacles") or []:
            c = by_id.get(p, {})
            if c.get("openable") and c.get("receptacle"):
                return p
        return None

    items, seen = [], set()
    for o in sorted(objs, key=lambda x: x.get("distance", 9999)):
        if not o.get("pickupable") or o["name"] in seen:
            continue
        seen.add(o["name"])
        cid = container_of(o)
        label = (
            f"{o['name']} (id: {o['id']}, inside {cid})"
            if cid
            else f"{o['name']} (id: {o['id']})"
        )
        items.append(label)

    # Deduplicate by name, keeping the closest instance for nav purposes.
    def dedup_by_name(seq):
        seen_names, result = {}, []
        for o in sorted(seq, key=lambda x: x.get("distance", 9999)):
            if o["name"] not in seen_names:
                seen_names[o["name"]] = True
                result.append(o)
        return result

    surface_objs = dedup_by_name(
        [o for o in objs if o.get("receptacle") and not o.get("openable")]
    )
    toggle_objs = dedup_by_name([o for o in objs if o.get("toggleable")])
    container_objs = dedup_by_name(
        [o for o in objs if o.get("openable") and o.get("receptacle")]
    )

    surfaces = sorted(f"{o['name']} (id: {o['id']})" for o in surface_objs)
    toggles = sorted(f"{o['name']} (id: {o['id']})" for o in toggle_objs)
    containers = sorted(f"{o['name']} (id: {o['id']})" for o in container_objs)

    lines = []
    if items:
        lines.append(
            'Items in this room (with their location - "inside X" means open container X first):'
        )
        lines.append("  " + ", ".join(sorted(items)))
    if containers:
        lines.append("Openable containers (go to, then open): " + ", ".join(containers))
    if surfaces:
        lines.append("Surfaces you can place things on: " + ", ".join(surfaces))
    if toggles:
        lines.append("Toggleable objects: " + ", ".join(toggles))
    return "\n".join(lines)


def _fmt_args(args: Dict) -> str:
    """Arg preview for the UI, e.g. object_id=Cabinet|-01.85|+02.02|+00.38."""
    return ", ".join(f"{k}={v}" for k, v in args.items())
