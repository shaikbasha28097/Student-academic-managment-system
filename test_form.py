import asyncio
from playwright.async_api import async_playwright

async def test_full_flow():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        url = 'http://results.jntuh.ac.in/resultAction?degree=btech&examCode=1665&etype=r&result=null&grad=null&type=intgrade&htno=22U51A0501'
        
        # Intercept POST request to see what's being sent
        submitted_data = []
        async def on_request(req):
            if req.method == 'POST':
                submitted_data.append({'url': req.url, 'post_data': req.post_data})
        page.on('request', on_request)
        
        await page.goto(url, timeout=20000, wait_until='domcontentloaded')
        
        # Fill htno
        await page.locator('#htno').fill('22U51A0501')
        
        # Set datepicker via jQuery if available, else directly
        dob = '2003/05/15'
        await page.evaluate("""(dob) => {
            const dp = document.getElementById('datepicker');
            dp.value = dob;
            // Try triggering jQuery datepicker setDate
            try { jQuery('#datepicker').datepicker('setDate', dob); } catch(e) {}
            dp.dispatchEvent(new Event('change', {bubbles: true}));
            dp.dispatchEvent(new Event('input', {bubbles: true}));
        }""", dob)
        
        # Get captcha value (it's already set as a text field value)
        captcha_val = await page.evaluate("document.getElementById('txtCaptcha').value")
        print(f'Captcha value: {captcha_val}')
        await page.locator('#txtInput').fill(captcha_val)
        
        # Check ALL form inputs before submit
        all_vals = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input, select')).map(i => ({
                id: i.id, name: i.name, type: i.type, value: i.value
            }));
        }""")
        print('All inputs before submit:')
        for v in all_vals:
            print(f"  id={v['id']} name={v['name']} type={v['type']} value={v['value']}")
        
        # Check formvalidation function
        form_val = await page.evaluate("""() => {
            return typeof formvalidation === 'function' ? formvalidation.toString() : 'NOT FOUND';
        }""")
        print(f'\nformvalidation: {form_val[:500]}')
        
        # Submit by clicking Submit button
        await page.locator('input[type=submit]').click()
        try:
            await page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        
        print(f'\nSubmitted POST requests:')
        for req in submitted_data:
            print(f"  URL: {req['url']}")
            print(f"  Data: {req['post_data']}")
        
        content = await page.content()
        print(f'\nResponse HTML length: {len(content)}')
        print(f'Contains invalid hallticket: {"invalid hallticket" in content.lower()}')
        print(f'Contains student name: {"student name" in content.lower()}')
        print(f'Contains Enter Date of Birth: {"enter date of birth" in content.lower()}')
        print('\nFirst 3000 chars:')
        print(content[:3000])
        
        await browser.close()

asyncio.run(test_full_flow())
