"""Syntax gate for embedded form scripts: every script a rule writes or rewrites must parse as an async function body,
the way Shesha evaluates it. One node process per batch. Requires Node 18+ on PATH."""
import json
import shutil
import subprocess

from core.project import require

_JS = ("const s=JSON.parse(require('fs').readFileSync(0,'utf8'));const bad=[];"
       "s.forEach((c,i)=>{try{new Function('return (async function(){\\n'+c+'\\n})')}catch(e){bad.push([i,e.message])}});"
       "process.stdout.write(JSON.stringify(bad));")


def syntax_errors(snippets):
    """[(index, message)] for every snippet that does not parse. Raises when node is missing or fails."""
    if not snippets:
        return []
    require(shutil.which('node') is not None, 'node is not on PATH: the syntax gate needs Node 18+')
    r = subprocess.run(['node', '-e', _JS], input=json.dumps(snippets), capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        raise RuntimeError('syntax gate failed to run: ' + (r.stderr or '')[:300])
    return json.loads(r.stdout)


def require_clean(new_snippets, old_snippets=None, what='rewrite'):
    """Refuse when the new scripts introduce syntax errors that the old ones did not have (index-aligned lists)."""
    before = {i for i, _ in syntax_errors(old_snippets)} if old_snippets else set()
    regress = [(i, m) for i, m in syntax_errors(new_snippets) if i not in before]
    require(not regress, f'{what} would introduce syntax errors: {regress[:3]}')
