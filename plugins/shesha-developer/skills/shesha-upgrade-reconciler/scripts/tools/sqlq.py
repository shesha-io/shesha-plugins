"""Read-only SQL helper for a Windows SQL Server (no python driver needed: PowerShell + System.Data.SqlClient). Usage:

    SHREC_SQL='<connection string>' python scripts/shrec.py sqlq "select top 5 * from dbo.VersionInfo order by Version desc"

READ-ONLY by construction: only a single SELECT (or WITH ... SELECT) statement is accepted; anything that could change data or schema
(insert, update, delete, drop, alter, create, truncate, merge, exec, grant, into, xp_/sp_ procedures, ...) is refused before PowerShell
starts. The connection string comes ONLY from the SHREC_SQL environment variable of the current shell: it is never printed, logged,
written to a file or put in a command line. Ask the user for the connection string in their own shell; do not store it.
Needs Windows PowerShell (or pwsh) on PATH.
"""
import os
import re
import shutil
import subprocess

FORBIDDEN = re.compile(r'\b(insert|update|delete|drop|alter|create|truncate|merge|exec|execute|grant|revoke|backup|restore|into|xp_\w+|sp_\w+|openquery|openrowset|opendatasource|next\s+value\s+for)\b', re.I)


def check_select(q):
    s = q.strip().rstrip(';').strip()
    if not re.match(r'^(select|with)\b', s, re.I):
        raise ValueError('only a SELECT / WITH query is allowed')
    if ';' in s:
        raise ValueError('a single statement only')
    if FORBIDDEN.search(re.sub(r"'[^']*'", "''", s)):
        raise ValueError('the query contains a keyword that can write or execute; this helper is read-only')
    return s


PS = r"""$cn = New-Object System.Data.SqlClient.SqlConnection($env:SHREC_SQL); $cn.Open(); $cmd = $cn.CreateCommand(); $cmd.CommandText = $env:SHREC_Q; $cmd.CommandTimeout = 120
$r = $cmd.ExecuteReader(); $cols = 0..($r.FieldCount-1) | ForEach-Object { $r.GetName($_) }; ($cols -join ' | ')
while ($r.Read()) { ($cols | ForEach-Object { [string]$r[$_] }) -join ' | ' }; $cn.Close()"""


def run(q):
    """Returns (header, rows[list of list of str]); raises on a refused query or a failed run (the message never contains the connection string)."""
    if not os.environ.get('SHREC_SQL'):
        raise RuntimeError('set SHREC_SQL in your own shell first (connection string; never stored by this skill)')
    q = check_select(q)
    exe = shutil.which('powershell') or shutil.which('pwsh')
    if not exe:
        raise RuntimeError('PowerShell is not on PATH: this helper needs it to reach a Windows SQL Server')
    r = subprocess.run([exe, '-NoProfile', '-Command', PS], env=dict(os.environ, SHREC_Q=q), capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError('query failed: ' + (r.stderr.strip().splitlines() or ['no output'])[0][:200])
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    return lines[0].split(' | '), [l.split(' | ') for l in lines[1:]]


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 1
    try:
        h, rows = run(argv[0])
        print(' | '.join(h))
        for r in rows[:500]:
            print(' | '.join(r))
    except (ValueError, RuntimeError) as e:
        print('ERROR:', e)
        return 1
    return 0
