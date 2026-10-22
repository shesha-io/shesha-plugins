"""DOM geometry chain walker (read-only): measure, do not guess, why a component is the wrong size or in the wrong place.

  shrec.py dom-chain <page-path-or-url> (--name <data-sha-c-name> | --selector <css> | --text <leaf text> [--closest <css>])
                     [--role local|deployed|reference] [--up 12] [--row auto|<k>|none] [--no-rules] [--viewport 1700x1000] [--wait 12000] [--json]

Finds ONE element on the rendered page, then prints for the element and each of its N ancestors: x, y, width, height, display, position,
flex, flex-direction, grid-template-columns, gap, width / min-width / max-width, overflow-x, child count, the data-sha-c-name when present,
and the stylesheet rules that matched and set width / height / flex / display / margin / grid / gap (with where the rule comes from).
With --name the three nested levels under the Shesha wrapper (wrapper, container, inner element) are listed as well, because on 0.46 the
flex-item sizing lives on the `sha-component` WRAPPER (from the device block's `dimensions`), while `style` code only reaches the INNER element (H48).

Row container: --row auto (default) takes the nearest ancestor that is display:flex/grid with 2+ children and lists ALL its DOM children,
flagging zero-size / display:none PLACEHOLDERS. A row whose inner element has 4 DOM children, 2 of them placeholders, defeats any script
that counts `row.children.length` (H48). --row <k> uses the k-th ancestor, --row none skips it.

Read-only: nothing is clicked or written (the browser guard aborts every write). Use it BEFORE changing a layout, and again after, at the
same viewport. Uses a fresh headless browser and the cached login of core.browse.session. No credentials are printed.
Record the placement outcome with  shrec.py verify --kind placement --result ok|fail --detail "<detail>".
"""
import argparse, json, os, sys

JS = r"""(a) => {
  const REL = /(^|[;{ ])(width|min-width|max-width|height|min-height|max-height|flex|flex-[a-z]+|display|grid[a-z-]*|gap|column-gap|row-gap|margin[a-z-]*|overflow[a-z-]*|position|inset|top|left)\s*:/;
  const short = (s, n) => { s = String(s == null ? '' : s); return s.length > n ? s.slice(0, n) + '...' : s; };
  const cn = (e) => (typeof e.className === 'string' ? e.className : (e.className && e.className.baseVal) || '');
  const find = () => {
    if (a.name) return document.querySelector('[data-sha-c-name="' + String(a.name).replace(/"/g, '') + '"]');
    if (a.selector) { try { return document.querySelector(a.selector); } catch (e) { return null; } }
    if (a.text) {
      const leaf = [...document.querySelectorAll('*')].find(e => e.childElementCount === 0 && (e.textContent || '').trim() === a.text);
      return leaf ? (a.closest ? leaf.closest(a.closest) : leaf) : null;
    }
    return null;
  };
  const source = (sh) => {
    if (sh.href) return sh.href.split('/').pop().split('?')[0].slice(0, 40);
    const n = [...document.querySelectorAll('style')].find(x => x.sheet === sh);
    if (n && n.getAttribute && n.getAttribute('data-styled')) return 'styled-components';
    if (n && n.getAttribute && n.getAttribute('data-emotion')) return 'emotion';
    return 'inline <style>';
  };
  const matched = (el) => {
    const out = [];
    const visit = (rules, sh) => {
      for (const r of rules) {
        if (r.cssRules && r.media) { let ok = true; try { ok = window.matchMedia(r.media.mediaText).matches; } catch (e) {} if (ok) visit(r.cssRules, sh); continue; }
        if (r.cssRules && !r.selectorText) { visit(r.cssRules, sh); continue; }
        if (!r.selectorText) continue;
        let m = false; try { m = el.matches(r.selectorText); } catch (e) {}
        if (m && REL.test(r.cssText)) out.push({ src: source(sh), rule: short(r.cssText, 240) });
      }
    };
    for (const sh of document.styleSheets) { let rs; try { rs = sh.cssRules; } catch (e) { continue; } if (rs) visit(rs, sh); }
    const inline = el.getAttribute && el.getAttribute('style');
    if (inline) out.push({ src: 'inline style attr', rule: short(inline, 240) });
    return a.rules ? out.slice(-5) : [];
  };
  const d = (e) => {
    const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    return { tag: e.tagName.toLowerCase(), cls: short(cn(e), 46), name: (e.dataset && e.dataset.shaCName) || '', kids: e.children.length,
      x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), display: cs.display, position: cs.position,
      flex: cs.flex, dir: cs.flexDirection, wrap: cs.flexWrap, cols: short(cs.gridTemplateColumns, 40), gap: cs.columnGap,
      width: cs.width, minW: cs.minWidth, maxW: cs.maxWidth, ov: cs.overflowX, margin: cs.margin };
  };
  const el = find();
  if (!el) return { error: 'element not found' };
  const out = { target: null, levels: [], chain: [], row: null };
  out.target = d(el);
  if (a.name) {
    const lv = [['wrapper', el], ['container', el.firstElementChild], ['inner', el.firstElementChild && el.firstElementChild.firstElementChild]];
    for (const [lab, x] of lv) if (x) out.levels.push(Object.assign({ level: lab, rules: matched(x) }, d(x)));
  }
  let e = el, i = 0, rowIdx = -1;
  for (; e && i <= a.up; i++, e = e.parentElement) {
    const o = Object.assign({ i, rules: matched(e) }, d(e));
    out.chain.push(o);
    if (a.row === 'auto' && rowIdx < 0 && i >= 1 && /flex|grid/.test(o.display) && o.kids >= 2) rowIdx = i;
  }
  if (a.row !== 'auto' && a.row !== 'none' && /^[0-9]+$/.test(a.row)) rowIdx = Number(a.row);
  if (rowIdx >= 0) {
    let r = el; for (let k = 0; k < rowIdx && r; k++) r = r.parentElement;
    if (r) {
      const kids = [...r.children].map((c, idx) => {
        const o = d(c); const zero = o.w === 0 || o.h === 0;
        o.idx = idx; o.placeholder = o.display === 'none' || (zero && c.childElementCount === 0);
        o.zero = zero; o.holdsTarget = c.contains(el); return o;
      });
      out.row = { ancestor: rowIdx, self: d(r), children: kids };
    }
  }
  return out;
}"""


