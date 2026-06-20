"""Generate the eval-reference page for the Guide.

A native MkDocs hook (configured under ``hooks:`` in mkdocs.yml), same pattern as
``gen_api_docs.py`` - no plugin, no extra dependency. The prose, the check schema
and the curated kitchen table are hand-authored here; the full list of valid
object-type *names* is generated from ``object_types.BASE_OBJECT_TYPES`` so it
can never drift from the code. ``on_pre_build`` writes ``eval-reference.md`` into
the docs dir before pages are gathered.

What the schema below documents is exactly what ``eval_runner.evaluate_check``
accepts - keep the two in sync if that function changes.
"""

import os

from genair_lab.object_types import BASE_OBJECT_TYPES

PROPERTIES = [
    ("isOpen", "The thing is open (vs closed).", "Openable"),
    ("isToggled", "The thing is switched on / running.", "Toggleable"),
    ("isSliced", "The food has been sliced.", "Sliceable"),
    ("isCooked", "The food has been cooked.", "Cookable"),
    ("isBroken", "The thing is broken.", "Breakable"),
    ("isDirty", "The thing is dirty.", "Dirtyable"),
    ("isFilledWithLiquid", "The container holds liquid.", "CanBeFilled"),
    ("isUsedUp", "A consumable has been used up.", "CanBeUsedUp"),
]

KITCHEN_TABLE = [
    ("Fridge", "`isOpen`", '`{"object": "Fridge", "property": "isOpen", "equals": true}`'),
    ("Microwave", "`isOpen`, `isToggled`", '`{"object": "Microwave", "property": "isOpen", "equals": true}`'),
    ("Cabinet", "`isOpen`", '`{"object": "Cabinet", "property": "isOpen", "equals": true}`'),
    ("Drawer", "`isOpen`", '`{"object": "Drawer", "property": "isOpen", "equals": true}`'),
    ("LightSwitch", "`isToggled`", '`{"object": "LightSwitch", "property": "isToggled", "equals": true}`'),
    ("Faucet", "`isToggled`", '`{"object": "Faucet", "property": "isToggled", "equals": true}`'),
    ("Toaster", "`isToggled`", '`{"object": "Toaster", "property": "isToggled", "equals": true}`'),
    ("CoffeeMachine", "`isToggled`", '`{"object": "CoffeeMachine", "property": "isToggled", "equals": true}`'),
    ("Bread", "`isSliced`", '`{"object": "Bread", "property": "isSliced", "equals": true}`'),
    ("Apple", "`isSliced`, `held`", '`{"object": "Apple", "property": "isSliced", "equals": true}`'),
    ("Tomato", "`isSliced`, `held`", '`{"object": "Tomato", "property": "isSliced", "equals": true}`'),
    ("Lettuce", "`isSliced`", '`{"object": "Lettuce", "property": "isSliced", "equals": true}`'),
    ("Potato", "`isSliced`, `isCooked`", '`{"object": "Potato", "property": "isCooked", "equals": true}`'),
    ("Egg", "`isBroken`, `isCooked`", '`{"object": "Egg", "property": "isBroken", "equals": true}`'),
    ("Mug", "`isFilledWithLiquid`, `held`", '`{"held": "Mug"}`'),
    ("Cup", "`isFilledWithLiquid`, `held`", '`{"object": "Cup", "property": "isFilledWithLiquid", "equals": true}`'),
    ("Knife", "`held`", '`{"held": "Knife"}`'),
]


def _columns(names, ncols=4):
    """Render a sorted name list as an HTML grid so 120 items stay compact."""
    cells = "".join(f"<code>{n}</code>" for n in names)
    return (
        f'<div class="objtype-grid" '
        f'style="display:grid;grid-template-columns:repeat({ncols},1fr);gap:.25rem .75rem">'
        f"{cells}</div>"
    )


