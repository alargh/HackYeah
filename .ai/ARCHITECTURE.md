# Repository Architecture

## Current state

The repository contains **Tutorly**, an AI-powered mathematical explanation system (MVP), plus the shared agent workflow.

| Area | Current decision |
| --- | --- |
| Product | Problem + optional knowledge scope → verified Manim lesson with AI voiceover; learner questions are answered with new follow-up videos |
| Demo scenario | 5 people A–E in a row, A and B not adjacent (answer verified as 72), with scope "Use only permutations, factorials and the multiplication rule." |
| Runtime AI | Gemini (`gemini-3.5-flash`, configurable via `GEMINI_MODEL`) through `google-genai`; voiceover via Azure Speech or local voices |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy + SQLite, SymPy, NetworkX, Manim CE |
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS 3 |
| Jobs | In-process thread pool; state in SQLite (no Redis) |
| Deployment | `docker compose up --build` (services `backend`, `frontend`) |

Design rationale and decisions: [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md).

## Repository map

| Path | Purpose |
| --- | --- |
| `prompts/` | Versioned Gemini prompts (front matter `version:`) |
| `backend/app/schemas/` | Typed IRs: `ProblemIR`, `ScopeIR`, `SolutionIR`, `LessonIR`/`SceneIR`/`ConceptLedger`, `NarrationIR`, `VisualPlan`, `ManimCode`, `FollowupPlan`, `Voiceover`, `ValidationResult`, `LessonStatus` |
| `backend/app/models/` | ORM: `Lesson`, `Scene`, `GenerationJob`, `ValidationRecord`, `ConversationMessage` |
| `backend/app/services/gemini/` | `LLMTransport` protocol, `GoogleGenAITransport`, `GeminiClient` (structured calls + JSON repair) |
| `backend/app/services/pipeline/` | `LessonPipeline` orchestration, local regeneration, tutor; `store.py` persistence |
| `backend/app/services/validation/` | `MathValidator` (SymPy, brute force, NetworkX), `ScopeValidator`, `LedgerValidator`, `ManimValidator` |
| `backend/app/services/tts.py` | `SpeechSynthesizer` protocol and Azure/local voice implementations (voiceover WAVs) |
| `backend/app/services/visuals/` | Visual design system: `manifest.yaml`, retrieval, grammar, compiler, `runtime/tutorly_visuals` (theme, primitives, layouts, camera, motion, `Stage` 2D, `Stage3D` stereometry, exact `geometry`) |
| `backend/app/services/manim/` | Sandboxed renderer (`sandbox_runner.py`: audit hook + voiceover hooks at `# EVENT:` markers) and FFmpeg concat |
| `backend/app/api/routes.py` | REST API |
| `backend/app/workers/jobs.py` | Background job runner and restart recovery |
| `backend/tests/` | Unit tests with a fake Gemini transport, real render tests, optional live integration test |
| `frontend/app/` | `/` problem input, `/lessons/[id]` lesson viewer |
| `frontend/components/` | Scene list, scene info, Ask Tutor, IR inspector, progress |
| `docker-compose.yml` | Stack definition |
| `AGENTS.md`, `.agents/skills/`, `.ai/` | Shared agent workflow |

## Data flow

`POST /api/lessons` → job → `LessonPipeline.run_generation`: analyze → compile scope → reason (+math/scope
validation, solution-only retries) → plan lesson (+ledger/scope validation, per-scene retries) → per scene
narration → voice → visual retrieval → semantic visual plan (+visual validation) → compiled Manim code (Gemini fallback, +AST validation) → render (Manim-only retries on failure) → concat.
Voiceover is synthesised after narration and before the visual plan, so real clip durations pace the animation.
`POST /ask` → `create_followup` (Scene row, `kind=followup`) → job `generate_followup`: Ask Tutor plans a
`FollowupPlan` → scope/ledger/SymPy validation (re-plan on failure) → the same per-scene path → its own video.
Every stage output is stored before the next stage starts.

## Commands

| Task | Command |
| --- | --- |
| Run stack | `docker compose up --build` |
| Backend tests | `docker compose exec backend python -m pytest -q -p no:cacheprovider` |
| Live Gemini test | `docker compose exec -e GEMINI_API_KEY=... backend python -m pytest -m integration -s -p no:cacheprovider` |
| Frontend build | `cd frontend && npm install && npm run build` |
