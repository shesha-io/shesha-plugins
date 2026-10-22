#!/usr/bin/env node
/* ─────────────────────────────────────────────────────────────────────────
 * shesha-design-comprehension / scripts/layout-probe.js        (Shesha 0.46)
 *
 * The measurement instrument for the design-comprehension layer.
 *
 * It walks a RENDERED page (a design prototype OR a built Shesha form) and
 * emits a structural layout JSON. Two layers of signal:
 *
 *  1. SHESHA LAYER (preferred on a built 0.46 form). Every live form component
 *     is wrapped in a div carrying data-sha-c-id / -name / -type / -property-name
 *     (sub-forms also -form-name). These attributes survive antd upgrades and
 *     hashed class names, so the probe anchors on them:
 *       - components[]      every wrapper: id, name, type, propertyName, rect,
 *                           nearest sha ancestor, tab membership, and for
 *                           containers the inner flex/grid facts + inner width
 *       - shaSplits[]       per parent component: x-clustered DIRECT sha children
 *                           (split-cell membership, widths) = the placement signal
 *       - tabPanes[]        per antd tabs component: label, active, and the sha
 *                           components mounted in each pane (works for inactive
 *                           panes too, so no need to click every tab)
 *       - placeholders[]    "Please, provide some content ..." Empty states and
 *                           "Component 'x' not registered" renderers
 *  2. GENERIC LAYER (for design prototypes that are not Shesha, and as a
 *     cross-check): bounding boxes, nesting depth, x-clustering into columns,
 *     y-banding into rows for every visible node (nodes[], multiColumnContainers[]).
 *
 * Nothing here depends on antd class names except tab labels, which are read from
 * role="tabpanel" / aria-labelledby (stable across antd 5 and 6) and a
 * best-effort `.ant-tabs` ancestor lookup.
 *
 * TWO WAYS TO RUN - the core (`PROBE_FN`) is identical in both:
 *
 *  A) Any browser tool that can evaluate JS in the page (Chrome extension
 *     javascript_tool, Playwright MCP browser_evaluate, DevTools console):
 *       1. navigate to the screen, set the pinned viewport
 *       2. node layout-probe.js --emit-eval [--root SEL] [--screen NAME] [--sha-only]
 *       3. evaluate the printed expression; save the returned JSON to a file.
 *
 *  B) Local Node + Playwright (CI / when playwright is installed):
 *       node layout-probe.js --url <url> --screen <name> --out <file.json> [--root SEL]
 *
 * Pin ONE fixed viewport for BOTH capture and verification (default 1440x900);
 * never compare measurements taken at different viewports.
 * ───────────────────────────────────────────────────────────────────────── */

'use strict';

