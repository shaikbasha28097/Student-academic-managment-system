import asyncio
import os
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Listen for console messages
        page.on("console", lambda msg: print(f"CONSOLE [{msg.type}]: {msg.text}"))
        # Listen for page errors (uncaught exceptions)
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        
        file_path = f"file:///{os.path.abspath('rendered_dashboard.html').replace(chr(92), '/')}"
        print(f"Navigating to {file_path}...")
        
        await page.goto(file_path)
        
        # Wait a bit for scripts to run
        await page.wait_for_timeout(2000)
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
