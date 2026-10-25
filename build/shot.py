import sys, asyncio, pathlib
from playwright.async_api import async_playwright
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = pathlib.Path(sys.argv[1]); steps = int(sys.argv[2]) if len(sys.argv) > 2 else 0
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        await pg.goto((ROOT / "dist" / "local.html").as_uri())
        for i in range(steps):
            await pg.evaluate("window.demo.step()"); await pg.wait_for_timeout(600)
        await pg.screenshot(path=str(OUT))
        print("errors:", errs)
        await b.close()
asyncio.run(main())
