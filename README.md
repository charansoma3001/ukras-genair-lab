# GenAIR Lab

A teaching lab built on [AI2-THOR](https://ai2thor.allenai.org/). You type a command, a robot tries to carry it out in a simulated home, and you watch it on screen. When it misunderstands you, you fix it by giving it more abilities and editing its system prompt.

Built for the UK RAS Summer School, following the GenAIR Tasks 1-5 on small local models (Qwen2.5-1.5B, Gemma3-4B) via Ollama or any OpenAI-compatible endpoint.

## Requirements

- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A model server. Ollama is the easiest option.
- macOS (Intel or Apple Silicon) or Linux x86_64. On Apple Silicon, AI2-THOR runs its Intel build under Rosetta, so install Rosetta once if you haven't: `softwareupdate --install-rosetta --agree-to-license`.
- Windows: AI2-THOR has no native build for this version, so run the lab inside [WSL2](https://learn.microsoft.com/windows/wsl/install) (Ubuntu), which is Linux x86_64.

## Quick start

Start a model server and pull the default model:

```bash
ollama serve                       # in one terminal
ollama pull granite4.1:3b
```

Pull the repository

```bash
git clone https://github.com/charansoma3001/ukras-genair-lab.git
cd ukras-genair-lab 
```

Then run the lab:

```bash
uv venv
source .venv/bin/activate
uv sync
cp .env.example .env               # edit if your model server isn't on localhost
uv run mkdocs build                # build the Guide (served at /guide)
uv run genair                      # serves http://localhost:8001
open http://localhost:8001 in your browser
```

The first run downloads the AI2-THOR scene build (a few minutes, once). After that it opens in about 6 seconds. Go to http://localhost:8001, type something like *"pick up the apple"*, and watch.

## The Guide

The 📖 link in the header opens the Guide (`/guide`), a MkDocs site with everything students need:

- A walkthrough of Tasks 1-5.
- An API reference listing the robot's capabilities, generated from the code so it stays in sync.

Rebuild it with `uv run mkdocs build`.

## What you edit

Three tabs in the UI, each backed by a file:

- System Prompt (`prompts/system_prompt.txt`): how the robot behaves.
- Abilities (`prompts/abilities.txt`): the actions you give it, one per line as `name(params) : description`, where `name` is an API function.
- Eval (`tasks/eval_cases.jsonl`): test cases. Run Eval for a pass rate, then swap the model in the dropdown and re-run to compare.

Each tab has a "Reset to default" button. The defaults live in `src/genair_lab/default_*`.

## The loop

The whole thing is in [`src/genair_lab/simple.py`](src/genair_lab/simple.py):

1. Build the messages: system prompt, what the robot sees, and your command.
2. Ask the model to pick one ability.
3. Run it in the simulator.
4. Show the model the new observation.
5. Repeat until the model calls `finish`, hits the step limit, or you press Stop.

## Config (`.env`)

| Variable | Meaning | Default |
|---|---|---|
| `MODEL_BASE_URL` | OpenAI-compatible endpoint | `http://localhost:11434/v1` |
| `MODEL_NAME` | model sent in each request | `qwen2.5:1.5b` |
| `MODEL_API_KEY` | any non-empty string for Ollama/llama-server | `ollama` |
| `SCENE` | AI2-THOR floor plan | `FloorPlan1` |
| `STEP_DELAY` | seconds between actions, so you can watch | `1.0` |
| `MAX_STEPS` | give up after this many model turns | `12` |
| `THINK` | enable a reasoning-model thinking pass | `true` |

## Docker (work in progress)

There's a `linux/amd64` image for running on x86_64 servers, but it isn't the recommended path yet, so use the local `uv run genair` route above. The image won't run on Apple Silicon (there's no arm64 AI2-THOR build, and emulation stalls on the Unity render), so it only helps x86_64 hosts.
