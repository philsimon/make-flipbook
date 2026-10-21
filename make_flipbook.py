#!/usr/bin/env python3
"""make_flipbook.py  Build an animated 3D book for a Ghost HTML card.
 
The book stands on its spine, turns to the cover, opens, and flips pages.
Run it and answer three prompts (drag each PDF into the Terminal window to paste its path):
 
    ~/flipbook-venv/bin/python3 make_flipbook.py
 
Needs: poppler (brew install poppler) and Pillow (pip install pillow, inside a virtual environment).
Output: one self-contained .html file. Paste its whole contents into a Ghost HTML card.
"""
import base64, io, json, os, re, shutil, subprocess, sys, tempfile, webbrowser
 
MAX_PAGES = 10      # never embed more interior pages than this
CREAM = (246, 242, 232)
 
try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is missing. Run these two commands once, then run this script again:\n"
             "  python3 -m venv ~/flipbook-venv\n"
             "  ~/flipbook-venv/bin/pip install pillow\n"
             "Then start the script with:  ~/flipbook-venv/bin/python3 make_flipbook.py")
for tool in ('pdftoppm', 'pdfinfo'):
    if not shutil.which(tool):
        sys.exit("poppler is missing (%s not found). Run:  brew install poppler" % tool)
 
def ask_path(label):
    while True:
        raw = input(label).strip()
        if len(raw) > 1 and raw[0] == raw[-1] and raw[0] in '\'"': raw = raw[1:-1]   # quotes from drag and drop
        raw = re.sub(r'\\(.)', r'\1', raw)                                           # backslash-escaped spaces
        path = os.path.expanduser(raw)
        if os.path.isfile(path) and path.lower().endswith('.pdf'): return path
        print("  I cannot find a PDF at that path. Try again.")
 
def run(*a):
    return subprocess.run(a, check=True, capture_output=True, text=True).stdout
 
def boxes(pdf, page=1):
    info = run('pdfinfo', '-box', '-f', str(page), '-l', str(page), pdf)
    def get(name):
        m = re.search(name + r':\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', info)
        return [float(v) for v in m.groups()] if m else None
    return get('MediaBox'), get('TrimBox')
 
