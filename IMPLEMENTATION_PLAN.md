# Tutorly — Implementation Plan

> "Understand mathematics, don't just solve it."

Tutorly turns a mathematical problem (plus an optional, user-defined knowledge
scope) into a validated, narrated, Manim-animated lesson, and lets the learner
ask a context-aware tutor about any scene.

The design follows the LLM2Manim ideas (plan first, structured scene planning,
symbol/concept ledger, narration separated from visuals, constrained generation,
validation, local regeneration) and adds explicit mathematical IRs, a
first-class knowledge scope and deterministic mathematical validation.

## 1. Architecture

```
Browser (Next.js) ──HTTP──> FastAPI backend ──> Gemini (gemini-3.5-flash)
                                 │
                                 ├── SQLite (all intermediate artifacts)
                                 ├── in-process job worker (thread pool)
                                 └── Manim sandbox (subprocess, temp dir,
                                     audit hook, timeout, output limits)
```

Two services only (`frontend`, `backend`). Redis is **not** used: SQLite stores
job state and one backend process runs a small thread pool, which is enough for
a hackathon demo and keeps the system easy to understand (see decision D4).

### Runtime pipeline

```
problem + scope
  → ProblemAnalyzer      → ProblemIR
  → ScopeCompiler        → ScopeIR        (scope warning if insufficient)
  → MathReasoner         → SolutionIR
        ↳ MathValidator (SymPy / brute-force enumeration / NetworkX)
        ↳ ScopeValidator (structured metadata + lexicon scan)
        ↳ on failure: regenerate SolutionIR only, with validator feedback
  → PedagogicalPlanner   → LessonIR (ConceptLedger + SceneIR[])
        ↳ LedgerValidator; invalid scene → regenerate that scene only
  → per scene:
        NarrationGenerator → NarrationIR   (ScopeValidator; regenerate narration only)
        VisualPlanner      → VisualPlan
        ManimGenerator     → ManimCode     (ManimValidator AST; regenerate code only)
  → Renderer (async)     → scene MP4s (+ concatenated lesson MP4)
        ↳ render failure → regenerate that scene's Manim code only
  → UI → Ask Tutor (context-aware Gemini, scope-checked)
```

## 2. Components

| Component | Path | Responsibility |
| --- | --- | --- |
| IR schemas | `backend/app/schemas/` | Pydantic v2 models for every stage |
| ORM models | `backend/app/models/` | `Lesson`, `Scene`, `GenerationJob`, `ValidationRecord`, `ConversationMessage` |
| Prompt store | `prompts/*.md`, `backend/app/services/prompts.py` | Versioned prompts with front matter |
| Gemini layer | `backend/app/services/gemini/` | `LLMTransport` protocol, `GoogleGenAITransport`, `GeminiClient` structured methods, JSON repair loop |
| Pipeline | `backend/app/services/pipeline/` | Stage orchestration, persistence, local regeneration, tutor |
| Validation | `backend/app/services/validation/` | `MathValidator`, `ScopeValidator`, `LedgerValidator`, `ManimValidator` |
| Manim | `backend/app/services/manim/` | Sandboxed render runner, video concatenation |
| Worker | `backend/app/workers/` | Background job executor |
| API | `backend/app/api/` | REST endpoints |
| Frontend | `frontend/` | Problem input page, lesson viewer, Ask Tutor |

## 3. Data flow and persistence

Every stage output is persisted as JSON on the `Lesson` (problem/scope/solution/
lesson IR) or `Scene` (scene IR, narration, visual plan, Manim source, render
logs) row. Every LLM call creates a `GenerationJob` row with `stage`, `model`,
`prompt_version`, `lesson_id`, `scene_id`, timestamps, duration, attempts and
error. Every validator run creates a `ValidationRecord`. Regeneration therefore
always reuses earlier valid stages.

Lesson status: `PENDING → PLANNING → GENERATING → VALIDATING → READY →
RENDERING → COMPLETED` (or `FAILED`). `READY` means all artifacts are generated
and validated but not yet rendered; with `AUTO_RENDER=true` (default) rendering
starts immediately.

## 4. Implementation phases

