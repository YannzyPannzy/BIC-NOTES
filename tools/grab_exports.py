"""Save the cheat sheets into sheets/ after exporting them with the Claude Docs connector.

The Docs `export` tool (format "html") returns each cheat sheet inline as base64, which
also lands in this session's transcript. This script finds the newest export of each
cheat sheet there and writes it to sheets/algebra.html, discrete.html, physics.html.

Usage (from the repo root, after exporting all three):  python3 tools/grab_exports.py
"""
import base64, glob, os, pathlib, re

NAMES = {'College Algebra Cheat Sheet': 'algebra',
         'Discrete Maths Cheat Sheet': 'discrete',
         'Physics 1 Cheat Sheet': 'physics'}
pat = re.compile(r'name\\*":\\*"(' + '|'.join(map(re.escape, NAMES)) + r')\.html\\*".{0,300}?bytes_b64\\*":\\*"([A-Za-z0-9+/=]+)', re.S)

logs = sorted(glob.glob(os.path.expanduser('~/.claude/projects/**/*.jsonl'), recursive=True), key=os.path.getmtime)
found = {}
for log in logs:                      # oldest first, so the newest export wins
    for m in pat.finditer(pathlib.Path(log).read_text(errors='ignore')):
        found[m.group(1)] = m.group(2)

out_dir = pathlib.Path(__file__).resolve().parent.parent / 'sheets'
out_dir.mkdir(exist_ok=True)
for name, subject in NAMES.items():
    if name not in found:
        print(f'{subject}: no export found - kept the old copy')
        continue
    html = base64.b64decode(found[name]).decode('utf-8')
    assert html.startswith('<h1') and 'language-latex' in html, f'{subject}: export does not look right'
    path = out_dir / f'{subject}.html'
    changed = not path.exists() or path.read_text() != html
    path.write_text(html)
    date = re.search(r'datetime="([0-9-]+)"', html)
    print(f'{subject}: saved ({len(html)} bytes, doc dated {date.group(1) if date else "?"}){" - changed" if changed else ""}')
