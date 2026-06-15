# GenAIR Lab { .brand }

Teach a robot to do chores by writing prompts.
{ .lead }

You type a command in plain English, a robot tries to carry it out in a simulated
home (AI2-THOR), and you watch it on screen. When it gets something wrong, you fix
it by giving the robot more abilities and editing its system prompt. There's no
robotics code to write.

[Get started](#setup){ .md-button .md-button--primary }
[The robot's API](api-reference.md){ .md-button }

## Setup

```bash
uv sync
cp .env.example .env          # point MODEL_BASE_URL at your model server
uv run mkdocs build           # build this Guide (served at /guide)
uv run genair                 # http://localhost:8001
```

You need an OpenAI-compatible model server running, e.g. Ollama (`ollama serve`)
or llama-server. Set `MODEL_BASE_URL` and `MODEL_NAME` in `.env`, then open
<http://localhost:8001>.

## How it works

1. You type a command, e.g. *"put the apple in the fridge"*.
2. The model is given your system prompt, a list of what the robot can currently
   see, and the abilities you equipped. It picks one ability to run.
3. The simulator runs it, the robot looks again, and this repeats until the command
   is done.

The model only gets the abilities you give it. So the lab comes down to two things:
picking the right abilities and writing a prompt that uses them well.

## What you edit

| Tab | What it controls |
|-----|------------------|
| System Prompt | How the robot decides what to do. Edits take effect on the next command. |
| Abilities | What the robot can do. One `name(params) : description` per line (see [the API](api-reference.md)). |
| Eval | Test cases that check the world after a command runs and report a pass rate (Tasks 4-5). |

## Writing abilities

An ability equips one function from [the robot's API](api-reference.md) and gives
it a description the model reads:

```text
pickup(object_id) : Pick up a visible object.
open(object_id) : Open a cabinet, fridge or drawer.
```

`name` has to be an API function. The description is up to you. Start from the
[API reference](api-reference.md).

## Controls

- **Model** dropdown: swap the model while running. The **⏏** button unloads it
  from memory (Ollama only).
- **Scene** dropdown: switch floor plan. Useful for checking whether your prompt
  and abilities still work outside the kitchen you tuned them on.
- **Step delay**: slow the robot down so you can follow each action.
- **Stop**: interrupt a running command after the current step.

## Tasks

1. [First commands](tutorial/task-1.md): get a feel for the loop.
2. [Navigation](tutorial/task-2.md): let the robot move and look around.
3. [Hands](tutorial/task-3.md): open, place, toggle, slice, cook.
4. [Evaluation](tutorial/task-4.md): write test cases and get a pass rate.
5. [Compare models](tutorial/task-5.md): run the same eval across models and scenes.
