"""Standalone generator for the Tutorly pitch deck.

Standard library only:  python generate_presentation.py [assets_dir] [output.html]
Embeds the screenshots from presentation-assets/ (base64) into ONE self-contained HTML file:
presentation-assets/tutorly_presentation.html. A missing image becomes a labelled placeholder.

In the browser: → / Space / click = next, ← = back, Home / End, F = fullscreen, P = print to PDF (one slide per page).
"""

import base64
import html
import mimetypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "presentation-assets"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ASSETS / "tutorly_presentation.html"


# ----------------------------------------------------------------------------------------------- building blocks
def img(name: str, alt: str, cls: str = "shot") -> str:
    path = ASSETS / name
    if not path.exists():
        return f'<div class="{cls} placeholder"><span>📷 {html.escape(alt)}</span><small>{html.escape(name)}</small></div>'
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img class="{cls}" src="data:{mime};base64,{data}" alt="{html.escape(alt)}">'


def browser(inner: str, url: str = "localhost:3000") -> str:
    return (f'<div class="browser"><div class="bar"><i></i><i></i><i></i><span>{url}</span></div>'
            f'<div class="viewport">{inner}</div></div>')


def bullets(items: list[str], icon: str = "✓") -> str:
    return '<ul class="bullets">' + "".join(f'<li><b>{icon}</b><span>{i}</span></li>' for i in items) + "</ul>"


def chips(items: list[str], cls: str = "") -> str:
    return '<div class="chips">' + "".join(f'<code class="chip {cls}">{i}</code>' for i in items) + "</div>"


def kicker(text: str, color: str = "blue") -> str:
    return f'<div class="kicker {color}">{text}</div>'


# ----------------------------------------------------------------------------------------------- slides
SLIDES: list[str] = []

# 1 · title
SLIDES.append(f"""
<section class="slide hero">
  <div class="hero-text">
    <div class="logo">Tutorly</div>
    <h1>Where Visual Learners Finally Understand the <em>Why</em></h1>
    <p class="lead">Most tools give students an answer. Tutorly delivers a <strong>verified, visual, narrated lesson</strong> —
    so learners understand the method, the formula's origin, and how to check their own work.</p>
    <div class="pills"><span>🧠 Gemini-powered</span><span>✓ verified by Python</span><span>🎬 animated</span><span>🔊 narrated</span></div>
  </div>
  <div class="hero-shot">{browser(img("initial ui.png", "Tutorly start screen"))}</div>
</section>""")

# 2 · solid geometry example
SLIDES.append(f"""
<section class="slide split">
  <div class="col text">
    {kicker("Example 1 · Solid Geometry", "yellow")}
    <h2>Volume of a Solid of Revolution</h2>
    <div class="problem"><span>Problem</span>Find the volume of the solid formed by rotating a hexagon around an axis.</div>
    <h3>What Tutorly shows</h3>
    {bullets(["3D solid, axis of rotation and labelled cross-sections",
              "Formulas revealed step by step — each one tied to the side or section it comes from",
              "<strong>SymPy</strong> checks every expression and intermediate value; the geometry is verified independently"])}
    <div class="callout green">Every displayed value is checked by <strong>SymPy</strong> — not just the final answer.</div>
  </div>
  <div class="col media">
    {browser(img("example explanation.png", "Lesson view: solid of revolution"), "localhost:3000/lessons/…")}
  </div>
</section>""")

# 3 · combinatorics example
SLIDES.append(f"""
<section class="slide split">
  <div class="col text">
    {kicker("Example 2 · Combinatorics", "blue")}
    <h2>5 People in a Row — A and B Cannot Stand Together</h2>
    <h3>The challenge</h3>
    <p>Count valid arrangements where two specific people cannot be adjacent — a classic problem that is easy to miscount.</p>
    <h3>How Tutorly solves it</h3>
    <ol class="steps">
      <li><span>Visualizes all <strong>120</strong> permutations</span></li>
      <li><span>Highlights the forbidden “block” case</span></li>
      <li><span>Applies the block method step by step: <span class="math">4! · 2! = 48</span></span></li>
      <li><span>Independently verifies <span class="math">120 − 48 = 72</span> by brute-force enumeration in Python — not by trusting the model</span></li>
    </ol>
  </div>
  <div class="col media">
    {browser(img("combinatorics_example_explanation.png", "Lesson view: 5 people in a row"), "localhost:3000/lessons/…")}
    <div class="stat"><b>72</b><span>valid arrangements<br><small>✓ brute force agrees</small></span></div>
  </div>
</section>""")

