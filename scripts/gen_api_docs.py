"""Generate the API-reference page from the live powers registry.

A native MkDocs hook (configured under ``hooks:`` in mkdocs.yml) - no plugin, no
extra dependency. ``on_pre_build`` runs before pages are gathered, writing
``api-reference.md`` into the docs dir so it's always in sync with the code. The
robot's API == the canonical functions in ``powers.POWERS_LIST``; an ability
equips one of these and gives it a description.
"""

import os

from genair_lab.powers import POWERS_LIST, signature

GROUP_BLURB = {
    "MOVE": "Get the robot around the room and aim its camera.",
    "INTERACT": "Use the robot's hands: pick up, place, open, toggle, and more. "
    "The robot must be **close to** and **able to see** the target.",
    "SENSE": "Look things up without changing the world.",
    "DONE": "Signal that the command is complete.",
}

# Order groups the way a student meets them in the tutorial.
GROUP_ORDER = ["MOVE", "INTERACT", "SENSE", "DONE"]


def render() -> str:
    lines = [
        "# The robot's API",
        "",
        "These are the functions the robot understands. Each one is a **capability** "
        "you can equip as an *ability* in the **Abilities** tab, using:",
        "",
        "```text",
        "name(params) : description",
        "```",
        "",
        "- `name` must be one of the functions below.",
        "- `description` is yours to write - it's the natural language the model reads "
        "to decide *when* to use the ability.",
        "- The model can only use the abilities you list. Equip more to do more.",
        "",
        '!!! tip "Reaching things"',
        "    To act on an object the robot must be **close to it** and **able to see "
        "it**. If it isn't visible, `navigate_to` it first.",
        "",
    ]

    by_group = {}
    for p in POWERS_LIST:
        by_group.setdefault(p.group, []).append(p)

    for group in GROUP_ORDER + [g for g in by_group if g not in GROUP_ORDER]:
        powers = by_group.get(group, [])
        if not powers:
            continue
        lines.append(f"## {group.title()}")
        lines.append("")
        if group in GROUP_BLURB:
            lines.append(GROUP_BLURB[group])
            lines.append("")
        for p in powers:
            lines.append(f"### `{signature(p)}`")
            lines.append("")
            lines.append(p.description)
            lines.append("")
            if p.params:
                lines.append("| Parameter | Type | Required |")
                lines.append("|-----------|------|----------|")
                for q in p.params:
                    lines.append(
                        f"| `{q.name}` | {q.type} | {'yes' if q.required else 'no'} |"
                    )
                lines.append("")
            lines.append("Equip it like this:")
            lines.append("")
            lines.append("```text")
            lines.append(f"{signature(p)} : {p.description}")
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def on_pre_build(config, **kwargs):
    """MkDocs hook: write the generated API reference into the docs dir.

    Only writes when the content actually changed - otherwise `mkdocs serve`
    sees the file touch, rebuilds, writes again, and loops forever.
    """
    out = os.path.join(config["docs_dir"], "api-reference.md")
    new = render()
    try:
        with open(out) as f:
            if f.read() == new:
                return
    except FileNotFoundError:
        pass
    with open(out, "w") as f:
        f.write(new)
