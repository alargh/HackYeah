export type LessonStatus =
  | "PENDING"
  | "PLANNING"
  | "GENERATING"
  | "VALIDATING"
  | "READY"
  | "RENDERING"
  | "COMPLETED"
  | "FAILED";

export interface LedgerEntry {
  symbol: string;
  meaning: string;
  kind: string;
  introduced_in: string;
  value?: string | null;
}

export interface SceneIR {
  scene_id: string;
  title: string;
  learning_goal: string;
  concepts: string[];
  solution_steps: string[];
  introduces: string[];
  uses: string[];
  mathematical_state: { known_facts: string[]; current_expression?: string | null; current_value?: string | null };
  narration_plan: string[];
  visual_plan: string[];
  duration_estimate: number;
  dependencies: string[];
}

export interface NarrationSegment {
  id: string;
  text: string;
  visual_event: string;
  concepts: string[];
}

export interface Voiceover {
  model: string;
  voice: string;
  segments: { id: string; visual_event: string; duration: number }[];
}

export interface Scene {
  scene_id: string;
  order: number;
  title: string;
  kind: "main" | "followup";
  parent_scene_id?: string | null;
  question?: string | null;
  followup?: { answer_summary: string; concepts_used: string[]; stays_in_scope: boolean } | null;
  voiceover?: Voiceover | null;
  status: string;
  error?: string | null;
  scene_ir?: SceneIR | null;
  narration?: { scene_id: string; segments: NarrationSegment[] } | null;
  visual_plan?: {
    template: string;
    secondary_templates: string[];
    layout: string;
    camera: string;
    objects: { id: string; type: string; value: string; emphasis: string }[];
    beats: { id: string; purpose: string; actions: { operation: string; targets: string[] }[] }[];
  } | null;
  visual_meta?: { retrieved_templates?: string[]; tags?: string[]; valid?: boolean; code_source?: "compiled" | "gemini" } | null;
  animation_plan?: { steps: { beat: string; primitive: string; targets: string[]; run_time: number }[] } | null;
  manim_code?: { class_name: string; code: string } | null;
  render_status: string;
  render_attempts: number;
  render_stderr?: string | null;
  video_url?: string | null;
  regeneration_count: number;
}

export interface ScopeIR {
  user_scope_text?: string | null;
  mode: "open" | "restricted";
  allowed_concepts: string[];
  forbidden_concepts: string[];
  allowed_methods: string[];
  forbidden_methods: string[];
  scope_sufficient: boolean;
  missing_concepts: string[];
  explanation: string;
}

export interface ReasoningStep {
  id: string;
  goal: string;
  method: string;
  expression?: string | null;
  claimed_value?: string | null;
  explanation: string;
  why_valid: string;
  concepts_used: string[];
}

export interface SolutionIR {
  selected_method: string;
  steps: ReasoningStep[];
  final_result: { expression: string; value: string; statement: string };
  verification: { strategy: string };
  concepts_used: string[];
}

export interface ValidationOut {
  validator: string;
  target: string;
  scene_id?: string | null;
  passed: boolean;
  issues: { code: string; message: string; severity: string; location?: string | null }[];
  details: Record<string, unknown>;
}

export interface Lesson {
  id: string;
  status: LessonStatus;
  current_stage?: string | null;
  error?: string | null;
  problem_text: string;
  scope_text?: string | null;
  problem_ir?: Record<string, unknown> | null;
  scope_ir?: ScopeIR | null;
  scope_warning?: { scope_sufficient: boolean; missing_concepts: string[]; explanation: string } | null;
  solution_ir?: SolutionIR | null;
  lesson_ir?: { title: string; learning_objectives: string[]; concept_ledger: { entries: LedgerEntry[] } } | null;
  math_verified?: boolean | null;
  verified_value?: string | null;
  render_quality?: string | null;
  video_url?: string | null;
  scenes: Scene[];
  followups: Scene[];
  validations: ValidationOut[];
}

export interface LessonSummary {
  id: string;
  created_at: string;
  status: LessonStatus;
  problem_text: string;
  title?: string | null;
}

export interface AskResponse {
  scene_id: string;
  parent_scene_id: string;
  status: string;
}

export interface ChatReply {
  answer: string;
  suggest_video: boolean;
  video_reason: string;
}

export interface ChatMessage {
  role: "user" | "tutor";
  scene_id?: string | null;
  content: string;
  payload?: {
    followup_scene_id?: string;
    kind?: string;
    suggest_video?: boolean;
    video_reason?: string;
    question?: string;
  } | null;
}

export interface Timings {
  lesson_id: string;
  status: string;
  total_s: number;
  phases: Record<string, number>;
  stages: { stage: string; calls: number; total_s: number; max_s: number; failed: number }[];
}

export interface Job {
  stage: string;
  scene_id?: string | null;
  status: string;
  model?: string | null;
  prompt_name?: string | null;
  prompt_version?: string | null;
  attempts: number;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  error?: string | null;
}
