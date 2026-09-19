"""
JNTUH Scraper using Playwright headless browser.
Fixed version: correctly handles the DOB datepicker (no name attr),
adds it as a named field and injects a hidden dob field into the form,
bypasses formvalidation() JS alerts, and runs asyncio safely inside Flask.
"""

import re
import os
import time
import json
import asyncio
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime


# ── Grade / SGPA helpers ───────────────────────────────────────────────────────

GRADE_POINTS = {
    'O': 10.0, 'A+': 9.0, 'A': 8.0,
    'B+': 7.0, 'B': 6.0, 'C': 5.0,
    'F': 0.0, 'AB': 0.0, 'ABSENT': 0.0, 'W': 0.0,
}

def grade_to_points(grade: str) -> float:
    return GRADE_POINTS.get(str(grade).upper().strip(), 0.0)


def get_regulation_year(roll: str) -> int:
    m = re.match(r'^(\d{2})', roll)
    return int(m.group(1)) if m else 22


def get_student_regulation(roll: str) -> str:
    year = get_regulation_year(roll)
    if year >= 25: return 'R25'
    if year >= 22: return 'R22'
    if year >= 20: return 'R20'
    if year >= 18: return 'R18'
    return 'R16'


def get_exam_codes(adm_year: int, roll: str) -> list:
    """
    Dynamically fetch and classify relevant exam codes from the JNTUH results homepage.
    Filters exams by student regulation and selects the regular exam for their batch
    along with subsequent regular/supplementary exam codes.
    """
    import os
    import json
    import time
    import requests
    import urllib.parse
    from bs4 import BeautifulSoup

    reg = get_student_regulation(roll)
    cache_file = 'jntuh_exam_codes.json'
    exams = []
    use_cache = False

    # Check cache first (valid for 6 hours to prevent hitting JNTUH constantly)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            if time.time() - cached_data.get('timestamp', 0) < 21600:
                exams = cached_data.get('exams', [])
                use_cache = True
        except Exception:
            pass

    if not use_cache or not exams:
        try:
            r = requests.get('http://results.jntuh.ac.in/jsp/home.jsp',
                             headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                             timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                romans = {'I': 1, 'II': 2, 'III': 3, 'IV': 4}

                for l in soup.find_all('a'):
                    href = l.get('href', '')
                    text = l.get_text(strip=True)
                    if 'examCode' not in href or 'RC/RV' in text or 'Minor' in text or 'Double' in text:
                        continue
                    if not ('B.Tech' in text or 'b.tech' in text or 'B.TECH' in text):
                        continue

                    parsed = urllib.parse.urlparse(href)
                    qs = urllib.parse.parse_qs(parsed.query)
                    code = qs.get('examCode', [''])[0]
                    etype = qs.get('etype', [''])[0]

                    reg_match = re.search(r'\((R\d{2})\)', text)
                    cur_reg = reg_match.group(1) if reg_match else None
                    if not cur_reg:
                        reg_match2 = re.search(r'R\d{2}', text)
                        cur_reg = reg_match2.group(0) if reg_match2 else None

                    year_match = re.search(r'(I|II|III|IV)\s+Year', text)
                    sem_match = re.search(r'(I|II)\s+Semester', text)

                    if year_match and sem_match:
                        yr = romans[year_match.group(1)]
                        sm = 1 if sem_match.group(1) == 'I' else 2
                        sem_index = (yr - 1) * 2 + sm
                    else:
                        sem_index = None

                    exam_type = 'Regular' if 'Regular' in text else ('Supplementary' if 'Supplementary' in text else 'Other')

                    if cur_reg and sem_index:
                        exams.append({
                            'code': code,
                            'etype': etype,
                            'reg': cur_reg,
                            'sem': sem_index,
                            'type': exam_type,
                            'title': text
                        })
                
                # Save to cache
                if exams:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump({'timestamp': time.time(), 'exams': exams}, f)
        except Exception:
            pass

    # Fallback minimal list if JNTUH is offline/timed out
    if not exams:
        return [
            {'code': '1662', 'sem': 1, 'etype': 'r17', 'reg': 'R22'},
            {'code': '1704', 'sem': 2, 'etype': 'r17', 'reg': 'R22'},
            {'code': '1771', 'sem': 3, 'etype': 'r17', 'reg': 'R22'},
            {'code': '1813', 'sem': 4, 'etype': 'r17', 'reg': 'R22'},
            {'code': '1841', 'sem': 5, 'etype': 'r17', 'reg': 'R22'},
            {'code': '1921', 'sem': 6, 'etype': 'r17', 'reg': 'R22'},
            {'code': '1948', 'sem': 7, 'etype': 'r17', 'reg': 'R22'},
            {'code': '1961', 'sem': 8, 'etype': 'r17', 'reg': 'R22'},
        ]

    # Filter by regulation
    reg_exams = [e for e in exams if e['reg'] == reg]

    # Sort chronologically by code number to query correctly
    reg_exams.sort(key=lambda x: int(x['code']))

    return reg_exams


# ── HTML parser ───────────────────────────────────────────────────────────────

def parse_result_html(html: str, meta: dict) -> dict | None:
    """Parse the result page HTML and extract subject data."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')

    # Extract the official name from the explicitly labeled JNTUH field.
    name = ''
    roll_pattern = re.compile(r'^\d{2}[A-Z0-9]{6,}$', re.IGNORECASE)
    for td in soup.select('table td'):
        label = re.sub(r'[^a-z]', '', td.get_text(' ', strip=True).lower())
        if label not in {'name', 'studentname'}:
            continue
        value_cell = td.find_next_sibling('td')
        candidate = value_cell.get_text(' ', strip=True) if value_cell else ''
        if candidate and not roll_pattern.fullmatch(candidate.replace(' ', '')):
            name = candidate
            break

    subjects = []
    sgpa_val = 0.0

    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
        headers = [th.get_text(' ', strip=True).lower() for th in rows[0].find_all(['th', 'td'])]
        if not any(w in h for h in headers for w in ['grade', 'subject', 'credits']):
            continue

        idx = {'code': -1, 'name': -1, 'total': -1, 'grade': -1, 'credits': -1, 'result': -1, 'int': -1, 'ext': -1}
        for i, h in enumerate(headers):
            header_key = re.sub(r'[^a-z]', '', h)
            if header_key in {'subjectcode', 'subcode', 'coursecode', 'code'}: idx['code'] = i
            if header_key in {'subjectname', 'subname', 'coursename', 'subject'}: idx['name'] = i
            if header_key in {'total', 'totalmarks', 'marks', 'mark'}: idx['total'] = i
            if 'grade' in header_key and 'point' not in header_key: idx['grade'] = i
            if 'credit' in header_key: idx['credits'] = i
            if header_key in {'result', 'status', 'passfail'}: idx['result'] = i
            if 'internal' in header_key or header_key.startswith('int'): idx['int'] = i
            if 'external' in header_key or header_key.startswith('ext'): idx['ext'] = i

        if idx['name'] == -1 and idx['grade'] == -1:
            continue

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all('td')]
            if not cells or len(cells) < 2:
                continue
            row_txt = ' '.join(cells).lower()
            if 'sgpa' in row_txt or 'cgpa' in row_txt:
                for c in cells:
                    try:
                        v = float(c)
                        if 0 < v <= 10:
                            sgpa_val = v
                            break
                    except ValueError:
                        pass
                continue

            def get(k): return cells[idx[k]] if idx[k] >= 0 and idx[k] < len(cells) else ''
            sub_name = get('name')
            subject_code = get('code').strip().upper()
            total_marks = get('total').strip()
            grade = get('grade')
            credits_str = get('credits')
            result_status = get('result').strip().upper()

            if not sub_name or sub_name.lower() == 'subject name':
                continue
            if sub_name.isdigit() and len(sub_name) <= 2:
                continue

            valid_grades = {'O', 'A+', 'A', 'B+', 'B', 'C', 'F', 'AB', 'ABSENT', 'W', '--'}
            if grade.upper() not in valid_grades:
                for c in cells:
                    if c.strip().upper() in valid_grades:
                        grade = c.strip()
                        break

            try:
                cred_num = float(credits_str)
            except ValueError:
                cred_num = 0.0

            if not result_status:
                result_status = 'PASS' if grade.upper().strip() not in ('F', 'AB', 'ABSENT', 'W', '--', '') else 'FAIL'

            subjects.append({
                'code': subject_code,
                'name': sub_name,
                'marks': total_marks,
                'total': total_marks,
                'grade': grade or '-',
                'credits': cred_num,
                'result': result_status,
                'points': grade_to_points(grade),
                'internal': get('int'),
                'external': get('ext'),
                'passed': grade.upper().strip() not in ('F', 'AB', '') and bool(grade),
            })

    if not subjects:
        return None

    total_cred = sum(s['credits'] for s in subjects if s['credits'] > 0)
    total_pts = sum(s['credits'] * s['points'] for s in subjects if s['credits'] > 0)
    sgpa = round(total_pts / total_cred, 2) if total_cred > 0 else 0.0
    if sgpa_val > 0:
        sgpa = sgpa_val

    return {
        'semester': int(meta['sem']),
        'type': meta.get('type') or ('Regular' if meta['etype'] == 'r' else 'Supplementary'),
        'examCode': meta['code'],
        'regulation': meta['reg'],
        'subjects': subjects,
        'sgpa': sgpa,
        'credits': total_cred,
        'studentName': name,
    }


# ── Core Playwright fetch (one exam code) ─────────────────────────────────────

def _run_async(coro):
    """
    Run an async coroutine safely regardless of whether there is already
    a running event loop (e.g. Flask debug / Werkzeug reloader context).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside a running event loop (Flask debug mode).
        # Run in a separate thread that has its own fresh event loop.
        result = [None]
        error = [None]

        def _run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                result[0] = new_loop.run_until_complete(coro)
            except Exception as e:
                error[0] = e
            finally:
                new_loop.close()

        t = threading.Thread(target=_run_in_thread)
        t.start()
        t.join()

        if error[0]:
            raise error[0]
        return result[0]
    else:
        return asyncio.run(coro)


def _normalize_dob(dob: str) -> str:
    """
    Convert any DOB format to YYYY-MM-DD (what the jQuery datepicker uses internally).
    Accepts: YYYY/MM/DD, YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY
    """
    dob = dob.strip()
    # Already YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', dob):
        return dob
    # YYYY/MM/DD → YYYY-MM-DD
    if re.match(r'^\d{4}/\d{2}/\d{2}$', dob):
        return dob.replace('/', '-')
    # DD/MM/YYYY → YYYY-MM-DD
    m = re.match(r'^(\d{2})[/-](\d{2})[/-](\d{4})$', dob)
    if m:
        return f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
    return dob.replace('/', '-')


async def _fetch_one_playwright(roll: str, entry: dict, dob_normalized: str, context) -> dict | None:
    """
    Fetch one semester result using Playwright.
    Key fix: the #datepicker has no 'name' attribute, so we inject a hidden
    'dob' field into the form before submission. The captcha is text-only
    (alphanumeric), we just copy txtCaptcha.value → txtInput.
    """
    url = (
        f"http://results.jntuh.ac.in/resultAction"
        f"?degree=btech&examCode={entry['code']}"
        f"&etype={entry['etype']}&result=null&grad=null&type=intgrade&htno={roll}"
    )
    page = await context.new_page()
    try:
        await page.goto(url, timeout=20000, wait_until='domcontentloaded')

        # Check if DOB form is present
        if await page.locator('#datepicker').count() == 0:
            # No form – already a result page
            html = await page.content()
            if len(html) < 500 or 'invalid hallticket' in html.lower():
                return None
            return parse_result_html(html, entry)

        # ── Fill Hall Ticket Number ───────────────────────────────────────
        htno_el = page.locator('#htno')
        if await htno_el.count() > 0:
            await htno_el.fill(roll)

        # ── Set DOB: inject as hidden field + set datepicker value ───────
        # The datepicker has no 'name', so the server never receives it via
        # normal form serialisation. We add a hidden <input name="dob"> and
        # also set the datepicker value so formvalidation() doesn't fail.
        await page.evaluate("""(dob) => {
            // Set visible datepicker field value
            const dp = document.getElementById('datepicker');
            if (dp) {
                dp.value = dob;
                dp.setAttribute('name', 'dob');   // give it a name so it posts
            }
            // Also inject a hidden dob field in case the server needs it
            const form = document.getElementById('myForm');
            if (form) {
                let hidden = document.getElementById('_dob_hidden');
                if (!hidden) {
                    hidden = document.createElement('input');
                    hidden.type = 'hidden';
                    hidden.name = 'dob';
                    hidden.id = '_dob_hidden';
                    form.appendChild(hidden);
                }
                hidden.value = dob;
            }
        }""", dob_normalized)

        # ── Handle captcha (text-based: copy txtCaptcha → txtInput) ──────
        captcha_val = await page.evaluate(
            "document.getElementById('txtCaptcha') ? document.getElementById('txtCaptcha').value : ''"
        )
        if captcha_val and await page.locator('#txtInput').count() > 0:
            await page.locator('#txtInput').fill(captcha_val)

        # ── Submit the form by bypassing formvalidation (direct POST) ─────
        # We submit directly to avoid any JS alert() popup blocking us.
        await page.evaluate("""() => {
            const form = document.getElementById('myForm');
            if (form) {
                // Bypass the onsubmit handler
                form.onsubmit = null;
                form.removeAttribute('onsubmit');
                form.submit();
            }
        }""")

        try:
            await page.wait_for_load_state('networkidle', timeout=12000)
        except Exception:
            pass

        html = await page.content()

        # Reject only the lookup form or an explicit validation error. Result
        # pages also contain a form, so checking for any <form> is too broad.
        if (len(html) < 500
                or 'enter date of birth' in html.lower()
                or 'invalid hallticket' in html.lower()
            or 'enter captcha' in html.lower()
            or 'incorrect captcha' in html.lower()):
            return None

        return parse_result_html(html, entry)

    except Exception:
        return None
    finally:
        await page.close()


# ── Parallel fetch all exam codes ─────────────────────────────────────────────

async def _fetch_all_playwright(roll: str, dob_normalized: str, exam_codes: list) -> list:
    """Launch a browser and fetch all exam codes in small parallel batches."""
    from playwright.async_api import async_playwright
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        # Batches of 5 to avoid server overload
        batch_size = 5
        for i in range(0, len(exam_codes), batch_size):
            batch = exam_codes[i:i + batch_size]
            tasks = [_fetch_one_playwright(roll, entry, dob_normalized, context) for entry in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in batch_results:
                if r and not isinstance(r, Exception):
                    results.append(r)
        await browser.close()
    return results


# ── CGPA computation ──────────────────────────────────────────────────────────

def _compute_cgpa(sem_results: list) -> dict:
    """
    Computes:
    - totalCredits: sum of credits for ALL unique subjects passed across Regular and Supplementary exams.
    - backlogsCount: total count of unique subjects attempted that have NOT been passed in any exam.
    - cgpa: weighted CGPA calculated using the best passed/latest attempt for each subject per semester.
    """
    subject_best_map = {}

    for r in sem_results:
        sem = r.get('semester')
        for sub in r.get('subjects', []):
            code = (sub.get('code') or '').strip().upper()
            name = (sub.get('name') or '').strip().upper()
            key = code if code else name
            if not key:
                continue

            composite_key = (sem, key)
            if composite_key not in subject_best_map:
                subject_best_map[composite_key] = sub
            else:
                prev = subject_best_map[composite_key]
                # Prefer passed attempt over failed attempt
                if sub.get('passed') and not prev.get('passed'):
                    subject_best_map[composite_key] = sub
                elif sub.get('passed') == prev.get('passed'):
                    # If both passed or both failed, pick attempt with higher points
                    if sub.get('points', 0) > prev.get('points', 0):
                        subject_best_map[composite_key] = sub

    passed_subjects = [s for s in subject_best_map.values() if s.get('passed')]
    failed_subjects = [s for s in subject_best_map.values() if not s.get('passed')]

    total_credits = sum(s.get('credits', 0.0) for s in passed_subjects if s.get('credits', 0.0) > 0)
    backlogs_count = len(failed_subjects)

    total_pts = sum(s.get('credits', 0.0) * s.get('points', 0.0) for s in passed_subjects if s.get('credits', 0.0) > 0)
    total_cred_cgpa = sum(s.get('credits', 0.0) for s in passed_subjects if s.get('credits', 0.0) > 0)

    cgpa = round(total_pts / total_cred_cgpa, 2) if total_cred_cgpa > 0 else 0.0

    return {
        'cgpa': cgpa,
        'totalCredits': total_credits,
        'backlogsCount': backlogs_count,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_jntuh_results(roll: str, dob: str | None = None) -> dict:
    """
    Main entry point. Fetches JNTUH results for the given roll number.
    dob accepts: YYYY/MM/DD, YYYY-MM-DD, DD/MM/YYYY
    """
    roll = roll.strip().upper()
    adm_year = get_regulation_year(roll)
    exam_codes = get_exam_codes(adm_year, roll)

    if not dob:
        return {
            'success': False,
            'error': 'Date of Birth is required. Please enter your DOB in YYYY/MM/DD format (e.g. 2004/07/15).',
            'need_dob': True,
        }

    dob_normalized = _normalize_dob(dob)

    try:
        results = _run_async(_fetch_all_playwright(roll, dob_normalized, exam_codes))
    except Exception as e:
        return {
            'success': False,
            'error': f'Scraper failed: {str(e)}',
        }

    if not results:
        return {
            'success': False,
            'error': (
                f'No results found for <strong>{roll}</strong> with DOB <strong>{dob}</strong>.<br>'
                'Please verify:<br>'
                '• Roll Number is correct (e.g. 22U51A0501)<br>'
                '• Date of Birth format is YYYY/MM/DD (e.g. 2004/03/30)<br>'
                '• Results are published on JNTUH website'
            ),
            'need_dob': False,
        }

    results.sort(key=lambda x: (x['semester'], 0 if x['type'] == 'Regular' else 1))

    student_name = next(
        (r['studentName'] for r in results if r.get('studentName')), f'Student ({roll})'
    )
    for r in results:
        r.pop('studentName', None)

    cgpa_data = _compute_cgpa(results)

    return {
        'success': True,
        'cached': False,
        'roll': roll,
        'name': student_name,
        'results': results,
        'cgpa': cgpa_data['cgpa'],
        'totalCredits': cgpa_data['totalCredits'],
        'backlogsCount': cgpa_data['backlogsCount'],
        'semCount': len(results),
    }
