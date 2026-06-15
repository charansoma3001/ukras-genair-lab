# Feature log

Append-only, one line per change. Newest at bottom.

- 2026-05-30 - Scaffolded repo; ported AI2-THOR engine (agent/navigator/parser/action_knowledge/object_types) from ai2thor-lab.
- 2026-05-30 - M1: transparent loop (`simple.py`) + FastAPI server (MJPEG video, SSE events, chat) + web dashboard. Verified end-to-end on macOS.
- 2026-05-30 - M2/M3: in-UI eval (Tasks 4–5) - `eval_runner.py`, `/eval/*`, Eval tab, model dropdown from `/models`, prompt export/import.
- 2026-05-30 - Added Stop button (`/stop` + `should_stop` in loop/eval).
- 2026-05-30 - Containment-aware observation: scene inventory tells the model which container holds each item (no blind search).
- 2026-05-30 - UI: split web into index/styles/app, Powers palette panel, removed scene dropdown, fixed Reset (→ /reset).
- 2026-05-30 - Gamified Abilities system: `powers.py` palette + `abilities.py` DSL (`name(params) -> POWER : desc`), `/powers` + `/abilities`, Abilities tab with click-to-equip. Model receives only equipped abilities.
- 2026-05-30 - Polish: powers tiles as tinted auto-grid chips (single-line signatures); `finish` collapsed to one TASK_COMPLETE line.
