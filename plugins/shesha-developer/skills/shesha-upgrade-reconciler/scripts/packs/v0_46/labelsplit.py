"""Rule `split_labels` (H20, targeted): give a field with a MULTI-LINE label its label as a separate text component.

Symptom on 0.46: a label that wraps to two lines overlaps the next row.
Cause: 0.46 / antd 6 fixes the label element at `var(--ant-form-label-height)` (32px). The variable is defined on the label
column itself, so no Appearance, Custom style or ancestor setting can change it. Fixed in 0.46.1 per its release notes
(not verified).

Writes (all ordinary components, no stylesheet), for every non-required field whose static label is in the measured list:
  row container (horizontal, align-items center, takes the field's visibility)
    text label    width = the label column share, right-aligned, the label font (default 14px / 400 / rgba(0,0,0,0.88) /
                  theme font = the Ant Design form-label look), 13px right gap (antd's label ::after), wraps freely
    field holder  container, width 'stretch' (flex: 1)
      field       unchanged except hideLabel: true (its own label is kept in `_reconcilerLabel`)
The input therefore starts at the same x as the inputs of normal fields in the same column. Existing split labels of the
form are resized to the current share first. The label share follows the labelCol the form renders with: the hosting
subForm's labelCol (majority across hosts, from ctx.session.forms()), else the form's own settings, else 8.
Templates: a working v7 `text` and v9 `container` from the same form when present, else the minimal bundled ones
(`bundled_text()` / `bundled_container()`, built in code). Required fields are skipped (their red mark would be lost)
and reported as INFO. Ids derive from the field id, so a field already wrapped is skipped (idempotent).
Marker: the `-row046` / `-lbl046` / `-hold046` id suffixes and the `_reconcilerLabel` key.
No retire: the split is a structural rewrite that projects keep once their forms are checked, and 0.46.1 (release notes)
makes the label height follow the content, so nothing needs to be undone automatically.

Options: labelSplitFont - the label text font ({size, weight, color, type}; each key overrides one default; default
14 / '400' / rgba(0, 0, 0, 0.88) / 'inherit' = the theme font, which is the antd form-label look; a project whose labels
are bold or use another typeface sets e.g. {"weight": "700", "type": "Segoe UI"}). The 13px right gap and the 0px
container gaps are fixed: they reproduce antd's own label geometry and are framework-neutral.
labelSplit - the MEASURED list of wrapping labels: either a list of label texts, or a path (absolute, or
relative to the project root) to a sweep measurement file / directory of them. A sweep file is JSON of the shape
{"main": {"labelOverflow": [...]}, "tabs": [{"defects": {"labelOverflow": [...]}, "sub": [{"defects": {...}}]}]}; a plain
JSON list of strings is accepted too. Unset = no-op.
"""
import collections
import copy
import glob
import json
import os

from core import project
from core.project import require
from core.tree import walk
from packs.v0_46.common import flush

ROW, LABEL_SUFFIX, HOLD = '-row046', '-lbl046', '-hold046'
FIELD_TYPES = {'textField', 'dropdown', 'checkbox', 'dateField', 'numberField', 'textArea', 'autocomplete', 'entityReference',
               'address', 'radio', 'switch', 'timePicker', 'checkboxGroup', 'currency', 'password', 'refListStatus', 'numericInput'}


# ------------------------------------------------------------------ bundled templates (component versions: text 7, container 9)
def _block(font=None, dimensions=None):
    b = {'border': {'hideBorder': False, 'radiusType': 'all', 'borderType': 'all',
                    'border': {'all': {'width': 1, 'style': 'none', 'color': '#d9d9d9'}, 'top': {}, 'bottom': {}, 'left': {}, 'right': {}},
                    'radius': {'all': 8}},
         'background': {'type': 'color', 'color': '', 'repeat': 'no-repeat', 'size': 'auto', 'position': 'center',
                        'gradient': {'direction': 'to right', 'colors': []}, 'url': ''},
         'font': font or {'align': 'left', 'weight': '400'},
         'dimensions': dimensions or {'width': 'auto', 'height': 'auto', 'minHeight': '0px', 'maxHeight': 'none',
                                      'minWidth': '0px', 'maxWidth': 'none'},
         'shadow': {'offsetX': 0, 'offsetY': 0, 'color': '#000', 'blurRadius': 0, 'spreadRadius': 0},
         'stylingBox': '{}', 'enableStyleOnReadonly': False, 'stylingBoxJson': {'_type': 'styleBox'}}
    return b


