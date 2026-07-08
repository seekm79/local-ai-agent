"""Browser tool for web testing (Phase 8.8).

Drives headless Chromium via Playwright: navigate, screenshot, click, type, and
read console errors. Screenshots are saved to the project's assets/ (run
artifacts) and shown in the agent board; console errors feed the Reviewer loop.

Playwright + a Chromium build are optional — every entry point degrades to a
clear prerequisite error when they are missing (Global rule 7).
"""
from __future__ import annotations

from pathlib import Path


async def available() -> tuple[bool, str | None]:
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        return False, (
            "Playwright not installed. Run: pip install playwright && "
            "playwright install chromium"
        )
    return True, None


async def run(url: str | None, actions: list[dict], artifacts_dir: Path) -> dict:
    """Run a sequence of browser actions. Each action is a dict:
      {action: 'navigate', url}
      {action: 'click', selector}
      {action: 'type', selector, text}
      {action: 'screenshot', name?}
      {action: 'wait', ms}
    Returns {screenshots: [rel paths], console_errors: [...], steps: [...]}.
    A screenshot is always taken at the end if none was requested.
    """
    ok, err = await available()
    if not ok:
        return {"error": err, "screenshots": [], "console_errors": []}

    from playwright.async_api import async_playwright

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    screenshots: list[str] = []
    steps: list[str] = []

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            page.on(
                "console",
                lambda m: console_errors.append(m.text) if m.type == "error" else None,
            )
            page.on("pageerror", lambda e: console_errors.append(str(e)))

            try:
                if url:
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    steps.append(f"navigated to {url}")

                took_shot = False
                for a in actions:
                    act = a.get("action")
                    if act == "navigate":
                        await page.goto(a["url"], wait_until="domcontentloaded", timeout=15000)
                        steps.append(f"navigated to {a['url']}")
                    elif act == "click":
                        await page.click(a["selector"], timeout=5000)
                        steps.append(f"clicked {a['selector']}")
                    elif act == "type":
                        await page.fill(a["selector"], a.get("text", ""), timeout=5000)
                        steps.append(f"typed into {a['selector']}")
                    elif act == "wait":
                        await page.wait_for_timeout(int(a.get("ms", 500)))
                    elif act == "screenshot":
                        name = a.get("name", f"shot{len(screenshots) + 1}.png")
                        target = artifacts_dir / name
                        await page.screenshot(path=str(target))
                        screenshots.append(target.name)
                        took_shot = True
                        steps.append(f"screenshot {name}")

                if not took_shot:
                    target = artifacts_dir / "screenshot.png"
                    await page.screenshot(path=str(target))
                    screenshots.append(target.name)
                    steps.append("screenshot screenshot.png")
            finally:
                await browser.close()
    except Exception as exc:  # navigation/selector/timeout failures
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "screenshots": screenshots,
            "console_errors": console_errors,
            "steps": steps,
        }

    return {
        "screenshots": screenshots,
        "console_errors": console_errors,
        "steps": steps,
    }
