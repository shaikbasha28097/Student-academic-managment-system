"""Quick test: verify DOB is now sent in the POST request to JNTUH."""
import asyncio
from playwright.async_api import async_playwright

async def test_dob_submitted():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        url = 'http://results.jntuh.ac.in/resultAction?degree=btech&examCode=1665&etype=r&result=null&grad=null&type=intgrade&htno=22U51A0501'

        submitted = []
        page.on('request', lambda req: submitted.append({'m': req.method, 'd': req.post_data}) if req.method == 'POST' else None)

        await page.goto(url, timeout=20000, wait_until='domcontentloaded')

        dob = '2003-05-15'  # YYYY-MM-DD format (what jQuery datepicker uses)

        # Fill htno
        await page.locator('#htno').fill('22U51A0501')

        # Inject DOB as named field
        await page.evaluate("""(dob) => {
            const dp = document.getElementById('datepicker');
            if (dp) { dp.value = dob; dp.setAttribute('name', 'dob'); }
            const form = document.getElementById('myForm');
            if (form) {
                let h = document.getElementById('_dob_hidden');
                if (!h) { h = document.createElement('input'); h.type='hidden'; h.name='dob'; h.id='_dob_hidden'; form.appendChild(h); }
                h.value = dob;
            }
        }""", dob)

        # Copy captcha
        cap = await page.evaluate("document.getElementById('txtCaptcha').value")
        print(f"Captcha: {cap}")
        await page.locator('#txtInput').fill(cap)

        # Bypass formvalidation and submit
        await page.evaluate("""() => {
            const f = document.getElementById('myForm');
            if (f) { f.onsubmit = null; f.removeAttribute('onsubmit'); f.submit(); }
        }""")

        try:
            await page.wait_for_load_state('networkidle', timeout=12000)
        except Exception:
            pass

        print(f"\nPOST requests intercepted: {len(submitted)}")
        for s in submitted:
            print(f"  POST data: {s['d']}")

        html = await page.content()
        print(f"\nHTML length: {len(html)}")
        print(f"Has 'Enter Date of Birth': {'enter date of birth' in html.lower()}")
        print(f"Has 'invalid hallticket': {'invalid hallticket' in html.lower()}")
        print(f"Has result table: {'subject' in html.lower() or 'grade' in html.lower()}")
        print(f"\nFirst 1500 chars of response:")
        print(html[:1500])

        await browser.close()

asyncio.run(test_dob_submitted())
