# Task 5 - Compare models

## Goal

See how much the *model* matters versus the *prompt*. Run the same eval against
different models and compare.

## How

1. Build an eval set you trust (Task 4).
2. Pick a model in the **Model** dropdown, **Run Eval**, note the pass-rate.
3. Switch model, re-run, compare. Use **⏏** to unload a model from memory between
   runs if you're tight on VRAM.

## Generalisation check

Use the **Scene** dropdown to re-run your eval on a different floor plan. If your
prompt and abilities still pass when the layout changes, they generalise. If they
only pass on FloorPlan1, you've tuned them to that one scene.