# 4 · pipeline
stages = ["ProblemIR", "ScopeIR", "SolutionIR <small>SymPy-verified</small>", "LessonIR", "Narration + Voice",
          "Visual plan", "Validators", "Manim render"]
flow = '<div class="flow">' + '<span class="arrow">→</span>'.join(f'<div class="stage">{s}</div>' for s in stages) + "</div>"
SLIDES.append(f"""
<section class="slide wide">
  {kicker("Architecture", "purple")}
  <h2>From Problem to Lesson: The Full Pipeline</h2>
  <p class="lead small">Inspired by <strong>LLM2Manim</strong> (arXiv:2604.05266), Tutorly uses a <strong>plan-first</strong> architecture
  with structured scenes, independent validation, and a feedback loop that regenerates <strong>only failed stages</strong> — not the entire lesson.</p>
  {flow}
  <p class="brain-note">🧠 <strong>Gemini 3.8 Flash</strong> drives every reasoning stage · 🐍 <strong>Python</strong> checks every output before it moves on</p>
  <div class="pair">
    <figure>{img("pipeline.png", "LLM2Manim reference pipeline")}<figcaption>Reference: the LLM2Manim plan-first pipeline (arXiv:2604.05266)</figcaption></figure>
  </div>
</section>""")

# 4b · Gemini as the brain
roles = [
    ("Understands the problem", "ProblemIR + ScopeIR: givens, unknowns, allowed methods", "Scope Validator: high-school level, learner's range"),
    ("Solves it, step by step", "SolutionIR with the reason for every step", "SymPy + NetworkX / brute force"),
    ("Plans the lesson", "scenes, concepts, notation ledger", "Ledger Validator: consistent notation across scenes"),
    ("Writes the narration", "spoken explanation, high-school language", "language & jargon checks"),
    ("Designs the visuals", "semantic visual plan: presets + operations", "geometry & layout validator"),
    ("Answers questions", "chat answer or a new video lesson", "same validated pipeline"),
]
rows_html = "".join(
    f'<div class="role"><b>{t}</b><span>{d}</span><em>✓ {v}</em></div>' for t, d, v in roles)
SLIDES.append(f"""
<section class="slide wide">
  {kicker("The brain", "purple")}
  <h2>Gemini 3.8 Flash: The Multimodal Brain Behind Every Stage</h2>
  <p class="lead small">Google's multimodal Gemini model does the thinking — understanding, solving, teaching and designing.
  It always answers in <strong>typed, structured JSON</strong>, so every output can be checked by code before the next stage uses it.</p>
  <div class="roles">
    <div class="role head"><b>Gemini does</b><span>Produces</span><em>Checked by</em></div>
    {rows_html}
  </div>
  <p class="verdict">Gemini is creative, Python is strict — <strong>the model proposes, code verifies</strong>.</p>
</section>""")

# 5 · presets
SLIDES.append(f"""
<section class="slide split presets">
  <div class="col text">
    {kicker("Visual language", "green")}
    <h2>Reusable Scene Presets & Visual Operations</h2>
    <h3>Combinatorics</h3>
    {chips(["arrangement_gallery", "permutation_counter", "block_method", "case_split"], "blue")}
    <h3>Solid Geometry</h3>
    {chips(["solid_reveal", "space_construction", "section_flatten", "solid_of_revolution"], "yellow")}
    <h3>Core Operations</h3>
    {chips(["create", "merge", "split", "transform", "measure", "enumerate", "emphasize_result"], "green")}
    <div class="callout">The model chooses <strong>what an operation means</strong> — colours, positions and code are determined
    by the preset. Scenes are <strong>repeatable, readable and verifiable</strong>.</div>
  </div>
  <div class="col media">{img("presets_overview.png", "Presets overview")}</div>
</section>""")

