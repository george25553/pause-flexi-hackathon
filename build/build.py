"""Inline fonts, models, engine and demo data into one self-contained page: dist/index.html"""
import base64, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parent.parent
F = ROOT / "build" / "fonts"
faces = [("Bricolage Grotesque", 600, "bricolage-grotesque", "latin"), ("Bricolage Grotesque", 700, "bricolage-grotesque", "latin"),
         ("Bricolage Grotesque", 800, "bricolage-grotesque", "latin"), ("IBM Plex Sans", 400, "ibm-plex-sans", "latin"),
         ("IBM Plex Sans", 500, "ibm-plex-sans", "latin"), ("IBM Plex Sans", 600, "ibm-plex-sans", "latin"),
         ("IBM Plex Mono", 400, "ibm-plex-mono", "latin"), ("IBM Plex Mono", 500, "ibm-plex-mono", "latin"),
         ("Noto Sans Georgian", 400, "noto-sans-georgian", "georgian"), ("Noto Sans Georgian", 600, "noto-sans-georgian", "georgian")]
css = []
for fam, w, pkg, sub in faces:
    path = next(F.glob(f"fontsource-{pkg}-*/package/files/{pkg}-{sub}-{w}-normal.woff2"))
    b64 = base64.b64encode(path.read_bytes()).decode()
    css.append(f"@font-face{{font-family:'{fam}';font-weight:{w};font-style:normal;font-display:swap;src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
src = (ROOT / "app" / "src.html").read_text()
models = (ROOT / "app" / "models.json").read_text()
out = (src.replace("/*FONTS*/", "\n".join(css))
          .replace("/*MODELS*/", "window.PAUSE_MODELS=" + models + ";")
          .replace("/*ENGINE*/", (ROOT / "app" / "engine.js").read_text())
          .replace("/*SCENARIOS*/", (ROOT / "app" / "scenarios.js").read_text()))
(ROOT / "dist").mkdir(exist_ok=True)
(ROOT / "dist" / "index.html").write_text(out)
# local preview wrapper (the artifact host adds the doctype/charset skeleton; locally we add it ourselves)
(ROOT / "dist" / "local.html").write_text('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body style="margin:0">' + out + "</body></html>")
print("dist/index.html", round(len(out) / 1024), "KB")
