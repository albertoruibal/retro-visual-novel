"use strict";
/* Layered top-to-bottom scene graph, drawn as SVG.
 *
 * Rank (row) = BFS depth from the entry scene (the first `# Scenes`); scenes
 * sharing a rank stack in file order. The SVG is given an explicit size and
 * #graphwrap scrolls both ways, which suits the wide, deep branch structure
 * (58 scenes, depth ~14). Parallel options to the same target are merged.
 * Clicking a node selects that scene and jumps back to the Editor tab. */
const GRAPH = { colw: 240, rowh: 120, nodew: 150, nodeh: 40, pad: 24 };
const EDGE_MAX_LABEL = 18;
/* Edge-label pill geometry: per-char width, horizontal padding, pill height,
 * and how far the pill top / text baseline sit above the label anchor. */
const PILL = { cw: 7.4, pad: 16, h: 22, top: 11, base: 5 };
const pillW = (text) => text.length * PILL.cw + PILL.pad;

function graphTrunc(s, n) {
  s = String(s == null ? "" : s);
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function renderGraph() {
  const svg = $("scenegraph");
  if (!svg) return;
  const scenes = (P && P.scenes) || [];
  if (!scenes.length) {
    svg.innerHTML = "";
    svg.setAttribute("width", 0);
    svg.setAttribute("height", 0);
    return;
  }
  const ids = scenes.map(s => s.id);
  const index = new Set(ids);

  const edges = [];
  const seen = new Set();
  scenes.forEach((s) => s.opts.forEach((o) => {
    const p = parseOpt(o);
    // `-> -` stays in the source scene; self-transitions do not move the story,
    // so they add no graph edge.
    const to = p.target === "-" ? s.id : p.target;
    if (!to || !index.has(to) || to === s.id) return;
    const key = s.id + "\u0000" + to;
    if (seen.has(key)) return;
    seen.add(key);
    edges.push({ from: s.id, to, label: p.label });
  }));

  // rank = BFS depth from the entry scene. Story graphs have cycles (scenes you
  // can revisit), so a longest-path rank would diverge; back-edges simply draw
  // as curves pointing up. Any scene not reachable from the entry gets its
  // own row block after the main component.
  const adj = new Map(ids.map(id => [id, []]));
  edges.forEach((e) => adj.get(e.from).push(e.to));
  const rank = new Map();
  let nextBase = 0;
  for (const start of ids) {
    if (rank.has(start)) continue;
    rank.set(start, nextBase);
    const q = [start];
    for (let head = 0; head < q.length; head++) {
      const u = q[head];
      for (const v of adj.get(u)) {
        if (!rank.has(v)) { rank.set(v, rank.get(u) + 1); q.push(v); }
      }
    }
    nextBase = Math.max(...rank.values()) + 1;
  }

  const byRank = new Map();
  scenes.forEach((s) => {
    const r = rank.get(s.id);
    if (!byRank.has(r)) byRank.set(r, []);
    byRank.get(r).push(s);
  });

  const { colw, rowh, nodew, nodeh, pad } = GRAPH;
  let maxRank = 0, cols = 0;
  byRank.forEach((list, r) => {
    if (r > maxRank) maxRank = r;
    if (list.length > cols) cols = list.length;
  });
  const pos = new Map();
  byRank.forEach((list, r) => {
    // Centre each row within the full canvas width so shorter rows sit under
    // the middle of the widest one, rather than hugging the left edge.
    const offset = (cols - list.length) * colw / 2;
    list.forEach((s, i) => {
      pos.set(s.id, { x: pad + offset + i * colw, y: pad + r * rowh });
    });
  });
  const width = pad * 2 + (cols - 1) * colw + nodew;
  const height = pad * 2 + maxRank * rowh + nodeh;

  // Anchor each edge on the side of a box that faces its partner: downward
  // edges leave the source's bottom and enter the target's top, upward edges
  // the reverse, and sideways edges connect left/right. Within a side, outgoing
  // and incoming edges are given separate lanes (and spread along the side) so
  // an input arrow never lands on top of an output arrow in the same box.
  const sideOf = (sp, tp) => {
    const dx = (tp.x + nodew / 2) - (sp.x + nodew / 2);
    const dy = (tp.y + nodeh / 2) - (sp.y + nodeh / 2);
    if (Math.abs(dy) >= Math.abs(dx))
      return { s: dy >= 0 ? "bottom" : "top", t: dy >= 0 ? "top" : "bottom" };
    return { s: dx >= 0 ? "right" : "left", t: dx >= 0 ? "left" : "right" };
  };
  const SIDES = ["top", "bottom", "left", "right"];
  const outBy = new Map(), inBy = new Map();
  const perNode = (map, id) => {
    if (!map.has(id)) map.set(id, { top: [], bottom: [], left: [], right: [] });
    return map.get(id);
  };
  edges.forEach((e) => {
    const side = sideOf(pos.get(e.from), pos.get(e.to));
    e._sSide = side.s; e._tSide = side.t;
    perNode(outBy, e.from)[side.s].push(e);
    perNode(inBy, e.to)[side.t].push(e);
  });
  // Outputs fan across the first half of a side, inputs across the second.
  const LANE = { out: [0.18, 0.5], in: [0.5, 0.82] };
  const anchor = (id, side, frac) => {
    const p = pos.get(id);
    if (side === "top") return { x: p.x + frac * nodew, y: p.y };
    if (side === "bottom") return { x: p.x + frac * nodew, y: p.y + nodeh };
    if (side === "left") return { x: p.x, y: p.y + frac * nodeh };
    return { x: p.x + nodew, y: p.y + frac * nodeh };
  };
  const applySlots = (by, outgoing) => {
    const prop = outgoing ? "_sFrac" : "_tFrac";
    const lane = outgoing ? LANE.out : LANE.in;
    by.forEach((sides) => {
      SIDES.forEach((side) => {
        const list = sides[side];
        // Order along the side by the partner's cross-axis centre so strands
        // need not cross one another.
        const key = (e) => {
          const other = pos.get(outgoing ? e.to : e.from);
          return (side === "top" || side === "bottom")
            ? other.x + nodew / 2 : other.y + nodeh / 2;
        };
        list.sort((a, b) => key(a) - key(b));
        const n = list.length;
        list.forEach((e, i) => {
          e[prop] = n === 1 ? (lane[0] + lane[1]) / 2
            : lane[0] + (lane[1] - lane[0]) * i / (n - 1);
        });
      });
    });
  };
  applySlots(outBy, true);
  applySlots(inBy, false);
  const geom = (e) => {
    const a = anchor(e.from, e._sSide, e._sFrac);
    const b = anchor(e.to, e._tSide, e._tFrac);
    let c1, c2;
    if (e._sSide === "top" || e._sSide === "bottom") {
      const my = (a.y + b.y) / 2;
      c1 = { x: a.x, y: my }; c2 = { x: b.x, y: my };
    } else {
      const mx = (a.x + b.x) / 2;
      c1 = { x: mx, y: a.y }; c2 = { x: mx, y: b.y };
    }
    return { a, b, c1, c2 };
  };
  edges.forEach((e) => { e._g = geom(e); });

  // Give every edge its own colour (golden-angle hues stay well separated)
  // and a matching arrow marker, so crossing lines can be told apart.
  const edgeColor = (i) => `hsl(${Math.round((i * 137.508) % 360)}, 68%, 62%)`;
  let defs = '<defs>';
  edges.forEach((e, i) => {
    e._color = edgeColor(i);
    defs += `<marker id="arrow${i}" viewBox="0 0 10 10" refX="9" refY="5" ` +
      `markerWidth="7" markerHeight="7" orient="auto-start-reverse">` +
      `<path d="M0,0 L10,5 L0,10 z" fill="${e._color}"/></marker>`;
  });
  let out = defs + '</defs>';

  // Place each label on its own edge curve: `at(t)` is the cubic's point at t,
  // so the pill sits over the arrow. Scan the curve for the point nearest the
  // middle where the pill clears every node and every label already placed.
  // Hovering a line reveals its pill at the pointer.
  const nodes = scenes.map((s) => {
    const p = pos.get(s.id);
    return { id: s.id, x: p.x, y: p.y, w: nodew, h: nodeh };
  });
  const placed = [];

  const labelPos = new Map();
  edges.forEach((e) => {
    if (!e.label) return;
    const { a, b, c1, c2 } = e._g;
    const text = graphTrunc(e.label, EDGE_MAX_LABEL);
    const lw = pillW(text), lh = PILL.h;
    const at = (t) => {
      const u = 1 - t;
      return {
        x: u*u*u*a.x + 3*u*u*t*c1.x + 3*u*t*t*c2.x + t*t*t*b.x,
        y: u*u*u*a.y + 3*u*u*t*c1.y + 3*u*t*t*c2.y + t*t*t*b.y,
      };
    };
    const boxAt = (q) => ({ x: q.x - lw / 2, y: q.y - PILL.top, w: lw, h: lh });
    // Pick the point along the curve (preferring the middle) where the pill
    // clears every node and every label already placed.
    let p = at(0.5);
    let best = null, bestCost = Infinity;
    for (let i = 0; i <= 20; i++) {
      const t = 0.1 + i * 0.04;
      const q = at(t);
      const box = boxAt(q);
      const cost = Math.abs(t - 0.5) * 100 +
        nodes.filter((r) => r.id !== e.from && r.id !== e.to &&
          box.x < r.x + r.w && box.x + box.w > r.x &&
          box.y < r.y + r.h && box.y + box.h > r.y).length * 10 +
        placed.filter((b) => box.x < b.x + b.w && box.x + box.w > b.x &&
          box.y < b.y + b.h && box.y + box.h > b.y).length;
      if (cost < bestCost) { bestCost = cost; best = q; }
      if (cost === 0) { p = q; break; }
    }
    if (best) p = best;
    // If the best point on the curve still covers a node or another label,
    // step just off the curve (nearest clear spot wins) so the pill stays
    // readable; its colour still ties it to its line.
    const clear = (box) =>
      !nodes.some((r) => r.id !== e.from && r.id !== e.to &&
        box.x < r.x + r.w && box.x + box.w > r.x &&
        box.y < r.y + r.h && box.y + box.h > r.y) &&
      !placed.some((b) => box.x < b.x + b.w && box.x + box.w > b.x &&
        box.y < b.y + b.h && box.y + box.h > b.y);
    if (bestCost > 0) {
      outer:
      for (let rad = 14; rad <= 96; rad += 14) {
        for (const [ox, oy] of [[0, rad], [0, -rad], [-rad, 0], [rad, 0],
                                [-rad, rad], [rad, rad], [-rad, -rad], [rad, -rad]]) {
          const q = { x: p.x + ox, y: p.y + oy };
          if (clear(boxAt(q))) { p = q; break outer; }
        }
      }
    }
    placed.push(boxAt(p));
    labelPos.set(e, p);
  });

  edges.forEach((e, i) => {
    const { a, b, c1, c2 } = e._g;
    const d = `M${a.x},${a.y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${b.x},${b.y}`;
    out += '<g class="edge-group">' +
      `<path class="edge" d="${d}" style="stroke:${e._color}" ` +
      `marker-end="url(#arrow${i})"/>`;
    if (e.label) {
      const p = labelPos.get(e);
      const text = graphTrunc(e.label, EDGE_MAX_LABEL);
      const lw = pillW(text);
      out += `<rect class="edge-label-bg" x="${p.x - lw / 2}" y="${p.y - PILL.top}" ` +
        `width="${lw}" height="${PILL.h}" rx="11" style="stroke:${e._color}"/>` +
        `<text class="edge-label" x="${p.x}" y="${p.y + PILL.base}" ` +
        `text-anchor="middle">${esc(text)}</text>`;
      e._ctrl = [a.x, a.y, c1.x, c1.y, c2.x, c2.y, b.x, b.y];
    }
    out += '</g>';
  });

  // A scene box takes the colour of the first arrow that points to it, so a
  // node and the edge leading into it read as the same strand. Entry scenes
  // (nothing points to them) keep the default border. Selection/hover/ending
  // styles still win by CSS specificity.
  const inColor = new Map();
  edges.forEach((e) => { if (!inColor.has(e.to)) inColor.set(e.to, e._color); });
  scenes.forEach((s) => {
    const p = pos.get(s.id);
    const cls = "node" + (s.ending ? " ending" : "") +
      (sel.kind === "scene" && sel.id === s.id ? " sel" : "");
    const sub = s.id + (s.ending ? ` · ${s.ending}` : "");
    const col = inColor.get(s.id);
    out += `<g class="${cls}" data-id="${esc(s.id)}"` +
      (col ? ` style="--edge:${col}"` : "") + ">" +
      `<rect x="${p.x}" y="${p.y}" width="${nodew}" height="${nodeh}" rx="6"/>` +
      `<text class="ntitle" x="${p.x + nodew / 2}" y="${p.y + 18}" ` +
      `text-anchor="middle">${esc(graphTrunc(s.title || s.id, 16))}</text>` +
      `<text class="nid" x="${p.x + nodew / 2}" y="${p.y + 33}" ` +
      `text-anchor="middle">${esc(graphTrunc(sub, 20))}</text>` +
      `</g>`;
  });

  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = out;
  svg.querySelectorAll(".node").forEach((g) => {
    g.addEventListener("click", () => {
      sel = { kind: "scene", id: g.dataset.id };
      selMemo.scene = g.dataset.id;
      setView("scenes");
    });
  });

  // Hovering near a line floats its label pill at the pointer. A pill hidden
  // by default (CSS) is revealed and moved on mousemove; leaving, or moving on
  // to a place that is not near any labeled line, hides it again. This works
  // for any label position — including pills that sit over other nodes.
  if (!svg._ghost) {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "edge-ghost");
    g.innerHTML =
      `<rect class="edge-label-bg" x="0" y="${-PILL.top}" width="0" ` +
      `height="${PILL.h}" rx="11"/>` +
      `<text class="edge-label" x="0" y="${PILL.base}" text-anchor="middle"></text>`;
    svg._ghost = g;
  }
  svg.appendChild(svg._ghost);
  svg._ghost.setAttribute("transform", "translate(-9999,-9999)");
  const ghost = svg._ghost;
  const ghostRect = ghost.querySelector("rect");
  const ghostText = ghost.querySelector("text");
  const labeled = edges.filter((e) => e.label);
  const segDist = (px, py, ax, ay, bx, by, cx, cy, dx, dy) => {
    let best = Infinity;
    for (let i = 0; i < 24; i++) {
      const t0 = i / 24, t1 = (i + 1) / 24, u = 1 - t0, v = 1 - t1;
      const x0 = u*u*u*ax + 3*u*u*t0*bx + 3*u*t0*t0*cx + t0*t0*t0*dx;
      const y0 = u*u*u*ay + 3*u*u*t0*by + 3*u*t0*t0*cy + t0*t0*t0*dy;
      const x1 = v*v*v*ax + 3*v*v*t1*bx + 3*v*t1*t1*cx + t1*t1*t1*dx;
      const y1 = v*v*v*ay + 3*v*v*t1*by + 3*v*t1*t1*cy + t1*t1*t1*dy;
      const ex = x1 - x0, ey = y1 - y0, len2 = ex*ex + ey*ey || 1;
      let tt = ((px - x0)*ex + (py - y0)*ey) / len2;
      tt = Math.max(0, Math.min(1, tt));
      const qx = x0 + tt*ex, qy = y0 + tt*ey;
      const dist = Math.hypot(px - qx, py - qy);
      if (dist < best) best = dist;
    }
    return best;
  };
  svg.onmousemove = (ev) => {
    const r = svg.getBoundingClientRect();
    const sx = (ev.clientX - r.left) / r.width * width;
    const sy = (ev.clientY - r.top) / r.height * height;
    let near = null, nd = 14;
    for (const e of labeled) {
      const c = e._ctrl;
      const d = segDist(sx, sy, c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7]);
      if (d < nd) { nd = d; near = e; }
    }
    if (!near) { ghost.setAttribute("transform", "translate(-9999,-9999)"); return; }
    const text = graphTrunc(near.label, EDGE_MAX_LABEL);
    const lw = pillW(text);
    ghostText.textContent = text;
    ghostRect.setAttribute("x", -lw / 2);
    ghostRect.setAttribute("width", lw);
    ghostRect.style.stroke = near._color;
    ghostText.style.fill = near._color;
    ghost.setAttribute("transform", `translate(${sx},${sy})`);
  };
  svg.onmouseleave = () => ghost.setAttribute("transform", "translate(-9999,-9999)");
}

function renderInventory() {
  const el = $("invlist");
  const items = (P.flags || []).filter(f => f.item)
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
  if (!items.length) { el.innerHTML = "<em>no items</em>"; return; }
  el.innerHTML = items.map(f => `<span class="badge item">${esc(f.name)}</span>`).join(" ");
}

