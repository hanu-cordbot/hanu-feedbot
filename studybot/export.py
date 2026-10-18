"""Exports a deck as files people can learn from without the bot running.

* A single self-contained HTML study pack: an interactive quiz (missed questions come
  back first, progress kept in the browser) and a printable review sheet. Share it in
  Discord, email it, or host it on GitHub Pages.
* An Anki-importable text file for spaced-repetition flashcards.

CLI, e.g. to publish every deck in a server to the existing GitHub Pages site:
    python -m studybot.export --guild 1234567890 --out docs/study
"""
import argparse
import html
import json
import re
import time
from pathlib import Path
from typing import Optional

from . import config
from .db import Store


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deck"


def pack_data(store: Store, deck_id: int, name: str) -> dict:
    return {
        "deck": name,
        "slug": slugify(name),
        "sources": store.deck_sources(deck_id),
        "exported": time.strftime("%Y-%m-%d"),
        "questions": [
            {
                "id": q["id"],
                "stem": q["stem"],
                "options": q["options"],
                "correct": q["correct_index"],
                "explanation": q["explanation"],
                "rationales": q["rationales"],
                "quote": q.get("source_quote") or "",
                "level": " · ".join(x for x in (q.get("difficulty"), q.get("cognitive_level")) if x),
            }
            for q in store.deck_questions(deck_id)
        ],
    }


def render_html(data: dict) -> str:
    # "</" is escaped so text from documents can never close the <script> tag.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__TITLE__", html.escape(data["deck"].title())).replace("__DATA__", payload)


def render_anki(data: dict) -> str:
    """Tab-separated notes with HTML, importable via Anki's File → Import."""
    esc = lambda s: html.escape(s).replace("\t", " ").replace("\n", "<br>")  # noqa: E731
    lines = ["#separator:tab", "#html:true", "#tags column:3"]
    tag = data["slug"]
    for q in data["questions"]:
        front = esc(q["stem"]) + "<br><br>" + "<br>".join(f"{'ABCD'[i]}. {esc(o)}" for i, o in enumerate(q["options"]))
        back = f"<b>{'ABCD'[q['correct']]}. {esc(q['options'][q['correct']])}</b><br><br>{esc(q['explanation'])}"
        if q["quote"]:
            back += f"<br><br><i>“{esc(q['quote'])}”</i>"
        lines.append(f"{front}\t{back}\t{tag}")
    return "\n".join(lines) + "\n"


def render_index(packs: list[dict]) -> str:
    items = "\n".join(
        f'<li><a href="{html.escape(p["slug"])}.html">{html.escape(p["deck"].title())}</a>'
        f'<span>{len(p["questions"])} questions</span></li>'
        for p in sorted(packs, key=lambda p: p["deck"])
    )
    return INDEX_TEMPLATE.replace("__ITEMS__", items or "<li>No decks yet.</li>")