def collect(pg, name=None, selector=None, text=None, closest=None, up=12, row='auto', rules=True):
    """Run the probe on a loaded page. Returns the result dict (key 'error' when the element is missing)."""
    return pg.evaluate(JS, {'name': name, 'selector': selector, 'text': text, 'closest': closest, 'up': up, 'row': str(row), 'rules': rules})


def _line(o, tag=''):
    nm = f' name={o["name"]}' if o.get('name') else ''
    return (f'{tag}<{o["tag"]}.{o["cls"]}>{nm} x={o["x"]} y={o["y"]} w={o["w"]} h={o["h"]} display={o["display"]} flex={o["flex"]} '
            f'width={o["width"]} min={o["minW"]} max={o["maxW"]} ov={o["ov"]} kids={o["kids"]}'
            + (f' dir={o["dir"]} wrap={o["wrap"]} gap={o["gap"]}' if 'flex' in o['display'] else '')
            + (f' cols={o["cols"]}' if o['display'] == 'grid' else ''))


def render(res):
    if res.get('error'):
        print('ERROR:', res['error']); return
    print('TARGET', _line(res['target']))
    for lv in res.get('levels') or []:
        print('  ' + _line(lv, f'[{lv["level"]}] '))
        for r in lv.get('rules') or []: print(f'      rule ({r["src"]}): {r["rule"]}')
    print('CHAIN (i=0 is the target, then each ancestor)')
    for o in res['chain']:
        print('  ' + _line(o, f'i{o["i"]} '))
        for r in o.get('rules') or []: print(f'      rule ({r["src"]}): {r["rule"]}')
    row = res.get('row')
    if not row:
        print('ROW: no flex/grid ancestor with 2+ children found (or --row none)'); return
    print(f'ROW CONTAINER = ancestor i{row["ancestor"]}: {_line(row["self"])}')
    ph = [c for c in row['children'] if c['placeholder']]
    sized = [c for c in row['children'] if not c['zero'] and c['display'] != 'none']
    for c in row['children']:
        flag = ' PLACEHOLDER (zero-size / display:none)' if c['placeholder'] else (' ZERO-SIZE' if c['zero'] else '')
        print('  ' + _line(c, f'child{c["idx"]}{" *holds target*" if c["holdsTarget"] else ""} ') + flag)
    print(f'ROW HAS {len(row["children"])} DOM children: {len(sized)} sized, {len(ph)} placeholder(s). '
          + ('A script that counts row.children (e.g. === 2) will not match this row (H48).' if ph else 'No placeholders.'))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='shrec dom-chain', description='DOM geometry chain walker (read-only). See the module docstring.')
    ap.add_argument('page', help='page path (/dynamic/Module/form?id=..) or full URL')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--name', help='data-sha-c-name of the component')
    g.add_argument('--selector', help='CSS selector (first match)')
    g.add_argument('--text', help='exact text of a leaf element')
    ap.add_argument('--closest', help='with --text: climb to this ancestor selector first')
    ap.add_argument('--role', default='local', choices=['local', 'deployed', 'reference'])
    ap.add_argument('--up', type=int, default=12, help='ancestors to walk (default 12)')
    ap.add_argument('--row', default='auto', help='auto | <k-th ancestor> | none')
    ap.add_argument('--no-rules', action='store_true', help='skip the matched stylesheet rules')
    ap.add_argument('--viewport', default='1700x1000')
    ap.add_argument('--wait', type=int, default=12000)
    ap.add_argument('--json', action='store_true', help='print the raw result as JSON')
    a = ap.parse_args(argv)
    from core.browse import session, settle
    w, h = (int(x) for x in a.viewport.lower().split('x'))
    with session(a.role, viewport=(w, h)) as pg:
        pg.goto(a.page); settle(pg, a.wait)
        res = collect(pg, a.name, a.selector, a.text, a.closest, a.up, a.row, not a.no_rules)
    if a.json: print(json.dumps(res, indent=1))
    else: render(res)
    return 1 if res.get('error') else 0


if __name__ == '__main__':
    sys.exit(main())
