# Tutorly

> **Understand mathematics, don't just solve it.**

Tutorly is an AI-powered mathematical explanation system. Give it a problem and (optionally) the
knowledge you are allowed to use. It parses the problem, solves it **inside your scope**, verifies the
result **independently in Python**, plans a lesson, writes narration and Manim animations, renders the
video with an **AI voiceover**, and answers your questions about any scene with **a new narrated video**.

The architecture follows *LLM2Manim: Pedagogy-Aware AI Generation of STEM Animations* (plan first,
structured scene planning, concept ledger, narration separate from visuals, constrained generation,
validation, local regeneration) and adds typed mathematical IRs, an explicit knowledge scope and
deterministic mathematical validation.

## Quick start

```bash
cp .env.example .env          # then set GEMINI_API_KEY=...
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000 (OpenAPI docs at `/docs`)

Click **Load demo problem** → **Generate lesson**. The lesson page shows pipeline progress, then the
scene list (left), the narrated Manim video (centre), scene info (right) and **Ask about this step** (bottom).
Asking a question (or pressing *Why?* / *Explain simpler* / *Give hint*) creates a follow-up video scene,
listed under the scene you asked about.

The backend image is large (~3 GB) because it contains LaTeX, FFmpeg and Manim. The first build takes a few minutes.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | — (required) | Gemini API key. `GOOGLE_API_KEY` is accepted as a fallback. Never commit it. |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Runtime model for all reasoning and generation |
| `AUTO_RENDER` | `true` | Render automatically after generation |
| `VOICEOVER` | `true` | Azure/local voiceover (`false` = silent videos) |
| `TTS_PROVIDER` | `local` | `azure`: Azure Speech with local fallback; `local`: Chatterbox with Piper fallback; `piper`: offline only |
| `MANIM_QUALITY` | `l` | `l` 480p (fast), `m` 720p, `h` 1080p |
| `RENDER_TIMEOUT_S` | `240` | Per-scene render timeout |
| `MAX_STAGE_RETRIES` | `2` | Validator-driven regenerations per stage |
| `MAX_RENDER_RETRIES` | `2` | Manim-only regenerations after a failed render |
| `DATA_DIR` | `/data` (Docker) | SQLite database + rendered media |
| `LOG_LEVEL` | `INFO` | Structured JSON logs |

Without a key the app still starts. `/api/health` reports `gemini_configured: false` and creating a lesson returns HTTP 503 with an explanation.

## Architecture

```
problem + optional scope
  → Problem Analyzer ─► ProblemIR          (Gemini, prompts/problem_analyzer.md)
  → Scope Compiler   ─► ScopeIR            (scope warning if insufficient; never silently expanded)
  → Math Reasoner    ─► SolutionIR         (scope is an INPUT to reasoning)
       ↳ MathValidator: SymPy evaluates every step + brute-force enumeration / NetworkX
       ↳ ScopeValidator: structured concept tags + bilingual lexicon scan
       ↳ on failure → regenerate the solution only, with validator feedback
  → Pedagogical Planner ─► LessonIR (ConceptLedger + SceneIR[])
       ↳ LedgerValidator; an invalid scene is regenerated alone
  → per scene (in parallel):
       Narration Generator ─► NarrationIR   (spoken text; scope-validated; regenerate narration only)
      Azure/local TTS     ─► Voiceover     (one WAV per segment; real durations replace estimates)
       Visual retrieval    ─► capabilities  (manifest subset relevant to this scene; deterministic)
       Visual Planner      ─► VisualPlan    (SEMANTIC: template + objects + beats of grammar operations)
         ↳ VisualPlanValidator (manifest + visual-quality rules); regenerate the visual plan only
       Visual compiler     ─► AnimationPlan ─► ManimCode  (deterministic, tutorly_visuals runtime)
         ↳ fallback: Gemini Manim Generator (AST allowlist; regenerate Manim only)
  → Sandboxed render ─► scene MP4s + concatenated lesson MP4
       ↳ render error → regenerate that scene's Manim code only, with stderr
  → UI → Ask about this step: question ─► Ask Tutor ─► FollowupPlan (new SceneIR + new ledger symbols)
       ↳ scope + ledger + SymPy state check; rejected plans are re-planned with feedback
       ↳ same narration → voice → visual plan → Manim → render path ─► its own follow-up video