def export_guild(store: Store, guild_id: int, out: Path, deck: Optional[str] = None) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written, packs = [], []
    for row in store.list_decks(guild_id):
        data = pack_data(store, row["id"], row["name"])
        if not data["questions"] or (deck and row["name"] != deck.strip().lower()):
            continue
        packs.append(data)
        for suffix, text in ((".html", render_html(data)), (".anki.txt", render_anki(data))):
            path = out / f"{data['slug']}{suffix}"
            path.write_text(text, encoding="utf-8")
            written.append(path)
    if not deck:
        (out / "index.html").write_text(render_index(packs), encoding="utf-8")
        written.append(out / "index.html")
    return written


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · Study pack</title>
<style>
:root {
  --bg: #f7f7f5; --card: #ffffff; --ink: #1d1d1f; --muted: #6b6b70; --line: #e3e3e0;
  --accent: #4f46e5; --on-accent: #ffffff; --good: #15803d; --good-bg: #e8f5ec; --bad: #b91c1c; --bad-bg: #fbeaea;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #141416; --card: #1d1d20; --ink: #ececef; --muted: #9a9aa2; --line: #2e2e33;
    --accent: #8b85ff; --on-accent: #141416; --good: #4ade80; --good-bg: #13291b; --bad: #f87171; --bad-bg: #2d1717;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 720px; margin: 0 auto; padding: 24px 16px 64px; }
header h1 { font-size: 1.6rem; margin: 0 0 4px; }
header p { margin: 0; color: var(--muted); font-size: .9rem; }
nav { display: flex; gap: 8px; margin: 20px 0; }
nav button { flex: 1; }
button { font: inherit; color: inherit; background: var(--card); border: 1px solid var(--line);
  border-radius: 10px; padding: 10px 14px; cursor: pointer; }
button:hover { border-color: var(--accent); }
button.primary, nav button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 20px; margin-bottom: 16px; }
.meta { color: var(--muted); font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; }
.stem { font-size: 1.1rem; font-weight: 600; margin: 8px 0 16px; }
.options { display: grid; gap: 8px; }
.options button { text-align: left; display: flex; gap: 10px; align-items: flex-start; }
.options b { color: var(--muted); min-width: 1.2em; }
.options button.right { background: var(--good-bg); border-color: var(--good); }
.options button.wrong { background: var(--bad-bg); border-color: var(--bad); }
.options button:disabled { cursor: default; }
.feedback h3 { margin: 18px 0 4px; font-size: .95rem; }
.feedback p, .feedback li { margin: 4px 0; }
.feedback ul { padding-left: 18px; margin: 4px 0; }
blockquote { margin: 8px 0 0; padding: 6px 12px; border-left: 3px solid var(--accent); color: var(--muted); }
.verdict.right { color: var(--good); } .verdict.wrong { color: var(--bad); }
.bar { height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; margin-bottom: 16px; }
.bar div { height: 100%; background: var(--accent); width: 0; transition: width .2s; }
.row { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; flex-wrap: wrap; }
.answer { color: var(--good); font-weight: 600; }
.hint { color: var(--muted); font-size: .8rem; text-align: center; }
@media print {
  nav, #quiz, .hint { display: none !important; }
  #review { display: block !important; }
  body { background: #fff; color: #000; }
  .card { break-inside: avoid; border-color: #ccc; }
}
</style>
</head>
<body>
<main>
  <header>
    <h1 id="title"></h1>
    <p id="subtitle"></p>
  </header>
  <nav>
    <button id="tab-quiz" aria-pressed="true">Quiz</button>
    <button id="tab-review" aria-pressed="false">Review sheet</button>
  </nav>
  <section id="quiz"></section>
  <section id="review" hidden></section>
  <p class="hint">Keys: 1–4 to answer, Enter for next. Print this page for a paper review sheet.</p>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById("data").textContent);
  var L = "ABCD";
  var KEY = "studypack:" + D.slug;
  var history = load();

  function load() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(history)); } catch (e) {} }
  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) { if (k === "text") n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]); }
    (kids || []).forEach(function (c) { if (c) n.appendChild(c); });
    return n;
  }

  document.title = D.deck.replace(/\b\w/g, function (c) { return c.toUpperCase(); }) + " · Study pack";
  document.getElementById("title").textContent = document.title.replace(" · Study pack", "");
  document.getElementById("subtitle").textContent =
    D.questions.length + " questions" + (D.sources.length ? " · from " + D.sources.join(", ") : "") + " · exported " + D.exported;

  // Missed questions first, then unseen, then ones already answered correctly.
  function order(ids) {
    function rank(q) { var h = history[q.id]; return h === undefined ? 1 : h ? 2 : 0; }
    return ids.slice().sort(function (a, b) { return rank(a) - rank(b) || Math.random() - .5; });
  }

  var queue, pos, score, missed, answered;
  var quiz = document.getElementById("quiz");

  function start(list) { queue = order(list); pos = 0; score = 0; missed = []; show(); }

  function show() {
    quiz.innerHTML = ""; answered = false;
    if (pos >= queue.length) return finish();
    var q = queue[pos];
    var bar = el("div", { class: "bar" }, [el("div")]);
    bar.firstChild.style.width = (100 * pos / queue.length) + "%";
    var opts = el("div", { class: "options" });
    q.options.forEach(function (o, i) {
      var b = el("button", {}, [el("b", { text: L[i] }), el("span", { text: o })]);
      b.onclick = function () { answer(q, i, opts, card); };
      opts.appendChild(b);
    });
    var card = el("div", { class: "card" }, [
      el("div", { class: "meta", text: "Question " + (pos + 1) + " of " + queue.length + (q.level ? " · " + q.level : "") }),
      el("div", { class: "stem", text: q.stem }), opts
    ]);
    quiz.appendChild(bar); quiz.appendChild(card);
  }

  function answer(q, i, opts, card) {
    if (answered) return; answered = true;
    var ok = i === q.correct;
    history[q.id] = ok; save();
    if (ok) score++; else missed.push(q);
    Array.prototype.forEach.call(opts.children, function (b, j) {
      b.disabled = true;
      if (j === q.correct) b.classList.add("right"); else if (j === i) b.classList.add("wrong");
    });
    var fb = el("div", { class: "feedback" }, [
      el("h3", { class: "verdict " + (ok ? "right" : "wrong"), text: ok ? "Correct" : "Not quite — the answer is " + L[q.correct] }),
      el("p", { text: q.explanation })
    ]);
    var others = q.options.map(function (_, j) { return j; })
      .filter(function (j) { return j !== q.correct && q.rationales[j]; })
      .sort(function (a, b) { return (b === i) - (a === i); });
    if (others.length) {
      fb.appendChild(el("h3", { text: "Why the others are wrong" }));
      fb.appendChild(el("ul", {}, others.map(function (j) { return el("li", { text: L[j] + " — " + q.rationales[j] }); })));
    }
    if (q.quote) fb.appendChild(el("blockquote", { text: "“" + q.quote + "”" }));
    var next = el("button", { class: "primary", text: pos + 1 < queue.length ? "Next" : "See results" });
    next.onclick = function () { pos++; show(); };
    fb.appendChild(el("div", { class: "row" }, [next]));
    card.appendChild(fb);
    next.focus();
  }

  function finish() {
    var pct = queue.length ? Math.round(100 * score / queue.length) : 0;
    var again = el("button", { text: "Start over" });
    again.onclick = function () { start(D.questions); };
    var kids = [el("div", { class: "stem", text: "You scored " + score + " / " + queue.length + " (" + pct + "%)" })];
    var row = el("div", { class: "row" }, [again]);
    if (missed.length) {
      var retry = el("button", { class: "primary", text: "Retry the " + missed.length + " you missed" });
      var m = missed.slice();
      retry.onclick = function () { start(m); };
      row.appendChild(retry);
    }
    kids.push(row);
    quiz.appendChild(el("div", { class: "card" }, kids));
  }

  document.addEventListener("keydown", function (e) {
    if (document.getElementById("quiz").hidden) return;
    var n = "1234".indexOf(e.key); if (n < 0) n = "abcd".indexOf(e.key.toLowerCase());
    var btns = quiz.querySelectorAll(".options button");
    if (n >= 0 && btns[n] && !answered) btns[n].click();
    else if (e.key === "Enter" && answered) { var nx = quiz.querySelector(".row button.primary"); if (nx) nx.click(); }
  });

  var review = document.getElementById("review");
  D.questions.forEach(function (q, n) {
    var kids = [
      el("div", { class: "meta", text: (n + 1) + (q.level ? " · " + q.level : "") }),
      el("div", { class: "stem", text: q.stem }),
      el("ul", {}, q.options.map(function (o, i) {
        return el("li", { class: i === q.correct ? "answer" : "", text: L[i] + ". " + o });
      })),
      el("p", { text: q.explanation })
    ];
    if (q.quote) kids.push(el("blockquote", { text: "“" + q.quote + "”" }));
    review.appendChild(el("div", { class: "card" }, kids));
  });

  function tab(which) {
    var isQuiz = which === "quiz";
    document.getElementById("quiz").hidden = !isQuiz;
    review.hidden = isQuiz;
    document.getElementById("tab-quiz").setAttribute("aria-pressed", isQuiz);
    document.getElementById("tab-review").setAttribute("aria-pressed", !isQuiz);
  }
  document.getElementById("tab-quiz").onclick = function () { tab("quiz"); };
  document.getElementById("tab-review").onclick = function () { tab("review"); };

  start(D.questions);
})();
</script>
</body>
</html>
"""

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Study packs</title>
<style>
:root { --bg: #f7f7f5; --card: #fff; --ink: #1d1d1f; --muted: #6b6b70; --line: #e3e3e0; --accent: #4f46e5; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #141416; --card: #1d1d20; --ink: #ececef; --muted: #9a9aa2; --line: #2e2e33; --accent: #8b85ff; }
}
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.5 system-ui, sans-serif; }
main { max-width: 720px; margin: 0 auto; padding: 24px 16px; }
ul { list-style: none; padding: 0; }
li { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; margin-bottom: 8px;
  display: flex; justify-content: space-between; gap: 12px; }
a { color: var(--accent); font-weight: 600; text-decoration: none; }
span { color: var(--muted); }
</style>
</head>
<body><main><h1>Study packs</h1><ul>
__ITEMS__
</ul></main></body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Export study decks as HTML study packs and Anki files")
    parser.add_argument("--guild", type=int, required=True, help="Discord server ID whose decks to export")
    parser.add_argument("--deck", help="Only this deck (default: all, plus an index page)")
    parser.add_argument("--out", type=Path, default=Path("docs/study"), help="Output folder")
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    args = parser.parse_args()
    for path in export_guild(Store(args.db), args.guild, args.out, args.deck):
        print(path)


if __name__ == "__main__":
    main()
