# GenAIR Lab

This is a teaching lab built on [AI2-THOR](https://ai2thor.allenai.org/). You will be able to type  commands for  a generative AI model, which will  try to execute your commands in a simulated home, and you will watch the effects on screen. If the model misunderstands you, you can improve it by giving it more abilities and editing the system prompt.

This Lab is Built for the UK RAS Summer School, and can be run using Ollama or any OpenAI-compatible endpoint.

## Step 1: Requirements

- Install [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Install a model server. [Ollama](https://ollama.com/) is the easiest option ('curl -fsSL https://ollama.com/install.sh | sh`)
- For macOS (Intel or Apple Silicon) or Linux x86_64. On Apple Silicon, AI2-THOR runs its Intel build under Rosetta, so please install Rosetta once if you haven't: `softwareupdate --install-rosetta --agree-to-license`.
- If you are using Windows: AI2-THOR has no native build for this version, so please run the lab inside [WSL2](https://learn.microsoft.com/windows/wsl/install) (Ubuntu), which is Linux x86_64.

## Step 2: Quick start

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

The first run downloads the AI2-THOR scene build (this takes a few minutes, once). After that it opens in about 6 seconds. On a web browser, go to http://localhost:8001, type something like *"pick up the apple"*, and watch.

## Step 3: The Guide and Tasks 1-5

The 📖 link in the header opens the Guide (`/guide`), a MkDocs site with everything students need:

- A walkthrough of Tasks 1-5.
- An API reference listing the robot's capabilities, generated from the code so that it stays in sync.

(You can rebuild it with `uv run mkdocs build`)

## Step 4: What you can edit

There are three tabs in the UI, each backed by a file:

- System Prompt (`prompts/system_prompt.txt`): gives instrictions to the model how it should behave overall.
- Abilities (`prompts/abilities.txt`): the robot actions  that you can give to the model, one per line as `name(params) : description`, where `name` is an API function.
- Eval (`tasks/eval_cases.jsonl`): test cases. Here you can define evaluations to test that the model behaves as desired, compute a pass rate, andthen then swap the model in the dropdown and re-run to compare.

Each tab has a "Reset to default" button. The defaults live in `src/genair_lab/default_*`.



## Config (`.env`)

| Variable | Meaning | Default |
|---|---|---|
| `MODEL_BASE_URL` | OpenAI-compatible endpoint | `http://localhost:11434/v1` |
| `MODEL_NAME` | model sent in each request | `granite4.1:3b` |
| `MODEL_API_KEY` | any non-empty string for Ollama/llama-server | `ollama` |
| `SCENE` | AI2-THOR floor plan | `FloorPlan1` |
| `STEP_DELAY` | seconds between actions, so that you can watch the animation | `1.0` |
| `MAX_STEPS` | give up after this many model turns | `12` |
| `THINK` | enable a reasoning-model thinking pass | `true` |

## Docker (work in progress)

There's a `linux/amd64` image for running on x86_64 servers, but it isn't the recommended path yet, so use the local `uv run genair` route above. The image won't run on Apple Silicon (there's no arm64 AI2-THOR build, and emulation stalls on the Unity render), so it only helps x86_64 hosts.