1. Schemas + deterministic pipeline skeleton (tests: schema tests).
2. Mocked Gemini transport with fixture responses (tests: pipeline with mocks).
3. Deterministic Manim scene + sandboxed renderer (tests: render pipeline).
4. Real Gemini transport (`google-genai`, structured JSON output, repair).
5. Validators wired into the pipeline with local regeneration.
6. Next.js frontend.
7. Docker + Compose.
8. End-to-end demo (requires `GEMINI_API_KEY`).

Tests are run after every phase.

## 5. Key technical decisions

- **D1 — Typed IRs everywhere.** Gemini never goes straight from text to Manim.
  Each stage receives earlier IRs as JSON and returns JSON validated by Pydantic.
- **D2 — Structured output + repair.** Calls use `response_mime_type=application/json`
  and the stage's JSON schema. Invalid output is sent back with the validation
  error using `prompts/repair_json.md`; a second failure fails the stage with a
  visible error.
- **D3 — Independent math verification.** The reasoner must emit SymPy-parsable
  expressions per step with claimed values; Python evaluates them in a
  whitelisted parser. When the ProblemIR includes an `enumeration_spec`
  (small permutation/sequence problems) or a `graph_spec`, Python additionally
  computes the answer by brute force / NetworkX, independent of the model's method.
- **D4 — No Redis.** A thread-pool worker plus job rows in SQLite. Jobs left
  running at startup are marked failed.
- **D5 — Scope is an input, not only a filter.** ScopeIR is passed to the
  reasoner, planner, narration, Manim and tutor prompts; ScopeValidator checks
  structured `concepts_used`/`methods` tags first, then a lexicon scan of prose.
- **D6 — Sandboxed Manim.** Generated code passes an AST allowlist validator,
  then runs in a subprocess with an isolated temp dir, a scrubbed environment
  (no API keys), a Python audit hook (blocks sockets, non-allowlisted
  subprocesses and writes outside the sandbox), a timeout, POSIX rlimits and
  truncated stdout/stderr — inside the backend container running as non-root.
- **D7 — Prompts as files.** `prompts/*.md` with `version:` front matter.
- **D8 — Mock transport is test-only.** No answer is hardcoded in application code;
  fixtures live under `backend/tests/`.
- **D10 — Voiceover drives timing.** Azure or local TTS produces one WAV per narration segment. The sandbox turns
  `# EVENT:` markers into hooks that start the clip and wait for the previous one, so audio and animation
  stay synchronised without trusting the LLM's timing. A TTS failure degrades to a silent scene.
- **D11 — Questions are answered with video.** Ask Tutor returns a `FollowupPlan` (a new SceneIR + new
  ledger symbols), validated for scope, ledger consistency and its own arithmetic, then rendered through
  the normal scene path as a follow-up scene that never alters the main lesson.
- **D9 — Local environment.** Docker image uses Python 3.12 as required; the
  local dev venv may use another 3.1x interpreter when 3.12 is not installed.

## 6. Visual Design System (visual-layer upgrade)

Goal: lessons should read as deliberate mathematical animation, not animated text cards, while staying
deterministic and inside the existing architecture.

What existed: Gemini `visual_planner` → `VisualPlan` (free-text events) → Gemini `manim_generator` writes the
whole scene → `ManimValidator` (AST) → sandboxed render with voiceover hooks at `# EVENT:` markers.

What changes (visual layer only, no other stage touched):

```
LessonIR / SceneIR / SolutionIR / NarrationIR (unchanged)
  → visual capability retrieval   services/visuals/retrieval.py  (deterministic tag matching over manifest.yaml)
  → semantic VisualPlan           Gemini visual_planner v2: template + typed objects + beats of grammar operations
  → VisualPlanValidator           manifest conformance + configurable visual-quality rules (retry visual plan only)
  → AnimationPlan                 services/visuals/compiler.py: grammar expands each operation into motion primitives
  → Manim source                  compiler emits a short scene that drives the tutorly_visuals runtime
  → existing ManimValidator, sandbox, voiceover hooks, renderer (unchanged path)
```