def bundled_text():
    """minimal `text` v7 (the shape the 0.46 designer saves), used as a template for split labels"""
    font = {'color': 'rgba(0, 0, 0, 0.88)', 'type': 'inherit', 'align': 'left', 'size': 14, 'weight': '400'}
    dims = {'width': 'fit-content', 'height': 'auto', 'minHeight': '0px', 'maxHeight': 'auto', 'minWidth': '0px', 'maxWidth': 'auto'}
    return {'code': False, 'copyable': False, 'delete': False, 'ellipsis': False, 'mark': False, 'italic': False,
            'underline': False, 'level': 1, 'textType': 'span', 'id': 'bundled-text', 'type': 'text', 'propertyName': 'text',
            'componentName': 'text', 'label': 'Text', 'labelAlign': 'right', 'parentId': None, 'isDynamic': False, 'version': 7,
            'contentDisplay': 'content', 'textAlign': 'start', 'content': '', 'dataType': 'string', 'contentType': 'primary',
            'fontSize': 'text-sm', 'padding': 'none', 'strong': True, 'enableStyleOnReadonly': False,
            'desktop': _block(dict(font), dict(dims)), 'tablet': _block(dict(font), dict(dims)), 'mobile': _block(dict(font), dict(dims))}


def bundled_container():
    """minimal `container` v9 (the shape the 0.46 designer saves), used as a template for the row and holder containers"""
    def dev():
        d = _block()
        d.update({'display': 'flex', 'direction': 'horizontal', 'justifyContent': 'start', 'flexWrap': 'wrap', 'gap': '8px'})
        return d
    return {'id': 'bundled-container', 'type': 'container', 'propertyName': 'container', 'componentName': 'container',
            'label': 'Container', 'labelAlign': 'right', 'parentId': None, 'isDynamic': False, 'version': 9,
            'direction': 'horizontal', 'justifyContent': 'start', 'flexWrap': 'wrap',
            'desktop': dev(), 'tablet': dev(), 'mobile': dev()}


# ------------------------------------------------------------------ the split itself
def _devices(c, fn):
    for dev in ('desktop', 'tablet', 'mobile'):
        if isinstance(c.get(dev), dict):
            fn(c[dev])


DEFAULT_FONT = {'size': 14, 'weight': '400', 'color': 'rgba(0, 0, 0, 0.88)', 'type': 'inherit'}   # the antd form-label look