def b64(im, q=84, size=None):
    if size: im = im.resize(size, Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=q, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
 
def groups(xs, gap=3):
    g = []
    for x in xs:
        if g and x - g[-1][-1] <= gap: g[-1].append(x)
        else: g.append([x])
    return [sum(a) / len(a) for a in g]
 
def read_cover(pdf, tmp):
    media, trim = boxes(pdf)
    if not trim: sys.exit("The cover PDF has no trim box, so I cannot find the cover edges.")
    ty0, ty1 = media[3] - trim[3], media[3] - trim[1]          # trim edges, measured from the top
    dpi = 216; s = dpi / 72
    run('pdftoppm', '-r', str(dpi), '-png', '-singlefile', pdf, os.path.join(tmp, 'cover'))
    im = Image.open(os.path.join(tmp, 'cover.png')).convert('RGB'); w, h = im.size
    # Find the fold marks that the printer draws just outside the trim, near the bottom edge.
    ticks = []
    for off in (6, 9, 3):
        y = int((media[3] - off) * s) if off < 10 else 0
        y = min(y, h - 1)
        xs = [x for x in range(w) if sum(im.getpixel((x, y))) < 300]
        ticks = [x / s for x in groups(xs)]
        if len(ticks) >= 4: break
    t = None
    inner = [x for x in ticks if trim[0] + 5 < x < trim[2] - 5]    # ignore the trim-edge marks
    if len(inner) == 6: t = inner[1:5]                          # flaps: hinge, back, spine, front, hinge
    elif len(inner) == 4: t = inner
    if t is None:
        print("\nI could not find the fold marks on the cover.")
        print("I will assume a full wrap with no flaps: back cover, spine, front cover, edge to edge.")
        spine = float(input("Spine width in inches: ").strip()) * 72
        cw = trim[2] - trim[0]; pw = (cw - spine) / 2
        t = [trim[0], trim[0] + pw, trim[0] + pw + spine, trim[2]]
    cut = lambda a, b: im.crop((round(a * s), round(ty0 * s), round(b * s), round(ty1 * s)))
    back, spine, front = cut(t[0], t[1]), cut(t[1], t[2]), cut(t[2], t[3])
    print("  cover: front %.0f x %.0f pt, spine %.0f pt wide" % (t[3] - t[2], ty1 - ty0, t[2] - t[1]))
    if abs(back.size[0] - front.size[0]) > 0.04 * front.size[0]:
        print("  Warning: the back and front panels differ in width. Check the result.")
    return back, spine, front
 
def read_pages(pdf, tmp):
    n = int(re.search(r'Pages:\s+(\d+)', run('pdfinfo', pdf)).group(1))
    use = min(n, MAX_PAGES)
    media, trim = boxes(pdf)
    if not trim: sys.exit("The interior PDF has no trim box, so I cannot crop the pages.")
    x0, x1 = trim[0], trim[2]; y0, y1 = media[3] - trim[3], media[3] - trim[1]
    dpi = 200; s = dpi / 72
    run('pdftoppm', '-r', str(dpi), '-f', '1', '-l', str(use), '-png', pdf, os.path.join(tmp, 'pg'))
    files = sorted(f for f in os.listdir(tmp) if f.startswith('pg') and f.endswith('.png'))
    aspect = (y1 - y0) / (x1 - x0)
    pages = []
    for f in files:
        im = Image.open(os.path.join(tmp, f)).convert('RGB')
        im = im.crop((round(x0 * s), round(y0 * s), round(x1 * s), round(y1 * s))).resize((600, round(600 * aspect)), Image.LANCZOS)
        if im.convert('L').point(lambda v: 255 if v < 200 else 0).getbbox() is None:
            pages.append(None); continue
        r, g, bl = im.split()      # tint the white page to match the cream paper of the 3D leaves
        pages.append(b64(Image.merge('RGB', (r.point(lambda v: v * CREAM[0] // 255), g.point(lambda v: v * CREAM[1] // 255), bl.point(lambda v: v * CREAM[2] // 255))), 80))
    while pages and pages[-1] is None: pages.pop()
    leaves = (len(pages) + 1) // 2
    shown = min(len(pages), 2 * (leaves - 1) + 1)     # the last leaf stays closed, so its back page never shows
    pages = pages[:shown]
    print("  interior: %d pages in the PDF, %d embedded (%d blank), page 1 starts on the right" % (n, shown, sum(p is None for p in pages)))
    if n > MAX_PAGES: print("  I used only the first %d pages." % MAX_PAGES)
    return pages, aspect
 
TEMPLATE = r"""<!-- __TITLE__: 3D book that turns, opens, and flips pages. Paste into a Ghost HTML card. -->
<div class="fb-wrap" id="fb-wrap">
<style>
  .fb-wrap {
    --fb-bg: #faf9f5;
    --fb-ink: rgba(3, 9, 17, 0.92);
    --fb-muted: rgba(5, 5, 5, 0.7);
    --fb-accent: #D97757;
    position: relative;
    max-width: 800px;
    margin: 2rem auto;
    background: var(--fb-bg);
    border-radius: 8px;
    overflow: hidden;
    font-family: Roboto, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  .fb-wrap .fb-box { position: relative; width: 100%; height: 0; }
  .fb-wrap .fb-stage {
    position: absolute; left: 0; top: 0; width: 800px; height: __SH__px;
    transform-origin: 0 0;
    perspective: 2300px; perspective-origin: 50% 46%;
  }
  .fb-wrap .fb-shadow {
    position: absolute; left: 400px; top: __SHADOWTOP__px; width: __SHADOWW__px; height: 44px; margin-left: -__SHADOWHALF__px;
    border-radius: 50%; background: radial-gradient(ellipse at center, rgba(3,9,17,.34), rgba(3,9,17,0) 70%);
  }
  .fb-wrap .fb-cam { position: absolute; left: 400px; top: __CAMTOP__px; width: 0; height: 0; transform-style: preserve-3d; }
  .fb-wrap .fb-book { position: absolute; left: -__WHALF__px; top: -__HHALF__px; width: __W__px; height: __H__px; transform-style: preserve-3d; }
  .fb-wrap .fb-book > div { position: absolute; box-sizing: border-box; }
  .fb-wrap .fb-face { position: absolute; box-sizing: border-box; backface-visibility: hidden; -webkit-backface-visibility: hidden; left: 0; top: 0; width: 100%; height: 100%; }
  .fb-wrap .fb-img { background-size: 100% 100%; background-repeat: no-repeat; }
  .fb-wrap .fb-paper { background: #f6f2e8; box-shadow: inset 0 0 0 1px rgba(60,40,10,.14); }
  .fb-wrap .fb-shade { background: #000; opacity: 0; }
  .fb-wrap .fb-gutter { background: linear-gradient(90deg, rgba(60,40,10,.22), rgba(60,40,10,0) 14%); }
  /* Light and depth cues for the closed book. */
  .fb-wrap .fb-sheen { background: linear-gradient(110deg, rgba(255,255,255,.13) 0%, rgba(255,255,255,0) 38%, rgba(0,0,0,.10) 100%); }
  .fb-wrap .fb-hinge { background: linear-gradient(90deg, rgba(0,0,0,.50) 0, rgba(0,0,0,0) 1.6%, rgba(255,255,255,.16) 2.6%, rgba(255,255,255,0) 5.5%); }
  .fb-wrap .fb-round { background: linear-gradient(90deg, rgba(0,0,0,.42), rgba(255,255,255,.10) 42%, rgba(0,0,0,.34)); }
  .fb-wrap .fb-top {
    background:
      linear-gradient(180deg, #1b110a 0, #1b110a 3px, rgba(0,0,0,0) 3px, rgba(0,0,0,0) calc(100% - 3px), #1b110a calc(100% - 3px)),
      repeating-linear-gradient(180deg, #f6f2e8 0 2px, #e8e1d0 2px 3px);
  }
  .fb-wrap .fb-fore {
    background:
      linear-gradient(90deg, #1b110a 0, #1b110a 3px, rgba(0,0,0,0) 3px, rgba(0,0,0,0) calc(100% - 3px), #1b110a calc(100% - 3px)),
      repeating-linear-gradient(90deg, #f6f2e8 0 2px, #e8e1d0 2px 3px);
  }
  .fb-wrap .fb-replay {
    position: absolute; right: 12px; top: 8px; z-index: 2;
    background: none; border: 0; padding: 4px 6px; cursor: pointer;
    font: 600 14px/1 Roboto, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    color: var(--fb-muted);
  }
  .fb-wrap .fb-replay:hover, .fb-wrap .fb-replay:focus-visible { color: var(--fb-accent); }
</style>
 
<div class="fb-box" id="fb-box" role="img" aria-label="__ALT__">
  <div class="fb-stage" id="fb-stage">
    <div class="fb-shadow" id="fb-shadow"></div>
    <div class="fb-cam" id="fb-cam">
      <div class="fb-book" id="fb-book">
        <!-- back cover: outer face (image) looks away, inner face (paper) looks forward -->
        <div style="left:0;top:0;width:__W__px;height:__H__px;transform:translateZ(-__HD__px);transform-style:preserve-3d">
          <div class="fb-face fb-img" style="transform:rotateY(180deg);background-image:url(__BACKIMG__)"></div>
          <div class="fb-face fb-paper"></div>
        </div>
        <!-- remaining page block -->
        <div style="left:0;top:__LT__px;width:__LW__px;height:__LH__px;transform:translateZ(0.6px);transform-style:preserve-3d">
          <div class="fb-face fb-paper"></div>
          <div class="fb-face fb-gutter"></div>
        </div>
        <!-- spine -->
        <div style="left:-__HD__px;top:0;width:__D__px;height:__H__px;transform:rotateY(-90deg);transform-style:preserve-3d">
          <div class="fb-face fb-img" style="background-image:url(__SPINEIMG__)"></div>
          <div class="fb-face fb-round"></div>
        </div>
        <!-- top and fore-edge of the page block, with the cover boards at each end -->
        <div style="left:0;top:-__HD__px;width:__LW__px;height:__D__px;transform:translateY(__LT__px) rotateX(90deg);backface-visibility:hidden;-webkit-backface-visibility:hidden"><div class="fb-face fb-top"></div></div>
        <div style="left:__FOREX__px;top:__LT__px;width:__D__px;height:__LH__px;transform:rotateY(90deg);backface-visibility:hidden;-webkit-backface-visibility:hidden"><div class="fb-face fb-fore"></div></div>
        <!-- page leaves and the front cover are added by the script -->
      </div>
    </div>
  </div>
</div>
 
<button class="fb-replay" id="fb-replay" type="button" aria-label="Replay the animation">↻ Replay</button>
 
<script>
(function () {
  var wrap = document.getElementById('fb-wrap');
  if (!wrap || wrap.getAttribute('data-fb-ready')) return;
  wrap.setAttribute('data-fb-ready', '1');
 
  var box = wrap.querySelector('#fb-box');
  var stage = wrap.querySelector('#fb-stage');
  var cam = wrap.querySelector('#fb-cam');
  var book = wrap.querySelector('#fb-book');
  var shadow = wrap.querySelector('#fb-shadow');
  var replay = wrap.querySelector('#fb-replay');
 
  var W = __W__, H = __H__, D = __D__, SH = __SH__;
  var LW = __LW__, LH = __LH__, LT = __LT__;
  var NL = __NL__;                  // leaves in the book
  var FLIPS = __FLIPS__;            // leaves that flip; the rest stay on the right
  // Interior pages, one entry per page. null means a blank page.
  var PAGES = __PAGES__;
  var FRONT = '__FRONTIMG__';
  var STEP = Math.min(2.4, (D - 8) / (NL + 0.5));
 
  // Front cover: hinged on the spine edge.
  var cover = document.createElement('div');
  cover.style.cssText = 'position:absolute;left:0;top:0;width:' + W + 'px;height:' + H + 'px;transform-origin:0 50%;transform-style:preserve-3d';
  cover.innerHTML =
    '<div class="fb-face fb-img" style="background-image:url(' + FRONT + ')"></div>' +
    '<div class="fb-face fb-sheen"></div>' +
    '<div class="fb-face fb-hinge"></div>' +
    '<div class="fb-face fb-shade" id="fb-fshade"></div>' +
    '<div class="fb-face fb-paper" style="transform:rotateY(180deg)"></div>' +
    '<div class="fb-face fb-shade" id="fb-cshade" style="transform:rotateY(180deg)"></div>';
  book.appendChild(cover);
  var fshade = cover.querySelector('#fb-fshade');
  var cshade = cover.querySelector('#fb-cshade');
 
  // Leaves show only the pages you supplied. The animation invents no page text.
  var leaves = [];
  for (var i = 0; i < NL; i++) {
    var z = D / 2 - 4 - i * STEP;
    var el = document.createElement('div');
    el.style.cssText = 'position:absolute;left:0;top:' + LT + 'px;width:' + LW + 'px;height:' + LH + 'px;transform-origin:0 50%;transform-style:preserve-3d';
    var pf = PAGES[2 * i], pb = PAGES[2 * i + 1];   // front shows page 2i+1, back shows page 2i+2
    el.innerHTML =
      '<div class="fb-face fb-paper"' + (pf ? ' style="background-image:url(' + pf + ');background-size:100% 100%"' : '') + '></div>' +
      '<div class="fb-face fb-gutter"></div>' +
      '<div class="fb-face fb-shade"></div>' +
      '<div class="fb-face fb-paper" style="transform:rotateY(180deg)' + (pb ? ';background-image:url(' + pb + ');background-size:100% 100%' : '') + '"></div>' +
      '<div class="fb-face fb-shade" style="transform:rotateY(180deg)"></div>';
    book.appendChild(el);
    leaves.push({ el: el, z: z, shades: el.querySelectorAll('.fb-shade') });
  }
 
  function clamp(v) { return Math.max(0, Math.min(1, v)); }
  function easeInOut(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  function easeOut(t) { return 1 - Math.pow(1 - t, 3); }
  function seg(t, a, b) { return clamp((t - a) / (b - a)); }
 
  // Timeline in milliseconds.
  var T_FADE = [0, 500];
  var T_TURN = [1700, 2900];
  var T_OPEN = [3000, 4100];
  var T_FLIP0 = 4200, FLIP_STEP = 900, FLIP_DUR = 800;
  var T_END = T_FLIP0 + Math.max(FLIPS - 1, 0) * FLIP_STEP + FLIP_DUR + 300;
  var SPINE_YAW = 58, FRONT_YAW = -13;   // the front view stays turned a little, so the book keeps its depth
 
  function draw(t) {
    var fade = easeOut(seg(t, T_FADE[0], T_FADE[1]));
    var turn = easeInOut(seg(t, T_TURN[0], T_TURN[1]));
    var open = easeInOut(seg(t, T_OPEN[0], T_OPEN[1]));
 
    // Slow drift while the spine shows.
    var drift = (1 - turn) * Math.sin(t / 800) * 4;
    var base = (SPINE_YAW + drift) * (1 - turn) + FRONT_YAW * turn;
    var yaw = base * (1 - open);
    var pitch = -17 + 2 * open;
    var tx = (W / 2) * open;
    stage.style.opacity = fade;   // Fade the stage, never the 3D container: opacity below 1 flattens 3D children.
    cam.style.transform = 'translateZ(' + (150 * open) + 'px) translateX(' + tx + 'px) rotateX(' + pitch + 'deg) rotateY(' + yaw + 'deg) translateY(' + ((1 - fade) * 10) + 'px)';
 
    // The front face darkens as it turns away from the light.
    fshade.style.opacity = 0.30 * (1 - Math.cos(yaw * Math.PI / 180));
 
    // Front cover swings open and drops to the left.
    cover.style.transform = 'translateZ(' + ((D / 2 + 0.4) * Math.cos(Math.PI * open)) + 'px) rotateY(' + (-180 * open) + 'deg)';
    cshade.style.opacity = 0.3 * Math.sin(Math.PI * open);
 
    for (var i = 0; i < NL; i++) {
      var L = leaves[i];
      var p = i < FLIPS ? easeInOut(seg(t, T_FLIP0 + i * FLIP_STEP, T_FLIP0 + i * FLIP_STEP + FLIP_DUR)) : 0;
      var lift = 10 * Math.sin(Math.PI * p);
      var zz = L.z * Math.cos(Math.PI * p) + lift;
      var sx = 1 - 0.05 * Math.sin(Math.PI * p);
      L.el.style.transform = 'translateZ(' + zz + 'px) rotateY(' + (-179 * p) + 'deg) scaleX(' + sx + ')';
      var sh = 0.16 * Math.sin(Math.PI * p);
      L.shades[0].style.opacity = sh;
      L.shades[1].style.opacity = sh;
    }
 
    // Floor shadow follows the spread.
    var sw = W + 20 + W * open;
    shadow.style.width = sw + 'px';
    shadow.style.marginLeft = (-sw / 2) + 'px';
  }
 
  function fit() {
    var k = wrap.clientWidth / 800;
    stage.style.transform = 'scale(' + k + ')';
    box.style.height = (SH * k) + 'px';
  }
  fit();
  window.addEventListener('resize', fit);
 
  var raf = 0, played = false;
 
  function play() {
    cancelAnimationFrame(raf);
    var start = null;
    function step(ts) {
      if (start === null) start = ts;
      var t = ts - start;
      draw(t);
      if (t < T_END) raf = requestAnimationFrame(step);
    }
    draw(0);
    raf = requestAnimationFrame(step);
  }
 
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) {
    draw(T_TURN[1] + 50); // Reduced motion: show the front cover, no movement.
    replay.style.display = 'none';
    return;
  }
 
  draw(0);
 
  function startOnce() {
    if (played) return;
    played = true;
    play();
  }
 
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { startOnce(); io.disconnect(); }
      });
    }, { threshold: 0.4 });
    io.observe(wrap);
  } else {
    startOnce();
  }
 
  replay.addEventListener('click', function () { played = true; play(); });
})();
</script>
</div>
"""
 
def slug(title):
    s = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return s or 'book'
 
def main():
    print("\nAnimated 3D book builder\n")
    cover_pdf = ask_path("Cover PDF (full wrap, back + spine + front): ")
    pages_pdf = ask_path("Interior PDF (the first pages): ")
    title = input("Book title (for the page description): ").strip() or "Book"
    with tempfile.TemporaryDirectory() as tmp:
        cdir = os.path.join(tmp, 'c'); pdir = os.path.join(tmp, 'p'); os.makedirs(cdir); os.makedirs(pdir)
        print("\nReading the cover...")
        back, spine, front = read_cover(cover_pdf, cdir)
        print("Reading the pages...")
        pages, aspect = read_pages(pages_pdf, pdir)
    prefix = 'bk-' + slug(title)[:14].strip('-')
    prefix = prefix.rstrip('-')
    W = 300
    H = round(W * front.size[1] / front.size[0])
    D = round(W * spine.size[0] / front.size[0], 1)
    NL = (len(pages) + 1) // 2
    flips = max(NL - 1, 0)
    LW = W - 2; LH = round(LW * aspect, 1); LT = round((H - LH) / 2, 1)
    SH = H + 160
    t = TEMPLATE.replace('fb-', prefix + '-')
    alt = 'An animated 3D view of the book %s. The book stands on its spine edge, turns to show the front cover, opens, and flips several pages.' % title
    vals = {
        '__W__': W, '__H__': H, '__D__': D, '__HD__': D / 2, '__WHALF__': W / 2, '__HHALF__': H / 2,
        '__LW__': LW, '__LH__': LH, '__LT__': LT, '__SH__': SH, '__CAMTOP__': SH / 2 - 10,
        '__SHADOWTOP__': H + 80, '__SHADOWW__': W + 20, '__SHADOWHALF__': (W + 20) / 2, '__FOREX__': LW - D / 2,
        '__NL__': NL, '__FLIPS__': flips, '__TITLE__': title, '__ALT__': alt.replace('"', "'"),
    }
    for k, v in vals.items(): t = t.replace(k, str(v))
    bh = round(620 * back.size[1] / back.size[0])
    t = t.replace('__PAGES__', json.dumps(pages))
    t = t.replace('__BACKIMG__', b64(back, 84, (620, bh)))
    t = t.replace('__SPINEIMG__', b64(spine, 84, (max(60, round(spine.size[0] / 2)), bh)))
    t = t.replace('__FRONTIMG__', b64(front, 84, (620, round(620 * front.size[1] / front.size[0]))))
    left = set(re.findall(r'__[A-Z]+__', re.sub(r'data:image/jpeg;base64,[A-Za-z0-9+/=]+', '', t)))
    if left: sys.exit("Build error: unfilled placeholders %s" % sorted(left))
    out = os.path.abspath(slug(title) + '-flip.html')
    open(out, 'w', encoding='utf-8').write(t)
    print("\nDone: %s (%d KB)" % (out, len(t) // 1024))
    print("Book: %d x %d, %.0f thick, %d leaves, %d flips." % (W, H, D, NL, flips))
    print("Paste the whole file into a Ghost HTML card.")
    try: webbrowser.open('file://' + out)
    except Exception: pass
 
main()