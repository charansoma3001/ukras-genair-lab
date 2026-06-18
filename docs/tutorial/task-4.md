# Task 4 - Evaluation

## Goal

Stop eyeballing it. Write **test cases** that check the state of the world after
a command runs, and get a pass-rate.

## How cases look

One JSON object per line in the **Eval** tab. Each is a command plus a check on
the world afterwards:

```json
{"command": "open the fridge", "check": {"object": "Fridge", "property": "isOpen", "equals": true}}
```

## Try this

- Write 5-10 cases covering the commands you worked on in Tasks 1-3.
- Click **Run Eval** and read the pass-rate. The scene resets between cases.
- A failing case is a precise bug report - fix the prompt or abilities and re-run.
