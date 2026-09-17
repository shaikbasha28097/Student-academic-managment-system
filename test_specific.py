import asyncio
from playwright.async_api import async_playwright

async def test_specific():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        roll = '22U51A05A6'
        dob = '2004-03-30'
        # Let's test a couple of codes
        codes = ['1665', '1674', '1685', '1692', '1700']
        
        for code in codes:
            url = f"http://results.jntuh.ac.in/resultAction?degree=btech&examCode={code}&etype=r&result=null&grad=null&type=intgrade&htno={roll}"
            print(f"\n--- Testing Code {code} ---")
            await page.goto(url, timeout=20000, wait_until='domcontentloaded')
            
            # Print if captcha and fields exist
            has_dp = await page.locator('#datepicker').count() > 0
            has_captcha = await page.locator('#txtCaptcha').count() > 0
            has_htno = await page.locator('#htno').count() > 0
            
            print(f"Elements: datepicker={has_dp}, captcha={has_captcha}, htno={has_htno}")
            
            if has_dp:
                await page.locator('#htno').fill(roll)
                
                await page.evaluate("""(dob) => {
                    const dp = document.getElementById('datepicker');
                    if (dp) {
                        dp.value = dob;
                        dp.setAttribute('name', 'dob');
                    }
                    const form = document.getElementById('myForm');
                    if (form) {
                        let h = document.getElementById('_dob_hidden');
                        if (!h) {
                            h = document.createElement('input');
                            h.type = 'hidden';
                            h.name = 'dob';
                            h.id = '_dob_hidden';
                            form.appendChild(h);
                        }
                        h.value = dob;
                    }
                }""", dob)
                
                captcha_val = await page.evaluate("document.getElementById('txtCaptcha') ? document.getElementById('txtCaptcha').value : ''")
                print(f"Captcha value generated on page: {captcha_val}")
                
                if captcha_val:
                    await page.locator('#txtInput').fill(captcha_val)
                
                # Take screenshot before submit
                await page.screenshot(path=f"before_submit_{code}.png")
                
                # Submit
                await page.evaluate("""() => {
                    const form = document.getElementById('myForm');
                    if (form) {
                        form.onsubmit = null;
                        form.removeAttribute('onsubmit');
                        form.submit();
                    }
                }""")
                
                try:
                    await page.wait_for_load_state('networkidle', timeout=8000)
                except Exception:
                    pass
                
                # Take screenshot after submit
                await page.screenshot(path=f"after_submit_{code}.png")
                
                html = await page.content()
                print(f"Result length: {len(html)}")
                if "invalid hallticket" in html.lower():
                    print("Status: Invalid Hallticket")
                elif "enter date of birth" in html.lower():
                    print("Status: Enter Date of Birth (failed DOB verification)")
                elif "enter correct captcha" in html.lower():
                    print("Status: Enter Correct Captcha (failed Captcha)")
                else:
                    print("Status: Other / Success?")
                    # Let's save a snippet of the table or text if it exists
                    if "grade" in html.lower() or "subject" in html.lower():
                        print("FOUND RESULTS TABLE!")
                        with open(f"result_{code}.html", "w", encoding="utf-8") as f:
                            f.write(html)
            else:
                print("No input form found (already at results page or direct fail)")
                html = await page.content()
                print(f"HTML snippet: {html[:500]}")
                
        await browser.close()

asyncio.run(test_specific())