// The probe runs INSIDE the page. Keep it self-contained (no closures over
// node scope) so it can be string-serialised for browser_evaluate / page.evaluate.
const PROBE_FN = function (opts) {
  opts = opts || {};
  var ROOT = opts.root || 'body';
  var X_TOL = opts.xTolerance == null ? 16 : opts.xTolerance; // px: same column band
  var Y_TOL = opts.yTolerance == null ? 14 : opts.yTolerance; // px: same row band
  var MIN_AREA = opts.minArea == null ? 24 : opts.minArea;    // ignore slivers
  var SHA_ONLY = !!opts.shaOnly;                              // omit generic nodes[] (smaller output)

  var rootEl = document.querySelector(ROOT) || document.body;

  function visible(el) {
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false;
    var r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  }

  function rectOf(el) {
    var r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }

  // Best-effort human label for a node, in priority order.
  function labelOf(el) {
    var aria = el.getAttribute && (el.getAttribute('aria-label') || el.getAttribute('placeholder'));
    if (aria) return aria.trim();
    if (el.id) {
      var lbl = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id) + '"]');
      if (lbl && lbl.textContent.trim()) return lbl.textContent.trim();
    }
    var own = '';
    for (var i = 0; i < el.childNodes.length; i++) {
      var n = el.childNodes[i];
      if (n.nodeType === 3 && n.textContent.trim()) { own += n.textContent.trim() + ' '; }
    }
    own = own.trim();
    if (own) return own.slice(0, 80);
    var t = (el.textContent || '').trim();
    return t ? t.slice(0, 80) : '';
  }

  function roleOf(el) {
    var tag = el.tagName.toLowerCase();
    var role = el.getAttribute && el.getAttribute('role');
    if (role) return role;
    if (/^h[1-6]$/.test(tag)) return 'heading';
    if (tag === 'button' || (typeof el.className === 'string' && /btn|button/i.test(el.className))) return 'button';
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return 'control';
    if (tag === 'table' || (typeof el.className === 'string' && /table|grid|datalist|datatable/i.test(el.className))) return 'table';
    if (tag === 'th') return 'col-header';
    if (tag === 'label') return 'label';
    if (tag === 'a') return 'link';
    var cs = getComputedStyle(el);
    if (cs.display === 'flex' || cs.display === 'grid' || cs.display === 'inline-flex') return 'container';
    return 'box';
  }

  function isContainer(el) {
    var cs = getComputedStyle(el);
    return cs.display === 'flex' || cs.display === 'grid' || cs.display === 'inline-flex' || el.children.length >= 2;
  }

  function clusterCol(rects) {
    var edges = rects.map(function (r) { return r.x; }).sort(function (a, b) { return a - b; });
    var bands = [];
    edges.forEach(function (x) {
      var b = bands.find(function (bb) { return Math.abs(bb - x) <= X_TOL; });
      if (b == null) bands.push(x);
    });
    bands.sort(function (a, b) { return a - b; });
    return bands;
  }
  function bandIndex(bands, x) {
    var ci = 0, best = Infinity;
    bands.forEach(function (band, idx) {
      var d = Math.abs(band - x);
      if (d < best) { best = d; ci = idx; }
    });
    return ci;
  }

  /* ── 1) SHESHA LAYER ───────────────────────────────────────────────────── */
  var shaEls = Array.prototype.slice.call(rootEl.querySelectorAll('[data-sha-c-id]'));
  var shaIndex = {}; // id -> record
  var components = [];

  function nearestSha(el) {
    var p = el.parentElement;
    while (p && p !== rootEl.parentElement) {
      if (p.hasAttribute && p.hasAttribute('data-sha-c-id')) return p;
      p = p.parentElement;
    }
    return null;
  }

  // tab membership: nearest role=tabpanel ancestor; label from aria-labelledby (rc-tabs sets it)
  function tabOf(el) {
    var p = el.parentElement;
    while (p && p !== rootEl.parentElement) {
      if (p.getAttribute && p.getAttribute('role') === 'tabpanel') {
        var lblId = p.getAttribute('aria-labelledby');
        var lblEl = lblId ? document.getElementById(lblId) : null;
        var owner = p.closest ? p.closest('[data-sha-c-type="tabs"]') : null;
        return {
          label: lblEl ? (lblEl.textContent || '').trim().slice(0, 60) : null,
          labelId: lblId || null,
          tabsId: owner ? owner.getAttribute('data-sha-c-id') : null,
          tabsName: owner ? owner.getAttribute('data-sha-c-name') : null
        };
      }
      p = p.parentElement;
    }
    return null;
  }

  shaEls.forEach(function (el) {
    var r = rectOf(el);
    var cs = getComputedStyle(el);
    var inner = el.querySelector('.sha-components-container');
    if (inner && nearestSha(inner) !== el) inner = null; // belongs to a nested component, not this one
    var innerBox = inner ? inner.querySelector(':scope > .sha-components-container-inner') : null;
    var ics = innerBox ? getComputedStyle(innerBox) : null;
    var ps = nearestSha(el);
    var rec = {
      id: el.getAttribute('data-sha-c-id'),
      name: el.getAttribute('data-sha-c-name'),
      type: el.getAttribute('data-sha-c-type'),
      propertyName: el.getAttribute('data-sha-c-property-name'),
      formName: el.getAttribute('data-sha-c-form-name') || undefined,
      parentShaId: ps ? ps.getAttribute('data-sha-c-id') : null,
      visible: visible(el),
      rect: r,
      cssWidth: cs.width,
      tab: tabOf(el)
    };
    if (ics) {
      rec.innerRect = rectOf(inner);                       // the container's own box (inside the wrapper)
      rec.layout = {
        display: ics.display,
        flexDirection: ics.display.indexOf('flex') >= 0 ? ics.flexDirection : null,
        gap: ics.display.indexOf('flex') >= 0 || ics.display.indexOf('grid') >= 0 ? ics.gap : null,
        overflow: ics.overflow
      };
      // wrapper vs container width: a calc() width applied to BOTH wrapper and container shrinks twice
      rec.doubleShrinkSuspect = r.w > 0 && rec.innerRect.w > 0 && rec.innerRect.w < r.w - 2;
    }
    shaIndex[rec.id] = rec;
    components.push(rec);
  });

  // split-cell membership per parent: x-cluster DIRECT sha children (visible only)
  var childrenOf = {};
  components.forEach(function (c) {
    if (c.parentShaId == null || !c.visible) return;
    (childrenOf[c.parentShaId] = childrenOf[c.parentShaId] || []).push(c);
  });
  var shaSplits = [];
  Object.keys(childrenOf).forEach(function (pid) {
    var kids = childrenOf[pid];
    var bands = clusterCol(kids.map(function (k) { return k.rect; }));
    kids.forEach(function (k) {
      k.colIndex = bandIndex(bands, k.rect.x);
      k.colCount = bands.length;
      k.rowBand = Math.round(k.rect.y / Y_TOL);
    });
    if (bands.length >= 2) {
      var p = shaIndex[pid];
      shaSplits.push({
        parentId: pid,
        parentName: p ? p.name : null,
        parentType: p ? p.type : null,
        parentWidth: p ? (p.innerRect ? p.innerRect.w : p.rect.w) : null,
        columnCount: bands.length,
        columnEdges: bands,
        cells: kids.map(function (k) {
          return { id: k.id, name: k.name, type: k.type, colIndex: k.colIndex, x: k.rect.x, w: k.rect.w, rowBand: k.rowBand };
        })
      });
    }
  });

  // tab panes (works for inactive panes: reads mounted descendants, not geometry)
  var tabPanes = [];
  Array.prototype.slice.call(rootEl.querySelectorAll('[data-sha-c-type="tabs"]')).forEach(function (tabsEl) {
    var panes = Array.prototype.slice.call(tabsEl.querySelectorAll('[role="tabpanel"]'));
    panes.forEach(function (pane) {
      // only panes owned by THIS tabs component (skip panes of nested tabs)
      var owner = pane.closest('[data-sha-c-type="tabs"]');
      if (owner !== tabsEl) return;
      var lblId = pane.getAttribute('aria-labelledby');
      var lblEl = lblId ? document.getElementById(lblId) : null;
      var names = [];
      Array.prototype.slice.call(pane.querySelectorAll('[data-sha-c-id]')).forEach(function (d) {
        var nearestTabs = d.parentElement ? d.parentElement.closest('[role="tabpanel"]') : null;
        if (nearestTabs === pane) names.push(d.getAttribute('data-sha-c-name'));
      });
      tabPanes.push({
        tabsId: tabsEl.getAttribute('data-sha-c-id'),
        tabsName: tabsEl.getAttribute('data-sha-c-name'),
        label: lblEl ? (lblEl.textContent || '').trim().slice(0, 60) : null,
        active: pane.getAttribute('aria-hidden') !== 'true',
        componentNames: names
      });
    });
  });

  // placeholders = something rendered nothing useful
  var placeholders = [];
  Array.prototype.slice.call(rootEl.querySelectorAll('.ant-empty')).forEach(function (e) {
    if (!visible(e)) return;
    var host = e.closest('[data-sha-c-id]');
    placeholders.push({
      kind: 'empty',
      text: (e.textContent || '').trim().slice(0, 100),
      componentName: host ? host.getAttribute('data-sha-c-name') : null,
      componentType: host ? host.getAttribute('data-sha-c-type') : null
    });
  });
  Array.prototype.slice.call(rootEl.querySelectorAll('[data-sha-c-id]')).forEach(function (e) {
    var t = (e.textContent || '');
    if (/Component '[^']+' not registered/.test(t) && e.children.length <= 3) {
      placeholders.push({
        kind: 'not-registered',
        text: t.trim().slice(0, 100),
        componentName: e.getAttribute('data-sha-c-name'),
        componentType: e.getAttribute('data-sha-c-type')
      });
    }
  });

  /* ── 2) GENERIC LAYER ──────────────────────────────────────────────────── */
  var nodes = [];
  var containers = [];
  if (!SHA_ONLY) {
    var idCounter = 0;
    var walk = function (el, depth, parentId) {
      if (!visible(el)) return;
      var r = el.getBoundingClientRect();
      if (r.width * r.height < MIN_AREA) return;
      var cs = getComputedStyle(el);
      var myId = idCounter++;
      nodes.push({
        id: myId,
        parentId: parentId,
        depth: depth,
        tag: el.tagName.toLowerCase(),
        role: roleOf(el),
        label: labelOf(el),
        shaName: el.getAttribute ? el.getAttribute('data-sha-c-name') : null,
        shaType: el.getAttribute ? el.getAttribute('data-sha-c-type') : null,
        rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
        flexDirection: (cs.display === 'flex' || cs.display === 'inline-flex') ? cs.flexDirection :
          (cs.display === 'grid' ? 'grid(' + (cs.gridTemplateColumns || '').split(' ').length + ')' : null),
        isContainer: isContainer(el)
      });
      for (var i = 0; i < el.children.length; i++) walk(el.children[i], depth + 1, myId);
    };
    walk(rootEl, 0, null);

    var byParent = {};
    nodes.forEach(function (n) {
      if (n.parentId == null) return;
      (byParent[n.parentId] = byParent[n.parentId] || []).push(n);
    });
    Object.keys(byParent).forEach(function (pid) {
      var kids = byParent[pid];
      var parent = nodes[+pid];
      var colBands = clusterCol(kids.map(function (k) { return k.rect; }));
      kids.forEach(function (k) {
        k.colIndex = bandIndex(colBands, k.rect.x);
        k.colCount = colBands.length;
        k.rowBand = Math.round(k.rect.y / Y_TOL);
      });
      if (colBands.length >= 2) {
        containers.push({
          parentId: +pid,
          parentLabel: parent.label,
          parentRole: parent.role,
          columnCount: colBands.length,
          columnEdges: colBands,
          childWidths: kids.map(function (k) { return k.rect.w; }),
          childIds: kids.map(function (k) { return k.id; })
        });
      }
    });
  }

  return {
    screen: opts.screen || (document.title || location.href),
    url: location.href,
    viewport: { w: window.innerWidth, h: window.innerHeight },
    capturedAt: opts.stamp || null, // pass a timestamp in; Date.now() is intentionally not called here
    shaComponentCount: components.length,
    components: components,
    shaSplits: shaSplits,
    tabPanes: tabPanes,
    placeholders: placeholders,
    nodeCount: nodes.length,
    multiColumnContainers: containers,
    nodes: nodes
  };
};