def split(holder_list, idx, text_tpl, cont_tpl, label_share='33.333%', allow_required=False, font=None):
    f = holder_list[idx]
    fid = f['id']
    require(not fid.endswith(HOLD), 'already a holder')
    label = f.get('label')
    require(isinstance(label, str) and label.strip(), f'{f.get("componentName")}: label is not static text')
    req = (f.get('validate') or {}).get('required')
    if req not in (None, False) and not (isinstance(req, dict) and req.get('_mode') != 'code' and not req.get('_value')):
        require(allow_required, f'{f.get("componentName")}: required field, label split would drop the required mark')
    parent_id = f.get('parentId')

    row = copy.deepcopy(cont_tpl)
    row.pop('components', None)
    row.update({'id': fid + ROW, 'componentName': f'{f.get("componentName")}Row046', 'propertyName': f'{f.get("componentName")}Row046',
                'label': 'Label row (0.46 multi-line label)', 'parentId': parent_id, 'direction': 'horizontal',
                'justifyContent': 'start', 'flexWrap': 'nowrap', 'alignItems': 'center',
                'visible': copy.deepcopy(f.get('visible', True))})
    row.pop('hidden', None)

    def rowdev(d):
        d.update({'display': 'flex', 'direction': 'horizontal', 'justifyContent': 'start', 'flexWrap': 'nowrap',
                  'alignItems': 'center', 'gap': '0px'})
        d.setdefault('dimensions', {}).update({'width': 'auto', 'minHeight': '0px'})
        d['stylingBoxJson'] = {'_type': 'styleBox', 'marginBottom': '2'}
    _devices(row, rowdev)

    txt = copy.deepcopy(text_tpl)
    txt.update({'id': fid + LABEL_SUFFIX, 'componentName': f'{f.get("componentName")}Label046', 'propertyName': f'{f.get("componentName")}Label046',
                'label': 'Label text', 'parentId': fid + ROW, 'content': label.strip(), 'textAlign': 'end', 'strong': True,
                'visible': True, 'contentType': 'custom'})   # 'primary' (template) paints colorPrimary; 'custom' uses font.color
    txt.pop('hidden', None)

    font_cfg = font

    def txtdev(d):
        font = d.setdefault('font', {})
        # type 'inherit': an absent type falls back to the text default font; inherit keeps the theme font
        font.update({**(font_cfg or DEFAULT_FONT), 'align': 'right'})
        if 'contentType' in d:
            d['contentType'] = 'custom'
        d.setdefault('dimensions', {}).update({'width': label_share, 'minWidth': label_share, 'maxWidth': label_share,
                                               'height': 'auto', 'minHeight': '0px'})
        d['stylingBoxJson'] = {'_type': 'styleBox', 'paddingRight': '13'}
    _devices(txt, txtdev)

    hold = copy.deepcopy(cont_tpl)
    hold.pop('components', None)
    hold.update({'id': fid + HOLD, 'componentName': f'{f.get("componentName")}Holder046', 'propertyName': f'{f.get("componentName")}Holder046',
                 'label': 'Field holder', 'parentId': fid + ROW, 'direction': 'vertical', 'justifyContent': 'start',
                 'visible': True})
    hold.pop('hidden', None)

    def holddev(d):
        d.update({'display': 'block', 'direction': 'vertical', 'justifyContent': 'start', 'gap': '0px'})
        d.setdefault('dimensions', {}).update({'width': 'stretch', 'minHeight': '0px'})
        d['stylingBoxJson'] = {'_type': 'styleBox'}
    _devices(hold, holddev)

    f['_reconcilerLabel'] = label
    f['hideLabel'] = True
    f['parentId'] = fid + HOLD
    hold['components'] = [f]
    row['components'] = [txt, hold]
    holder_list[idx] = row
    return f'{f.get("componentName")}: label moved into its own text ({label.strip()[:40]})'


def set_label_share(c, share):
    """Resize a split label to the label column share (e.g. labelCol 10 -> '41.667%'). Returns 1 if changed."""
    if c.get('type') != 'text' or not c['id'].endswith(LABEL_SUFFIX):
        return 0
    n = 0
    for dev in ('desktop', 'tablet', 'mobile'):
        d = c.get(dev)
        if not isinstance(d, dict):
            continue
        dims = d.setdefault('dimensions', {})
        for k in ('width', 'minWidth', 'maxWidth'):
            if dims.get(k) != share:
                dims[k] = share
                n = 1
    return n


# ------------------------------------------------------------------ discovery
def holder_lists(o, out):
    if isinstance(o, dict):
        for v in o.values():
            holder_lists(v, out)
    elif isinstance(o, list):
        for i, x in enumerate(o):
            if isinstance(x, dict) and 'type' in x and 'id' in x:
                out.append((o, i))
            holder_lists(x, out)
    return out


def norm(t):
    return ' '.join((t or '').replace(':', ' ').split()).strip().lower()


def own_label_col(m):
    s = m.get('formSettings') or {}
    lc = s.get('labelCol')
    if isinstance(lc, dict):
        lc = lc.get('span')
    return lc if isinstance(lc, int) and lc > 0 else 8