def render() -> str:
    L = [
        "# Writing eval cases",
        "",
        "The **Eval** tab runs a list of test cases and reports a pass-rate. Each "
        "case is a **command** plus a **check** on the world *after* the robot runs "
        "it. The scene is reset before every case, so cases don't affect each other.",
        "",
        "This page is the reference for what you can put in a check. For the hands-on "
        "walkthrough, see [Task 4 - Evaluation](tutorial/task-4.md).",
        "",
        "## The format",
        "",
        "One JSON object per line (JSONL) in the Eval tab:",
        "",
        "```json",
        '{"command": "open the fridge", "check": {"object": "Fridge", "property": "isOpen", "equals": true}}',
        "```",
        "",
        "- One case per line; the line must be valid JSON.",
        "- `command` is required - the plain-English instruction, exactly as you'd type it in chat.",
        "- `check` describes the world state that means the command succeeded.",
        "- Blank lines and lines starting with `#` are ignored, so you can comment.",
        "",
        "There are two kinds of check.",
        "",
        "## Check 1 - what the robot is holding",
        "",
        "```json",
        '{"command": "pick up the apple", "check": {"held": "Apple"}}',
        '{"command": "put the mug down", "check": {"held": "nothing"}}',
        "```",
        "",
        "- `held` is an **object type name** (e.g. `Apple`, `Mug`, `Knife`). The match "
        "is on the *type*, and it is **case-sensitive** - `apple` will not match.",
        '- Use `"nothing"` (or `""`) to assert the robot\'s hands are empty.',
        "",
        "## Check 2 - a property of an object",
        "",
        "```json",
        '{"command": "open the fridge", "check": {"object": "Fridge", "property": "isOpen", "equals": true}}',
        "```",
        "",
        "- `object` is the **object type name** (case-sensitive).",
        "- `property` is one of the state properties in the table below. **Required** "
        "for this kind of check.",
        "- `equals` is the value you expect (`true` or `false`). **Optional - it "
        "defaults to `true`**, so you can drop it when checking for `true`. (`value` "
        "is accepted as an alias for `equals`.)",
        "",
        "!!! note \"'Any object of that type' wins\"",
        "    The check passes if **any** object of that type matches. A scene has "
        "several cabinets, so `{\"object\": \"Cabinet\", \"property\": \"isOpen\"}` "
        "passes as soon as *one* cabinet is open - not all of them.",
        "",
        "### Properties you can check",
        "",
        "| Property | Means | AI2-THOR capability |",
        "|----------|-------|---------------------|",
    ]
    for prop, meaning, cap in PROPERTIES:
        L.append(f"| `{prop}` | {meaning} | {cap} |")
    L += [
        "",
        "## Finding valid object names",
        "",
        "Two things matter: **spelling** and **whether it's actually in your scene**.",
        "",
        "- **Spelling / which names exist at all** - use the full catalog of type "
        "names below. Names are case-sensitive and have no spaces (`LightSwitch`, "
        "not `light switch`).",
        "- **Whether it's in *this* scene** - click the **Objects** button in the "
        "header (next to the scene name). It lists every object in the current scene "
        "by name, what you can check on each, and its **current state** - the ground "
        "truth for this scene, and the fastest way to copy a correct name into a "
        "case. (You can also equip the `list_objects` ability to have the robot "
        "report what it sees while it moves, but the Objects button shows the whole "
        "room at once.) The default scene (`FloorPlan1`) is a kitchen, so it won't "
        "contain bedroom or bathroom objects even though they're valid names.",
        "",
        "For the authoritative list of every object, which room types it appears in, "
        "and its actionable properties, see the "
        "[AI2-THOR object types page](https://ai2thor.allenai.org/ithor/documentation/objects/object-types).",
        "",
        "### Common kitchen objects and what to check",
        "",
        "A starting point for the default scene. The **Objects** button is still "
        "the final word on what's actually present.",
        "",
        "| Object | You can check | Example case `check` |",
        "|--------|---------------|----------------------|",
    ]
    for obj, checks, example in KITCHEN_TABLE:
        L.append(f"| `{obj}` | {checks} | {example} |")
    L += [
        "",
        '??? note "All valid object type names"',
        "    Generated from the code, so it can\'t drift. Not all of these exist in "
        "every scene - use the **Objects** button to see what's in yours.",
        "",
        "    " + _columns(sorted(BASE_OBJECT_TYPES)).replace("\n", "\n    "),
        "",
        "## Watch out: checks that pass for free",
        "",
        '!!! warning "A passing case isn\'t always a real one"',
        "    Some properties are **already true when the scene loads**. For example "
        "the kitchen `LightSwitch` often starts switched **on**, so a case like "
        "`{\"command\": \"turn on the light\", \"check\": {\"object\": \"LightSwitch\", "
        "\"property\": \"isToggled\", \"equals\": true}}` can pass *even if the robot "
        "did nothing*.",
        "",
        "    Before trusting a green result, check the start state (does the property "
        "already hold at step 0?). Prefer commands that flip a property from `false` "
        "to `true` - e.g. check `isOpen` on something that starts closed, or assert "
        "`equals: false` first to confirm the baseline.",
        "",
    ]
    return "\n".join(L)


def on_pre_build(config, **kwargs):
    """MkDocs hook: write eval-reference.md into the docs dir.

    Only writes when the content changed, so `mkdocs serve` doesn't loop.
    """
    out = os.path.join(config["docs_dir"], "eval-reference.md")
    new = render()
    try:
        with open(out) as f:
            if f.read() == new:
                return
    except FileNotFoundError:
        pass
    with open(out, "w") as f:
        f.write(new)