# 6 · tech stack
cards = [
    ("Frontend", "🖥️", "Next.js 15, React 19, TypeScript, Tailwind CSS", "fast, modern, responsive UI"),
    ("Backend", "⚙️", "FastAPI, Python 3.12, Pydantic, SQLAlchemy, SQLite", "typed REST API · every attempt, error and result logged in SQLite"),
    ("Math & Verification", "🧮", "Gemini 3.8 Flash as the multimodal reasoning brain · SymPy · NetworkX · brute-force enumeration",
     "independent validation of every result"),
    ("Animation & Voice", "🎬", "Manim Community + FFmpeg · Azure TTS or local Piper", "narrated, rendered video"),
]
grid = "".join(f'<div class="card"><div class="icon">{ic}</div><h3>{t}</h3><p>{d}</p><small>{s}</small></div>'
               for t, ic, d, s in cards)
SLIDES.append(f"""
<section class="slide wide">
  {kicker("Tech stack", "blue")}
  <h2>Built for Speed, Modularity & Local Deployment</h2>
  <div class="grid4">{grid}</div>
  <div class="terminal"><span>$</span> docker compose up --build <em># the full stack runs locally — ideal for demos and offline use</em></div>
</section>""")

# 8 · design rationale
rows = [("Mathematical reasoning", "didactic planning"), ("Narrative", "semantic visual plan")]
sep = "".join(f'<div class="sep"><span>{a}</span><b>⟷</b><span>{b}</span></div>' for a, b in rows)
SLIDES.append(f"""
<section class="slide wide">
  {kicker("Design rationale", "purple")}
  <h2>Why Not Just LLM → Manim?</h2>
  <div class="versus">
    <div class="panel bad">
      <h3>✗ The risk of direct code generation</h3>
      <div class="mini-flow"><span>problem</span>→<span>LLM</span>→<span>Manim code</span></div>
      <p>Feeding a problem straight to an LLM for Manim code can produce <strong>wrong formulas</strong>,
      <strong>inconsistent narration</strong> and <strong>unstable animations</strong> — with no way to isolate the failure.</p>
    </div>
    <div class="panel good">
      <h3>✓ Tutorly's separation of concerns</h3>
      {sep}
      {bullets(["Each stage validated independently; failures trigger <strong>local regeneration only</strong>",
                "Manim code passes <strong>AST validation</strong> and runs in a sandboxed, offline process",
                "Every attempt, error and result is logged in <strong>SQLite</strong> — AI with accountability, not a black box"])}
    </div>
  </div>
  <p class="verdict">A broken animation never touches the <strong>verified mathematics</strong> — only that scene is regenerated.</p>
</section>""")

# 9 · questions become lessons
SLIDES.append(f"""
<section class="slide split">
  <div class="col text">
    {kicker("Follow-up questions", "yellow")}
    <h2>Every Student Question Becomes a New Video Lesson</h2>
    <p>When a student asks <em>“Why can't we just count all arrangements?”</em>, Tutorly uses the scene context, the knowledge
    scope and the concept ledger to answer in chat — and, when a picture is needed, generates a personalised animated
    explanation through <strong>the same validated pipeline</strong>.</p>
    <div class="pillars">
      <div><b>Understand</b><span>Visual, narrated reasoning — not just text</span></div>
      <div><b>Verify</b><span>Every value independently checked by code</span></div>
      <div><b>Control</b><span>AI supports — the student decides the pace and depth</span></div>
    </div>
  </div>
  <div class="col media">
    {browser(img("question.png", "A follow-up question answered as a new video lesson"), "localhost:3000/lessons/…")}
  </div>
</section>""")

# 10 · closing
SLIDES.append("""
<section class="slide hero closing">
  <div class="hero-text center">
    <div class="logo">Tutorly</div>
    <h1>Understand mathematics,<br>don't just solve it.</h1>
    <div class="pills"><span>Understand</span><span>Verify</span><span>Control</span></div>
    <p class="lead small">Thank you! · Questions?</p>
  </div>
</section>""")


