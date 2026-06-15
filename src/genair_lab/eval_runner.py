"""Lightweight evaluation - Tasks 4 & 5.

A student writes a handful of test cases (one JSON object per line). Each case is
a command plus a check on the world AFTER the robot runs it:

    {"command": "open the fridge", "check": {"object": "Fridge", "property": "isOpen", "equals": true}}
    {"command": "pick up the apple", "check": {"held": "Apple"}}
    {"command": "turn on the light", "check": {"object": "LightSwitch", "property": "isToggled", "equals": true}}

We reset the scene before every case so they're independent, run the same loop
the chat uses, then check the result. The pass-rate is reported back to the UI.
Swap the model in the UI and re-run to compare (Task 5).
"""

import json
from typing import Callable, Dict, List

from .simple import run_command


def parse_cases(text: str) -> List[Dict]:
    """Parse JSONL text into a list of case dicts. Raises ValueError with a
    line number on the first bad line, so the UI can show a helpful message."""
    cases = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"Line {n}: not valid JSON ({e.msg})")
        if "command" not in case:
            raise ValueError(f'Line {n}: missing "command"')
        cases.append(case)
    return cases


def evaluate_check(agent, check: Dict) -> bool:
    """Return True if the world matches the case's check after running it."""
    if not check:
        return False

    # held-object check
    if "held" in check:
        held = agent.held_object.split("|")[0] if agent.held_object else None
        want = check["held"]
        return held is None if want in (None, "", "nothing") else held == want

    # object-property check (passes if ANY object of that type matches)
    if "object" in check:
        obj_type = check["object"]
        prop = check.get("property")
        expected = check.get("equals", check.get("value", True))
        for o in agent.get_all_objects():
            if o["name"] == obj_type or obj_type in o["id"]:
                if o.get(prop) == expected:
                    return True
        return False

    return False


def run_eval(
    cases: List[Dict],
    *,
    agent,
    make_executor: Callable,
    abilities,
    llm: Callable,
    system_prompt: str,
    scene: str,
    emit: Callable = lambda *a, **k: None,
    should_stop: Callable = lambda: False,
    max_steps: int = 12,
    step_delay: float = 0.5,
) -> Dict:
    """Run every case (resetting the scene between them) and report the score.

    Must be called on the robot worker thread (it drives the simulator).
    """
    results = []
    total = len(cases)
    emit(
        "EVAL_STARTED",
        f"Running {total} case(s) with the current model & prompt…",
        {"total": total},
    )

    for i, case in enumerate(cases, 1):
        if should_stop():
            emit("EVAL_STOPPED", f"Stopped after {i - 1}/{total} case(s).")
            break
        command = case["command"]
        # fresh scene so cases don't contaminate each other
        agent.controller.reset(scene=scene)
        agent.held_object = None
        executor = make_executor()

        emit("EVAL_CASE_STARTED", command, {"index": i, "total": total})
        try:
            run_command(
                command,
                agent=agent,
                executor=executor,
                abilities=abilities,
                llm=llm,
                system_prompt=system_prompt,
                emit=emit,
                should_stop=should_stop,
                max_steps=max_steps,
                step_delay=step_delay,
            )
            passed = evaluate_check(agent, case.get("check", {}))
        except Exception as e:
            emit("ERROR", f"Eval case failed to run: {e}")
            passed = False

        results.append(
            {"command": command, "pass": passed, "check": case.get("check", {})}
        )
        emit("EVAL_CASE_DONE", command, {"index": i, "total": total, "pass": passed})

    n_pass = sum(1 for r in results if r["pass"])
    rate = round(100 * n_pass / total) if total else 0
    emit(
        "EVAL_DONE",
        f"{n_pass}/{total} passed ({rate}%)",
        {"passed": n_pass, "total": total, "rate": rate, "results": results},
    )
    return {"passed": n_pass, "total": total, "rate": rate, "results": results}