```

### Visual design system

Lessons are built from a reusable visual library, not from free-form Manim code
(`backend/app/services/visuals/`):

- **`manifest.yaml`**: capabilities as metadata. It lists 15 templates (`problem_reveal`, `constraint_reveal`,
  `permutation_counter`, `block_method`, `case_split`, `counting_tree`, `complement_counting`, `graph_build`,
  `graph_traversal`, `highlight_path`, `formula_transform`, `before_after`, `comparison`, `spotlight`, `summary`),
  operations, object types, layouts, cameras, motion presets, emphasis roles and the visual-quality rules.
- **Retrieval** (`retrieval.py`): deterministic tag matching over the problem, solution and scene. Only the
  relevant templates reach the planner. A permutation problem never sees graph templates, and vice versa.
- **Semantic plan**: Gemini names a template, typed objects (`item`, `slot`, `region`, `arrangement`, `node`, …)
  and beats of grammar operations. Grouping → `merge`, cases → `split`/`branch`, equivalent form → `transform`,
  removal → `remove`, result → `emphasize_result`. It names semantic emphasis roles (`forbidden`, `result`, …),
  never colours, fonts, coordinates or Manim calls.
- **Validation** (`validation/visual_validator.py`): the plan must use known templates, operations and objects, and
  pass the quality rules: real visual objects, no runs of text-only beats, a mathematical operation for every
  solution step, emphasis, spatial separation for cases, transforms for formulas, visible graph-state changes,
  restricted LaTeX, no colours or fonts, and limited camera moves. Thresholds and severities are configured in the manifest.
- **Compiler** (`grammar.py`, `compiler.py`): each operation expands into motion primitives. For example
  `merge` becomes indicate → move together → enclose with a label → relayout. Timings follow the voice. The result is an
  inspectable **AnimationPlan** and a short scene that drives the runtime.
- **Runtime** (`visuals/runtime/tutorly_visuals/`): plain Manim Community code, copied into the sandbox. It contains the theme
  (all colours, fonts and strokes), primitives, layouts, camera presets, motion presets and the `Stage`. Regions whose value ends
  in a count draw that many elements, so for example the 48 forbidden arrangements are visibly carved out of 120 and removed.
- **Stereometry** (`Stage3D`, ThreeDScene): solids are built from exact coordinates (`geometry.py`) and drawn edge by edge
  while the camera orbits. Auxiliary segments, points, planes and angles are added, and `measure` labels are checked
  against the exact geometry. `flatten` lifts the key right triangle out of the solid and lays it flat beside it, so
  the computation happens next to a true-shape picture. Supported solids: cube, cuboid, prisms, pyramids, tetrahedron.
  The problem's `geometry_spec` lets Python compute the answer independently.
- **Permutation galleries**: `enumerate` shows every arrangement (or a sample). Python decides which ones break the
  constraint; those are struck through but stay readable, and the valid ones are counted.
- If a plan still fails validation after retries, the scene falls back to Gemini-written Manim code. The inspector shows
  which path each scene took.

### Voiceover

Each scene's narration is spoken by Azure or the local neural voice service, with Piper as the offline fallback.
Each segment is (written as spoken language, e.g. "pięć silnia" rather than "5!").
Synchronisation is deterministic: the Manim code marks each visual event with `# EVENT: <id>`. Inside the
sandbox each marker becomes a hook that starts that segment's clip (Manim `add_sound`). If the previous clip is
still playing, the hook first pauses the animation until it ends, and the scene waits for the last clip before
finishing. The voice therefore never overlaps or gets cut off, and Manim mixes the audio into the MP4. If TTS fails,
the scene is rendered silently and the failure is logged in the job log.

### Questions become videos

`POST /api/lessons/{id}/ask` does not return chat text. It creates a follow-up scene (`scene_3_q1`, ...) and generates
it in the background. Gemini plans one short scene answering the question, using the current scene, the ledger and
the scope. The plan must pass the scope validator and the ledger validator, and a SymPy check of the scene's own
claim (for example, *what if 6 people?* → `6! - 2*5!` must equal the stated `480`). It is then narrated, voiced,
animated and rendered like any other scene. Follow-ups never change the main lesson or its joined video.

Two roles: **Gemini** is the runtime mathematical AI. The app talks to it only through
`GeminiClient` (`backend/app/services/gemini/client.py`), which depends on a replaceable `LLMTransport`.
Every call sends the stage's Pydantic JSON schema, validates the response, and retries once with
`prompts/repair_json.md` before failing the stage with a visible error.

Everything is persisted (SQLite): IRs on `Lesson`/`Scene`, one `GenerationJob` row per LLM call or
render (model, prompt name + version, attempts, duration, error), every `ValidationResult`, and the
tutor conversation. Persistence is what makes local regeneration and retry possible.

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for components and key decisions, and
[.ai/ARCHITECTURE.md](.ai/ARCHITECTURE.md) for the repository map.

### Independent mathematical verification

The answer is never trusted from the model:

1. Each `ReasoningStep.expression` (e.g. `factorial(5)`, `total - forbidden`) is parsed by a whitelisted
   SymPy parser and evaluated. Later steps reference the *evaluated* values of earlier steps, and every
   `claimed_value` is compared.