# ----------------------------------------------------------------------------------------------- page
CSS = """
:root{--bg:#0b0f1c;--panel:#141a2c;--panel2:#1a2238;--edge:#273152;--fg:#eef1f8;--muted:#98a2b8;
--blue:#7ea6bd;--yellow:#d4b26a;--green:#86b89a;--red:#c98585;--purple:#9e94c4}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:#05070d;color:var(--fg);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;overflow:hidden}
#deck{position:absolute;left:50%;top:50%;width:1600px;height:900px;transform-origin:center center}
.slide{position:absolute;inset:0;padding:48px 56px 44px;display:none;background:
 radial-gradient(1200px 600px at 85% -10%,rgba(126,166,189,.06),transparent 60%),
 radial-gradient(900px 500px at -10% 110%,rgba(158,148,196,.05),transparent 60%),var(--bg);overflow:hidden}
.slide.active{display:flex;animation:in .45s ease}
@keyframes in{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
h1{font-size:54px;line-height:1.08;font-weight:800;letter-spacing:-.02em}
h1 em{font-style:normal;background:linear-gradient(90deg,var(--blue),var(--green));-webkit-background-clip:text;color:transparent}
h2{font-size:38px;line-height:1.12;font-weight:800;letter-spacing:-.015em;margin-bottom:18px}
h3{font-size:17px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin:22px 0 10px;font-weight:700}
p{font-size:19px;line-height:1.5;color:#cfd5e3}
strong{color:var(--fg)}
.lead{font-size:22px;line-height:1.5;color:#cfd5e3;margin-top:22px}.lead.small{font-size:20px;margin-top:0}
.logo{font-weight:800;font-size:24px;color:var(--blue);letter-spacing:.02em;margin-bottom:26px}
.kicker{display:inline-block;font-size:14px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;padding:6px 12px;border-radius:999px;margin-bottom:16px;border:1px solid}
.kicker.blue{color:var(--blue);border-color:rgba(126,166,189,.4);background:rgba(126,166,189,.08)}
.kicker.yellow{color:var(--yellow);border-color:rgba(212,178,106,.4);background:rgba(212,178,106,.08)}
.kicker.green{color:var(--green);border-color:rgba(134,184,154,.4);background:rgba(134,184,154,.08)}
.kicker.purple{color:var(--purple);border-color:rgba(158,148,196,.4);background:rgba(158,148,196,.08)}
.pills{display:flex;gap:12px;margin-top:30px;flex-wrap:wrap}
.pills span{padding:10px 18px;border-radius:999px;background:var(--panel2);border:1px solid var(--edge);font-size:18px;font-weight:600}
/* layouts */
.hero{align-items:center;gap:40px}.hero-text{flex:0 0 560px}.hero-shot{flex:1;min-width:0}
.hero-text.center{flex:1;text-align:center}.hero-text.center .pills{justify-content:center}
.closing h1{font-size:76px}
.split{gap:36px;align-items:center}.split .col.text{flex:0 0 470px}.split .col.media{flex:1;min-width:0;display:flex;flex-direction:column;gap:16px;justify-content:center;height:100%}
.wide{flex-direction:column;justify-content:center}.wide>.kicker{align-self:flex-start}
.shot{display:block;max-width:100%;max-height:100%;object-fit:contain;border-radius:14px;border:1px solid var(--edge);box-shadow:0 20px 50px rgba(0,0,0,.45);background:#fff}
.shot.crisp{image-rendering:auto}
.placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;min-height:220px;background:var(--panel)!important;border:2px dashed var(--edge)!important;color:var(--muted);font-size:20px}
.placeholder small{font-size:14px;opacity:.7}
.browser{border-radius:14px;overflow:hidden;border:1px solid var(--edge);box-shadow:0 30px 70px rgba(0,0,0,.55);background:#fff}
.browser .bar{height:34px;background:#1d2438;display:flex;align-items:center;gap:7px;padding:0 14px}
.browser .bar i{width:11px;height:11px;border-radius:50%;background:#ff5f57}.browser .bar i:nth-child(2){background:#febc2e}.browser .bar i:nth-child(3){background:#28c840}
.browser .bar span{margin-left:14px;font-size:13px;color:var(--muted);background:#121828;padding:4px 14px;border-radius:6px;flex:1;max-width:340px}
.browser .viewport .shot{border:0;border-radius:0;box-shadow:none;width:100%}
.problem{background:var(--panel);border:1px solid var(--edge);border-left:4px solid var(--yellow);border-radius:12px;padding:16px 20px;font-size:21px;line-height:1.45}
.problem span{display:block;font-size:13px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--yellow);margin-bottom:4px}
.bullets{list-style:none;display:flex;flex-direction:column;gap:12px}
.bullets li{display:flex;gap:12px;font-size:18px;line-height:1.4;color:#cfd5e3}
.bullets b{flex:0 0 28px;height:28px;border-radius:8px;background:rgba(134,184,154,.14);color:var(--green);display:flex;align-items:center;justify-content:center;font-size:16px;margin-top:1px}
.callout{margin-top:24px;padding:16px 20px;border-radius:12px;background:rgba(126,166,189,.08);border:1px solid rgba(126,166,189,.35);font-size:19px;line-height:1.45;color:#d7e6ee}
.callout.green{background:rgba(134,184,154,.08);border-color:rgba(134,184,154,.4)}
.steps{counter-reset:s;list-style:none;display:flex;flex-direction:column;gap:12px}
.steps li{counter-increment:s;display:flex;gap:12px;align-items:baseline;font-size:18px;line-height:1.4;color:#cfd5e3}
.steps li::before{content:counter(s);flex:0 0 30px;height:30px;border-radius:50%;background:var(--blue);color:var(--bg);font-weight:800;display:flex;align-items:center;justify-content:center;font-size:16px}
.math{font-family:"Cambria Math",Georgia,serif;color:var(--yellow);font-size:22px;white-space:nowrap}
.media.stack .shot{height:345px;width:auto;max-width:100%;background:none;align-self:center}
.stat{align-self:flex-end;display:flex;align-items:center;gap:14px;background:var(--panel);border:1px solid rgba(134,184,154,.5);border-radius:16px;padding:12px 22px;box-shadow:0 12px 30px rgba(0,0,0,.4)}
.stat b{font-size:52px;color:var(--green);font-weight:800}.stat span{font-size:17px;line-height:1.3;color:var(--muted)}.stat small{color:var(--green)}
.flow{display:flex;align-items:center;gap:8px;margin:22px 0 26px;flex-wrap:nowrap}
.stage{background:var(--panel2);border:1px solid var(--edge);border-radius:10px;padding:10px 12px;font-size:16px;font-weight:700;text-align:center;line-height:1.2;white-space:nowrap}
.stage small{display:block;font-size:11px;color:var(--green);font-weight:600}
.flow .arrow{color:var(--muted);font-size:20px}
.pair{display:block;margin-top:6px}
figure{display:flex;flex-direction:column;gap:10px;min-height:0;align-items:center;justify-content:center}
figure .shot{max-height:520px;width:100%}
figcaption{font-size:16px;color:var(--muted);text-align:center}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{font-family:ui-monospace,Consolas,monospace;font-size:16px;padding:7px 12px;border-radius:8px;background:var(--panel2);border:1px solid var(--edge)}
.chip.blue{color:var(--blue)}.chip.yellow{color:var(--yellow)}.chip.green{color:var(--green)}
.presets .col.text{flex-basis:440px!important}.presets .col.media .shot{max-height:808px;background:var(--bg)}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:22px;margin-top:20px}
.card{background:var(--panel);border:1px solid var(--edge);border-radius:18px;padding:28px 24px;display:flex;flex-direction:column;gap:12px;min-height:340px}
.card .icon{font-size:40px}.card h3{margin:0;color:var(--fg);font-size:20px}
.card p{font-size:19px;color:#d5dbe8}.card small{margin-top:auto;font-size:15px;color:var(--muted)}
.terminal{margin-top:34px;font-family:ui-monospace,Consolas,monospace;font-size:20px;background:#070a12;border:1px solid var(--edge);border-radius:12px;padding:18px 24px}
.terminal span{color:var(--green);margin-right:12px}.terminal em{color:var(--muted);font-style:normal;margin-left:14px}
.qc .col.media.tall{align-items:center}.qc .shot{height:808px;width:auto;max-height:none}
.versus{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:16px}
.closing .lead{margin-top:30px}
.verdict{margin-top:26px;text-align:center;font-size:22px;color:#cfd5e3}.verdict strong{color:var(--green)}
.brain-note{margin:-8px 0 18px;font-size:18px;color:var(--muted)}
.roles{display:flex;flex-direction:column;gap:8px;margin-top:22px}
.role{display:grid;grid-template-columns:300px 1fr 330px;gap:20px;align-items:center;background:var(--panel);border:1px solid var(--edge);border-radius:12px;padding:13px 22px}
.role b{font-size:19px;color:var(--purple)}.role span{font-size:18px;color:#cfd5e3}.role em{font-style:normal;font-size:17px;color:var(--green)}
.role.head{background:none;border:0;padding:0 22px}.role.head b,.role.head span,.role.head em{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:700}
.panel{border-radius:18px;padding:30px;border:1px solid}
.panel h3{margin-top:0;font-size:19px}
.panel.bad{background:rgba(201,133,133,.06);border-color:rgba(201,133,133,.35)}.panel.bad h3{color:var(--red)}
.panel.good{background:rgba(134,184,154,.05);border-color:rgba(134,184,154,.35)}.panel.good h3{color:var(--green)}
.mini-flow{display:flex;align-items:center;gap:10px;margin:8px 0 22px;font-size:20px;color:var(--muted)}
.mini-flow span{padding:8px 14px;border-radius:8px;background:var(--panel2);border:1px solid var(--edge);color:var(--fg);font-weight:600}
.sep{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;margin-bottom:12px}
.sep span{padding:10px 14px;border-radius:10px;background:var(--panel2);border:1px solid var(--edge);font-size:18px;font-weight:600;text-align:center}
.sep b{color:var(--green);font-size:22px}
.panel.good .bullets{margin-top:18px}
.pillars{display:grid;grid-template-columns:1fr;gap:10px;margin-top:24px}
.pillars div{background:var(--panel);border:1px solid var(--edge);border-radius:12px;padding:12px 18px;display:flex;align-items:baseline;gap:14px}
.pillars b{flex:0 0 120px;font-size:19px;color:var(--yellow)}.pillars span{font-size:16px;line-height:1.4;color:#cfd5e3}
.question figure .shot{width:100%;max-height:none}
.question figure:first-child .shot{width:70%}
/* chrome */
#progress{position:fixed;left:0;bottom:0;height:4px;background:linear-gradient(90deg,var(--blue),var(--green));transition:width .3s}
#counter{position:fixed;right:18px;bottom:12px;font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums}
@media print{
 @page{size:1600px 900px;margin:0}
 html,body{overflow:visible;background:var(--bg)}
 #deck{position:static;transform:none!important}
 .slide{position:relative;display:flex!important;width:1600px;height:900px;page-break-after:always;animation:none}
 #progress,#counter{display:none}
}
"""

