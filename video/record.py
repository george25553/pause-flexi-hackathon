"""Drive the prototype in headless Chromium, capture it with the DevTools screencast (uncut screen capture),
fire UI actions in sync with each narration line, and log timings for muxing."""
import asyncio, base64, json, pathlib, sys, time
from playwright.async_api import async_playwright
HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from script import BEATS
FR = HERE / "frames"; FR.mkdir(exist_ok=True)
for f in FR.glob("*.jpg"): f.unlink()
DURS = json.load(open(HERE / "audio" / "durations.json"))
GAP = 0.55

async def main():
    frames = []
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--disable-gpu"])
        ctx = await b.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=1.2)
        pg = await ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto((HERE.parent / "dist" / "local.html").as_uri())
        await pg.wait_for_timeout(1500)
        cdp = await ctx.new_cdp_session(pg)
        def on_frame(ev):
            ts = ev["metadata"]["timestamp"]; n = len(frames)
            path = FR / f"f{n:05d}.jpg"; path.write_bytes(base64.b64decode(ev["data"]))
            frames.append((ts, path.name))
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}))
        cdp.on("Page.screencastFrame", on_frame)
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})
        await pg.wait_for_timeout(600)
        # nudge a repaint so we get an initial frame
        await pg.evaluate("document.body.style.outline='0px solid transparent'")
        await pg.wait_for_timeout(500)
        starts = []

        async def run_actions(acts):
            for a in acts:
                if a.startswith("sleep:"): await asyncio.sleep(int(a[6:]) / 1000)
                elif a.startswith("click:"): await pg.click(a[6:])
                else: await pg.evaluate(a)

        for i, beat in enumerate(BEATS):
            t = time.time(); starts.append(t)
            if beat.get("chapter"):
                await pg.evaluate("([a,b]) => demo.caption(a,b)", list(beat["chapter"]))
                asyncio.get_event_loop().call_later(3.0, lambda: asyncio.ensure_future(pg.evaluate("demo.caption(null)")))
            task = asyncio.ensure_future(run_actions(beat["do"]))
            await asyncio.sleep(DURS[i] + GAP)
            await task
        await pg.wait_for_timeout(1800)
        end = time.time()
        await cdp.send("Page.stopScreencast")
        await b.close()
    json.dump({"frames": frames, "starts": starts, "end": end, "errors": errs}, open(HERE / "timeline.json", "w"))
    print("frames", len(frames), "duration", round(end - frames[0][0], 1), "errors", errs)

asyncio.run(main())