2. The final expression must equal the claimed final value. The model's own verification checks must also hold.
3. If the analyzer formalised the problem (`enumeration_spec` for small arrangement problems,
   `graph_spec` for graphs), Python computes the answer **by brute force / NetworkX** without looking at the
   solution. For the demo it enumerates all 120 permutations of ABCDE and counts 72 with A, B not adjacent.

### Safety of generated code

Generated Manim code is untrusted:

- Static AST validation runs first: only `manim`/`math`/`numpy` imports and an allowlisted Manim subset. No `open`, `exec`, `eval`, `getattr`, `config`, dunder attributes, `while` or `with`.
- Execution happens in a fresh temp directory, in a separate `python -I` process with a scrubbed environment (no API keys).
- A PEP 578 audit hook blocks sockets, every subprocess except LaTeX/dvisvgm/FFmpeg, and writes outside the sandbox.
- The process gets a timeout, POSIX rlimits (CPU, file size, no core dumps) and truncated stdout/stderr.
- In Compose the backend runs as non-root with `cap_drop: ALL`, `no-new-privileges` and a PID limit.

## API

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/lessons` | `{problem, scope?}` → starts generation (202) |
| `GET` | `/api/lessons` | Recent lessons |
| `GET` | `/api/lessons/{id}` | Status, all IRs, scope warning, verification, latest validations, scenes |
| `GET` | `/api/lessons/{id}/scenes` | Scenes with narration, visual plan, Manim source, render status |
| `POST` | `/api/lessons/{id}/render` | `{scene_ids?}` → (re)render |
| `GET` | `/api/lessons/{id}/media` | Video URLs and render status |
| `POST` | `/api/lessons/{id}/ask` | `{scene_id, question}` → 202 `{scene_id}` of a new follow-up video scene |
| `POST` | `/api/lessons/{id}/scenes/{scene_id}/regenerate` | `{artifact: scene\|narration\|visual\|manim, instruction?}` local regeneration |
| `POST` | `/api/lessons/{id}/retry` | Resume a failed lesson, reusing valid stages |
| `GET` | `/api/lessons/{id}/jobs` | Per-stage generation log (model, prompt version, timing) |
| `GET` | `/api/lessons/{id}/messages` | Question history (questions + answer summaries) |

Lesson status: `PENDING → PLANNING → GENERATING → VALIDATING → READY → RENDERING → COMPLETED` (or `FAILED`).

## Development

Backend tests run inside the backend image, which has Manim, LaTeX and FFmpeg:

```bash
docker compose exec backend python -m pytest -q -p no:cacheprovider          # running stack
# or, against local sources:
docker build -f backend/Dockerfile -t tutorly-backend:dev .
docker run --rm -v "$PWD/backend/app:/app/app" -v "$PWD/backend/tests:/app/tests" \
  -v "$PWD/prompts:/app/prompts" tutorly-backend:dev python -m pytest -q -p no:cacheprovider
```

Unit tests mock Gemini (`backend/tests/fixtures.py`) and need no API key. The live integration test
runs only when a key is present:

```bash
docker compose exec -e GEMINI_API_KEY=... backend python -m pytest -m integration -s -p no:cacheprovider
```

Local backend without Docker (Python 3.12): `cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload`.
Frontend: `cd frontend && npm install && npm run dev`. It proxies `/api` and `/media` to `BACKEND_URL`,
which defaults to `http://localhost:8000`.

Prompts live in [`prompts/`](prompts/) with a `version:` front-matter header. Bump the version when you change one.
It is stored with every generation.

## Known limitations

- The deterministic independent check covers small arrangement problems and a few graph queries. For other
  problems, verification relies on SymPy evaluation of the model's step expressions, which checks arithmetic but not the method.
- Scope checking relies on structured concept tags plus a small EN/PL lexicon. The optional secondary Gemini semantic scope check is not implemented.
- The job runner is an in-process thread pool. Jobs interrupted by a restart are marked `FAILED` and can be resumed with *Retry*.
- Rendering is sandboxed at process level, not with a separate network-less container or seccomp profile.
- The visual library covers counting, sets, cases, trees, graphs and formula rewriting. Other topics, such as geometry or
  function plots, fall back to Gemini-written Manim code until templates exist for them.
- Follow-up videos take roughly as long as one lesson scene to produce (plan → voice → Manim → render), so they are not instant.

## Working with an agent

Start with [AGENTS.md](AGENTS.md), which links the repository rules, architecture map, and workflow
(`grill-me`, `write-spec`, `edit-spec`, `implement-task`, `prepare-draft-pr` skills under `.agents/skills/`).
