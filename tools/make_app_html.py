"""Turn the published notebook artifact HTML into the lean file the BIC Notes iPhone app downloads.

Usage: python3 tools/make_app_html.py <artifact.html> notebook.html

- strips the artifact page skeleton (if present) and the big inline font/KaTeX style block
- adds a normal HTML head that loads the fonts and KaTeX CSS from the web instead
"""
import re, sys, pathlib

src = pathlib.Path(sys.argv[1]).read_text()
if src.lstrip().lower().startswith('<!doctype'):
    i = src.lower().find('<body>')
    if i != -1:
        src = src[i + len('<body>'):]
    src = re.sub(r'</body>\s*</html>\s*$', '', src, flags=re.I)
src = re.sub(r'<style>\s*@font-face.*?</style>', '', src, count=1, flags=re.S)
assert '@font-face' not in src, 'inline font block not removed'
assert 'katex.min.js' in src and 'class="subject"' in src, 'does not look like the notebook'

head = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Caveat:wght@600;700&family=Kalam:wght@300;400;700&display=swap">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;-webkit-text-size-adjust:100%}img{max-width:100%}[hidden]{display:none!important}</style>
</head><body>
'''
out = head + src.strip() + '\n</body></html>\n'
pathlib.Path(sys.argv[2]).write_text(out)
print(f'wrote {sys.argv[2]} ({len(out.encode())} bytes)')