JS = """
const slides=[...document.querySelectorAll('.slide')];let i=0;
const deck=document.getElementById('deck'),bar=document.getElementById('progress'),ctr=document.getElementById('counter');
function fit(){const s=Math.min(innerWidth/1600,innerHeight/900);deck.style.transform=`translate(-50%,-50%) scale(${s})`}
function show(n){i=Math.max(0,Math.min(slides.length-1,n));slides.forEach((s,k)=>s.classList.toggle('active',k===i));
 bar.style.width=((i+1)/slides.length*100)+'%';ctr.textContent=(i+1)+' / '+slides.length;try{history.replaceState(null,'','#'+(i+1))}catch(e){}}
addEventListener('keydown',e=>{if(['ArrowRight','PageDown',' ','Enter'].includes(e.key)){e.preventDefault();show(i+1)}
 else if(['ArrowLeft','PageUp','Backspace'].includes(e.key)){e.preventDefault();show(i-1)}
 else if(e.key==='Home')show(0);else if(e.key==='End')show(slides.length-1);
 else if(e.key.toLowerCase()==='f'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()}
 else if(e.key.toLowerCase()==='p')print();});
addEventListener('click',e=>{if(e.target.closest('a'))return;show(e.clientX<innerWidth*0.25?i-1:i+1)});
let tx=null;addEventListener('touchstart',e=>tx=e.touches[0].clientX);addEventListener('touchend',e=>{if(tx===null)return;const d=e.changedTouches[0].clientX-tx;if(Math.abs(d)>40)show(d<0?i+1:i-1);tx=null});
addEventListener('resize',fit);fit();show((parseInt(location.hash.slice(1))||1)-1);
"""

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tutorly — Pitch Deck</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body><div id="deck">{''.join(SLIDES)}</div><div id="progress"></div><div id="counter"></div>
<script>{JS}</script></body></html>"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(page, encoding="utf-8")
missing = [n for n in ("initial ui.png", "example explanation.png", "combinatorics_example_explanation.png", "pipeline.png",
                       "scene generation.png", "presets_overview.png", "question.png")
           if not (ASSETS / n).exists()]
print(f"saved {OUT} ({OUT.stat().st_size // 1024} KB, {len(SLIDES)} slides)" + (f"; placeholders for: {missing}" if missing else ""))
