// T14 review API (Cloudflare Pages Function + D1).
// Secrets: REVIEW_PASSCODE (reviewers), ADMIN_PASSCODE (final say). Never commit them.
const DECISIONS = new Set(["approve", "reject", "edit", "escalate", "skip"]);
const COLUMNS = ["rank", "item_id", "score", "reason", "suggested_action", "slice", "evidence_path",
  "reviewer", "reviewer_decision", "override_value", "review_note", "reviewed_at"];

const json = (o, s = 200) => new Response(JSON.stringify(o), {
  status: s, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });

function same(a, b) {                       // constant-time compare
  const e = new TextEncoder(), x = e.encode(a), y = e.encode(b);
  let d = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) d |= (x[i] || 0) ^ (y[i] || 0);
  return d === 0;
}
function roleOf(req, env) {
  const p = req.headers.get("x-passcode") || "";
  if (env.ADMIN_PASSCODE && same(p, env.ADMIN_PASSCODE)) return "admin";
  if (env.REVIEW_PASSCODE && same(p, env.REVIEW_PASSCODE)) return "reviewer";
  return null;
}

let queueCache;
async function loadQueue(req, env) {
  if (!queueCache) queueCache = await (await env.ASSETS.fetch(new URL("/queue.json", req.url))).json();
  return queueCache;
}

// 'class' | 'x,y,w,h' | 'class,x,y,w,h'
function validOverride(v, classes) {
  const parts = String(v).split(",").map((s) => s.trim()).filter(Boolean);
  let hasClass = false;
  if (parts.length && classes.includes(parts[0])) { parts.shift(); hasClass = true; }
  if (!parts.length) return hasClass;
  return parts.length === 4 && parts.every((s) => Number.isFinite(Number(s)));
}

// latest row per (item, reviewer) -> resolved state per item
function resolve(rows, items) {
  const by = new Map(items.map((i) => [i.item_id, { item_id: i.item_id, reviewers: {}, admin: null }]));
  for (const r of rows) {                    // rows ordered by id ASC, so later rows win
    const it = by.get(r.item_id);
    if (!it) continue;
    if (r.role === "admin") it.admin = r;
    else it.reviewers[r.reviewer.toLowerCase()] = r;
  }
  for (const it of by.values()) {
    const rs = Object.values(it.reviewers).filter((r) => r.decision !== "skip");
    if (it.admin) { it.state = "final"; it.final = it.admin; continue; }
    if (!rs.length) { it.state = "pending"; continue; }
    if (rs.some((r) => r.decision === "escalate")) { it.state = "escalated"; continue; }
    const key = (r) => r.decision + "|" + (r.decision === "edit" ? r.override_value : "");
    if (rs.every((r) => key(r) === key(rs[0]))) { it.state = "ok"; it.final = rs[0]; }
    else it.state = "conflict";
  }
  return [...by.values()];
}

const csv = (v) => {
  v = String(v ?? "");
  return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
};

export async function onRequest({ request, env, params }) {
  const path = "/" + [].concat(params.path || []).join("/");
  const role = roleOf(request, env);
  if (!role) return json({ error: "sai passcode" }, 401);
  const q = await loadQueue(request, env);
  const ids = new Set(q.items.map((i) => i.item_id));
  const all = async () => (await env.DB.prepare("SELECT * FROM decisions ORDER BY id ASC").all()).results;

  if (path === "/decision" && request.method === "POST") {
    let b;
    try { b = await request.json(); } catch { return json({ error: "JSON không hợp lệ" }, 400); }
    const reviewer = String(b.reviewer || "").trim();
    const decision = String(b.decision || "").trim().toLowerCase();
    const override = String(b.override_value || "").trim();
    const note = String(b.note || "").trim().slice(0, 500);
    if (reviewer.length < 2 || reviewer.length > 40) return json({ error: "tên người duyệt 2-40 ký tự" }, 400);
    if (!ids.has(b.item_id)) return json({ error: "item không có trong queue" }, 400);
    if (!DECISIONS.has(decision)) return json({ error: "decision không hợp lệ" }, 400);
    if (decision === "edit" && !validOverride(override, q.classes))
      return json({ error: "edit cần: tên class, 'x,y,w,h' hoặc 'class,x,y,w,h'" }, 400);
    await env.DB.prepare(
      "INSERT INTO decisions (item_id, reviewer, role, decision, override_value, note) VALUES (?,?,?,?,?,?)")
      .bind(b.item_id, reviewer, role, decision, decision === "edit" ? override : "", note).run();
    return json({ ok: true, role });
  }

  if (path === "/mine" && request.method === "GET") {
    const me = (new URL(request.url).searchParams.get("reviewer") || "").trim().toLowerCase();
    const mine = {};
    for (const r of await all()) if (r.reviewer.toLowerCase() === me && r.role === role) mine[r.item_id] = r;
    return json({ role, mine });
  }

  if (role !== "admin") return json({ error: "cần passcode admin" }, 403);

  if (path === "/status" && request.method === "GET") {
    const items = resolve(await all(), q.items);
    const count = (s) => items.filter((i) => i.state === s).length;
    return json({ total: items.length, pending: count("pending"), ok: count("ok"), final: count("final"),
      conflict: count("conflict"), escalated: count("escalated"), items });
  }

  if (path === "/audit" && request.method === "GET") return json(await all());

  if (path === "/export" && request.method === "GET") {
    const items = resolve(await all(), q.items);
    const blocked = items.filter((i) => i.state === "conflict" || i.state === "escalated");
    if (blocked.length) return json({ error: "còn box cần admin chốt", items: blocked.map((i) => i.item_id) }, 409);
    const byId = new Map(items.map((i) => [i.item_id, i]));
    const lines = [COLUMNS.join(",")];
    for (const it of q.items) {
      const r = byId.get(it.item_id);
      const f = r.final;
      const voters = Object.values(r.reviewers).filter((x) => x.decision !== "skip");
      const names = r.state === "final" ? "admin:" + f.reviewer : voters.map((x) => x.reviewer).join("+");
      const notes = Object.values(r.reviewers).map((x) => x.note).filter(Boolean).join(" | ");
      lines.push([it.rank, it.item_id, it.score, it.reason, it.suggested_action, it.slice, it.evidence_path,
        f ? names : "", f ? f.decision : "", f ? f.override_value : "",
        f ? (r.state === "final" && f.note ? f.note : notes) : "", f ? f.ts : ""].map(csv).join(","));
    }
    return new Response(lines.join("\n") + "\n", { headers: { "content-type": "text/csv; charset=utf-8",
      "content-disposition": "attachment; filename=review_queue_reviewed.csv", "cache-control": "no-store" } });
  }
  return json({ error: "not found" }, 404);
}