- **Library** `backend/app/services/visuals/`: `manifest.yaml` (templates, layouts, cameras, motion,
  emphasis roles, quality rules: metadata only), `manifest.py`, `retrieval.py`, `grammar.py`, `compiler.py`,
  and `runtime/tutorly_visuals/` (theme tokens, primitives, layouts, motion presets, camera presets, `Stage`).
  The runtime is plain Manim Community code, copied into the render sandbox; it never imports `app`.
- **Grammar** maps meaning to motion: new object → create, removal → remove, grouping → merge, case analysis →
  branch/split, equivalent form → transform/morph, important choice → highlight, relation → connect,
  growth → grow, comparison → compare, result → emphasize_result.
- **Design tokens**: the model may only name semantic roles (`neutral`, `secondary`, `active`, `focus`,
  `forbidden`, `result`, `transformation`); colours, fonts, stroke widths and timings live in the runtime theme.
- **Fallback**: if a plan still fails validation after retries, or compiled code fails to render, the existing
  Gemini `manim_generator` path is used, so no lesson is blocked by the library's coverage.
- **References**: Manim Community examples and storytelling patterns (establishing shot → focus → transform →
  result) inform the presets; no ManimGL (3b1b) APIs are used.

## 7. Permutation galleries and stereometry (visual-layer extension)

### Reference review (sources actually inspected)

| Source | What it offered | What Tutorly adopted |
| --- | --- | --- |
| dbillion/manim-storytelling-skills (`style/camera.py`, `style/timing.py`, `references/camera-and-scenes.md`, `references/style-guide.md`, `manim-dsa-explainer/SKILL.md`, `style/shapes3d.py`) | Concrete Manim CE cinematography: 3D resting view phi 65–75 deg / theta -45…-60 deg / zoom ~0.8, ambient orbit <= 0.12 rad/s stopped before reading beats, HUD via `add_fixed_in_frame_mobjects`, labels anchored to 3D points kept upright, wireframe "sweep reveal" with `Create`, technique grammar (`TransformFromCopy` = same idea in two representations, strikethrough = cancellation, `LaggedStart` for many similar objects), pause after each new idea | `Stage3D` camera presets and orbit rules, fixed-in-frame HUD, fixed-orientation vertex/measure labels, edge-by-edge solid reveal, `flatten` (the 3D triangle shown again flat), struck-through (never deleted) forbidden arrangements, lagged gallery reveal |
| Manim Community examples gallery (`docs/source/examples.rst`) | `ThreeDScene` camera API (`set_camera_orientation`, `move_camera`, `begin_ambient_camera_rotation`), `FixedInFrameMObjectTest`, `MovingCameraScene` following camera | exact CE APIs used by `Stage3D`; 2D focus/zoom presets already in `camera.py` |
| manim-examples.github.io | a curated index of CE tutorials/plugins (no reusable code) | confirmed CE as the target; no code taken |
| animg.app/explore | community gallery: dark minimal style, step-by-step equation transforms, side panels tracking state | right-hand "worked panel" next to the main visual (flattened triangle + formulas) |
| 3b1b/manim (`example_scenes.py`) | ManimGL APIs (`frame.reorient`, `fix_in_frame`, `TransformMatchingStrings`) | ideas only (keep matching parts during rewrites, fixed text during 3D motion); **no ManimGL API is used** |

### What was added

- `runtime/tutorly_visuals/geometry.py`: exact solids (cube, cuboid, prisms, pyramids, tetrahedron),
  derived points, distances/angles/areas/volumes with SymPy; shared by the renderer and the validators.
- `geometry_spec` in ProblemIR: Python computes stereometry answers independently (like brute force for
  permutations).
- 3D visual vocabulary: object types `solid`/`point`/`segment`/`plane`/`angle`, operations `measure` and
  `flatten`, layout `space_3d`, cameras `three_quarter`/`orbit`/`top_view`/`front_view`; templates
  `solid_reveal`, `space_construction`, `section_flatten`; runtime `Stage3D` (ThreeDScene).
- Every length/angle the plan writes on screen is compared with the exact geometry (`MEASURE_MISMATCH`).
- Permutations: `enumerate` / template `arrangement_gallery` shows every arrangement (or a sample); the
  compiler classifies them with the problem's `enumeration_spec`, so struck/valid cards are decided by Python.
