"""Turn the published notebook artifact HTML into the lean file the BIC Notes iPhone app downloads.

Usage: python3 tools/make_app_html.py <artifact.html> notebook.html [sheets_dir]

- strips the artifact page skeleton (if present) and the big inline font/KaTeX style block
- adds a normal HTML head that loads the fonts and KaTeX CSS from the web instead
- puts the three cheat sheets inside the app: sheets/algebra.html, discrete.html, physics.html
  (Claude Docs html exports) become pages at #cheat-algebra etc., and the
  "Open the cheat sheet" links point there instead of claude.ai
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

# ---------- cheat sheets inside the app ----------
SUBJECTS = ['algebra', 'discrete', 'physics']
sheets_dir = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else pathlib.Path(__file__).resolve().parent.parent / 'sheets'


# ---- stacking wide formulas for the phone ----
# The cheat sheets were laid out for a wide page, with several formulas side by side
# (separated by \qquad) and long  A => B => C  chains. On a phone those become separate lines.

def top_level_commands(tex):
    """Yield (position, name) for every command outside braces and environments."""
    i, depth, env, n = 0, 0, 0, len(tex)
    while i < n:
        c = tex[i]
        if c == '\\':
            m = re.match(r'\\([A-Za-z]+|.)', tex[i:])
            name = m.group(1)
            if name == 'begin':
                env += 1
            elif name == 'end':
                env -= 1
            elif depth == 0 and env == 0:
                yield i, name
            i += len(m.group(0))
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1


def tidy(parts):
    parts = [re.sub(r'^(?:\\[ ,;]|\\q?quad|\s)+|(?:\\[ ,;]|\\q?quad|\s)+$', '', p) for p in parts]
    return [p for p in parts if p]


def split_gaps(tex):
    """Cut at runs of \\qquad (a lone \\quad is just spacing inside one formula)."""
    cuts = []
    for pos, name in top_level_commands(tex):
        if name == 'qquad' and not (cuts and pos < cuts[-1][1]):
            g = re.match(r'(?:\\q?quad\s*)+', tex[pos:])
            cuts.append((pos, pos + len(g.group(0))))
    parts, start = [], 0
    for a, b in cuts:
        parts.append(tex[start:a]); start = b
    parts.append(tex[start:])
    return tidy(parts)


def split_arrows(tex, longer_than=60):
    """Put each => step of a long chain on its own line, starting with the arrow."""
    if len(tex) <= longer_than:
        return [tex]
    cuts = [pos for pos, name in top_level_commands(tex) if name == 'Rightarrow']
    if not cuts:
        # A = B = C  ->  "A = B" then "= C" on the next line
        eq, depth, env, i = [], 0, 0, 0
        while i < len(tex):
            c = tex[i]
            if c == '\\':
                m = re.match(r'\\([A-Za-z]+|.)', tex[i:])
                env += {'begin': 1, 'end': -1}.get(m.group(1), 0)
                i += len(m.group(0)); continue
            depth += {'{': 1, '}': -1}.get(c, 0)
            if c == '=' and depth == 0 and env == 0:
                eq.append(i)
            i += 1
        if len(eq) < 2:
            return [tex]
        parts, start = [], 0
        for pos in eq[1:]:
            parts.append(tex[start:pos]); start = pos
        parts.append(tex[start:])
        return tidy(parts)
    parts, start = [], 0
    for pos in cuts:
        parts.append(tex[start:pos]); start = pos
    parts.append(tex[start:])
    parts = tidy(parts)
    return [re.sub(r'^\\Rightarrow(?:\\[ ,;]|\\q?quad|\s)*', r'\\Rightarrow\\; ', p) for p in parts]


def whole_group(tex, prefix):
    """If tex is exactly  prefix{...}  return the inside, else None."""
    if not tex.startswith(prefix + '{'):
        return None
    depth = 0
    for i in range(len(prefix), len(tex)):
        if tex[i] == '\\':
            continue
        if tex[i] == '{' and tex[i - 1] != '\\':
            depth += 1
        elif tex[i] == '}' and tex[i - 1] != '\\':
            depth -= 1
            if depth == 0:
                return tex[len(prefix) + 1:i] if i == len(tex) - 1 else None
    return None


def split_one(part):
    """Split a part that is wholly coloured or boxed, keeping the colour/box on each piece."""
    inner = whole_group(part, r'\boxed')
    if inner is not None:
        core = inner.strip()
        if core.startswith('\\ '):
            core = core[2:]
        if core.endswith('\\'):
            core = core[:-1]
        core = core.strip()
        m = re.match(r'\\textcolor\{(#[0-9a-fA-F]{6})\}', core)
        body = whole_group(core, m.group(0)) if m else None
        if body is not None:
            return ['\\boxed{\\ \\textcolor{%s}{%s}\\ }' % (m.group(1), p) for p in split_gaps(body)]
        return [part]
    m = re.match(r'\\textcolor\{(#[0-9a-fA-F]{6})\}', part)
    body = whole_group(part, m.group(0)) if m else None
    if body is not None:
        return ['\\textcolor{%s}{%s}' % (m.group(1), p) for p in split_gaps(body)]
    return [part]


def split_gathered(tex):
    """Inside \\begin{gathered}, turn the \\qquad gaps of each row into new rows."""
    def fix(m):
        rows = re.split(r'\\\\', m.group(1))
        out = [p for row in rows for p in split_gaps(row.strip())]
        return '\\begin{gathered} ' + ' \\\\ '.join(out) + ' \\end{gathered}'
    return re.sub(r'\\begin\{gathered\}(.*?)\\end\{gathered\}', fix, tex, flags=re.S)


# Formulas too long for one phone line and with nothing to split at: a phone layout.
# If the cheat sheet's wording changes, the original won't match and it simply scrolls sideways.
PHONE_TEX = {
    r'\boxed{\ \textcolor{#1d4ed8}{|A \cup B \cup C| = |A| + |B| + |C| - |A \cap B| - |A \cap C| - |B \cap C|} \textcolor{#dc2626}{\,+ |A \cap B \cap C|}\ }':
    r'\boxed{\ \begin{aligned} \textcolor{#1d4ed8}{|A \cup B \cup C|} &\textcolor{#1d4ed8}{= |A| + |B| + |C|} \\ &\textcolor{#1d4ed8}{\quad - |A \cap B| - |A \cap C| - |B \cap C|} \\ &\textcolor{#dc2626}{\quad + |A \cap B \cap C|} \end{aligned}\ }',
}


def split_wide(tex):
    tex = tex.strip()
    if tex in PHONE_TEX:
        return [PHONE_TEX[tex]]
    tex = split_gathered(tex)
    out = []
    for part in split_gaps(tex):
        for piece in split_one(part):
            out.extend(split_arrows(piece))
    return out


def sheet_section(subject, html):
    # drop the doc's date/author line
    html = re.sub(r'<p>\s*<time[^>]*>.*?</time>.*?</p>', '', html, count=1, flags=re.S)
    # drop the doc's colour key: the notebook already shows the same key at the top
    html = re.sub(r'<pre><code class="language-latex">\\begin\{array\}\{ccc\}\s*\\textcolor\{#1d4ed8\}\{\\large\\textsf\{\\textbf\{MUST KNOW\}\}\}.*?</code></pre>',
                  '', html, count=1, flags=re.S)
    # latex blocks -> notebook maths blocks (rendered by the notebook's own KaTeX code)
    html = re.sub(r'<pre><code class="language-latex">(.*?)</code></pre>',
                  lambda m: ''.join('<div class="m d">' + p + '</div>' for p in split_wide(m.group(1).strip())),
                  html, flags=re.S)
    assert 'MUST KNOW' not in html, f'{subject}: colour key not removed'
    assert '<pre' not in html, f'{subject}: unexpected code block left'
    # wide tables scroll sideways on the phone
    html = re.sub(r'<table>(.*?)</table>', r'<div class="tbl"><table>\1</table></div>', html, flags=re.S)
    # heading ids from the doc could clash with the notebook's ids
    html = re.sub(r'<(h[1-6]) id="[^"]*">', r'<\1>', html)
    return (f'<section class="cheat" id="cheat-{subject}" hidden>\n'
            f'<p class="sheet-link back"><a href="#{subject}">← Back to notes</a></p>\n'
            f'{html.strip()}\n'
            f'<p class="sheet-link back"><a href="#{subject}">← Back to notes</a></p>\n'
            f'</section>\n')


CHEAT_CSS = '''<style>
.cheat{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-weight:400;font-size:1rem;line-height:1.55;padding-block:14px 8px}
.cheat .back{margin:4px 0 0}
.cheat h1{font-family:inherit;font-size:1.65rem;font-weight:700;margin:14px 0 4px}
.cheat h2{font-family:inherit;font-size:1.2rem;font-weight:700;margin:30px 0 8px;padding-bottom:4px;border-bottom:1.5px solid var(--rule)}
.cheat p{margin:10px 0 4px}
.cheat ul,.cheat ol{margin:6px 0;padding-left:1.4em}
.cheat li p{margin:2px 0}
.cheat .tbl th,.cheat .tbl td{border:1px solid #cbd5e1;padding:4px 10px}
.cheat .tbl th{background:#f8fafc}
.cheat .m.d{margin:2px 0 6px}
.cheat .katex-display>.katex{text-align:left}
@media (max-width:640px){.cheat .katex{font-size:1em}}
</style>
'''

CHEAT_JS = '''<script>
(function(){
  // cheat sheet pages: #cheat-algebra, #cheat-discrete, #cheat-physics
  var subjects = ['algebra','discrete','physics'];
  // shrink a formula a little (never below 80%) when it is slightly too wide for the screen
  function fit(){
    document.querySelectorAll('section.cheat:not([hidden]) .m.d').forEach(function(el){
      var k = el.querySelector('.katex'); if(!k) return;
      k.style.fontSize = '';
      var over = el.scrollWidth / el.clientWidth;
      if(over > 1.01) k.style.fontSize = Math.max(0.8, 0.99 / over) + 'em';
    });
  }
  function route(){
    var h = (location.hash || '').replace('#','');
    var m = /^cheat-(algebra|discrete|physics)$/.exec(h);
    document.querySelectorAll('section.cheat').forEach(function(c){ c.hidden = !m || c.id !== h; });
    if(!m) return;
    subjects.forEach(function(s){
      var sec = document.getElementById('sec-'+s), tab = document.getElementById('tab-'+s);
      if(sec) sec.hidden = true;
      if(tab) tab.setAttribute('aria-selected', s === m[1] ? 'true' : 'false');
    });
    window.scrollTo(0, 0);
    fit();
  }
  window.addEventListener('hashchange', route);
  window.addEventListener('resize', fit);
  if(document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  route();
})();
</script>
'''

have = {s: sheets_dir / f'{s}.html' for s in SUBJECTS}
if all(p.exists() for p in have.values()):
    links = re.findall(r'<p class="sheet-link"><a href="https://claude\.ai/artifact/[^"]+"[^>]*>', src)
    assert len(links) == 3, f'expected 3 cheat sheet links, found {len(links)}'
    # each link sits inside its subject's section, in order algebra, discrete, physics
    for s in SUBJECTS:
        sec_start = src.index(f'id="sec-{s}"')
        link = re.compile(r'<p class="sheet-link"><a href="https://claude\.ai/artifact/[^"]+"[^>]*>')
        m = link.search(src, sec_start)
        src = src[:m.start()] + f'<p class="sheet-link"><a href="#cheat-{s}">' + src[m.end():]
    assert 'claude.ai/artifact' not in src.split('<p class="updated"')[0], 'a cheat sheet link was not rewritten'
    sections = ''.join(sheet_section(s, have[s].read_text()) for s in SUBJECTS)
    k = src.index('<p class="updated"')
    src = src[:k] + sections + '\n' + src[k:]
    src = src.replace('</style>', '</style>\n' + CHEAT_CSS, 1)
    src = src.rstrip() + '\n' + CHEAT_JS
    print('cheat sheets: inside the app')
else:
    print('cheat sheets: not found in', sheets_dir, '- links still open claude.ai')

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