/* ── Node CLI ────────────────────────────────────────────────────────────── */
function parseArgs(argv) {
  var a = {};
  for (var i = 2; i < argv.length; i++) {
    var k = argv[i];
    if (k.indexOf('--') === 0) {
      var key = k.slice(2);
      var val = (argv[i + 1] && argv[i + 1].indexOf('--') !== 0) ? argv[++i] : true;
      a[key] = val;
    }
  }
  return a;
}

async function main() {
  var args = parseArgs(process.argv);
  var opts = {
    root: args.root || 'body',
    screen: args.screen || null,
    stamp: args.stamp || null,
    shaOnly: !!args['sha-only']
  };

  // Mode A helper: print the exact evaluate payload, then exit.
  if (args['emit-eval']) {
    var payload = '(' + PROBE_FN.toString() + ')(' + JSON.stringify(opts) + ')';
    process.stdout.write(payload + '\n');
    return;
  }

  // Mode B: drive a local Playwright browser.
  if (!args.url) {
    console.error('Usage:\n  node layout-probe.js --emit-eval [--root SEL] [--screen NAME] [--sha-only]\n' +
      '  node layout-probe.js --url <url> --screen <name> --out <file.json> [--root SEL] [--sha-only]');
    process.exit(2);
  }
  let chromium;
  try { ({ chromium } = require('playwright')); }
  catch (e) {
    console.error('Local playwright not installed. Use --emit-eval and run the payload through any in-page JS evaluator instead.');
    process.exit(3);
  }
  var vw = +(args.vw || 1440), vh = +(args.vh || 900);
  var browser = await chromium.launch();
  var page = await browser.newPage({ viewport: { width: vw, height: vh } });
  await page.goto(args.url, { waitUntil: 'networkidle' });
  if (args.wait) await page.waitForTimeout(+args.wait);
  var result = await page.evaluate(PROBE_FN, opts);
  await browser.close();
  var out = JSON.stringify(result, null, 2);
  if (args.out) {
    require('fs').writeFileSync(args.out, out);
    console.error('wrote ' + args.out + ' (' + result.shaComponentCount + ' sha components, ' +
      result.shaSplits.length + ' sha splits, ' + result.nodeCount + ' generic nodes, ' +
      result.placeholders.length + ' placeholders)');
  } else {
    process.stdout.write(out + '\n');
  }
}

if (require.main === module) main();
module.exports = { PROBE_FN };