def label_cols(session):
    """{form key: labelCol it renders with (hosting subForms' majority)}; keys are 'Module/name' (and bare 'name')."""
    votes = collections.defaultdict(collections.Counter)
    for row in session.forms():
        mk = row.get('markup')
        try:
            tree = json.loads(mk) if isinstance(mk, str) else (mk or {})
        except ValueError:
            continue
        for c, _, _ in walk(tree):
            f = c.get('formId')
            if c.get('type') == 'subForm' and isinstance(f, dict) and f.get('name') and isinstance(c.get('labelCol'), int):
                votes[f['name']][c['labelCol']] += 1
                if f.get('module'):
                    votes[f"{f['module']}/{f['name']}"][c['labelCol']] += 1
    return {k: v.most_common(1)[0][0] for k, v in votes.items()}


def labels_from_option(value, base=None):
    """The set of label texts named by the `labelSplit` option (list of texts, or path to sweep measurement file(s))."""
    if isinstance(value, (list, tuple)):
        require(all(isinstance(x, str) for x in value), 'option labelSplit: a list must hold label texts (strings)')
        return set(value)
    require(isinstance(value, str) and value, 'option labelSplit must be a list of label texts or a path to a sweep measurement file')
    path = value if os.path.isabs(value) else os.path.join(base or os.getcwd(), value)
    require(os.path.exists(path), f'option labelSplit: {path} does not exist')
    files = sorted(glob.glob(os.path.join(path, '*.json'))) if os.path.isdir(path) else [path]
    out = set()
    for f in files:
        d = project.read_json(f)
        require(d is not None, f'option labelSplit: {f} is not valid JSON')
        if isinstance(d, list):
            out |= {x for x in d if isinstance(x, str)}
            continue
        blocks = [d.get('main') or {}] + [t.get('defects') or {} for t in d.get('tabs', [])] \
            + [s.get('defects') or {} for t in d.get('tabs', []) for s in t.get('sub', [])]
        for b in blocks:
            out |= {x for x in (b.get('labelOverflow') or []) if isinstance(x, str)}
    return out


def _font(ctx):
    raw = ctx.opt('labelSplitFont')
    if raw is None:
        return None
    require(isinstance(raw, dict) and raw and set(raw) <= {'size', 'weight', 'color', 'type'},
            'option labelSplitFont must be an object with keys from size, weight, color, type')
    return {**DEFAULT_FONT, **raw}


def _wanted(ctx):
    raw = ctx.opt('labelSplit')
    if not raw:
        return set()

    def build():
        return {norm(x) for x in labels_from_option(raw, project.find_root())}
    return ctx.cache('split_labels.wanted', build)


def _templates(m):
    comps = {c['id']: c for c, _, _ in walk(m)}
    txt = next((c for c in comps.values() if c['type'] == 'text' and c.get('version') == 7 and isinstance((c.get('desktop') or {}).get('font'), dict)), None)
    cont = next((c for c in comps.values() if c['type'] == 'container' and c.get('version') == 9 and isinstance(c.get('desktop'), dict)), None)
    return txt or bundled_text(), cont or bundled_container()


def apply(ctx, markup):
    want = _wanted(ctx)
    if not want:
        return 0
    txt, cont = _templates(markup)
    cols = ctx.cache('split_labels.label_cols', lambda: label_cols(ctx.session))
    lc = cols.get(ctx.form, cols.get(ctx.name))
    if lc is None:
        lc = own_label_col(markup)
    share = f'{lc / 24 * 100:.3f}%'
    font = _font(ctx)
    n = 0
    resized = sum(set_label_share(c, share) for c, _, _ in walk(markup))
    if resized:
        ctx.note(f'{resized} split label(s) resized')
        n += resized
    for lst, i in holder_lists(markup, []):
        f = lst[i]
        if f.get('type') not in FIELD_TYPES or f.get('hideLabel') is True:
            continue
        lab = f.get('label')
        if not isinstance(lab, str) or norm(lab) not in want:
            continue
        try:
            ctx.note(split(lst, i, txt, cont, label_share=share, font=font))
            n += 1
        except project.WriteRefused as e:
            ctx.info(f'label split skipped: {str(e)[:160]}')
    return n
