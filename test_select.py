import requests
import re
import urllib.parse
from bs4 import BeautifulSoup

def get_regulation_year(roll: str) -> int:
    m = re.match(r'^(\d{2})', roll)
    return int(m.group(1)) if m else 22

def get_student_regulation(roll: str) -> str:
    # Most students starting 22 are R22, 20 are R20, 18 are R18, 16 are R16
    year = get_regulation_year(roll)
    if year >= 22: return 'R22'
    if year >= 20: return 'R20'
    if year >= 18: return 'R18'
    return 'R16'

def test_selection(roll):
    r = requests.get('http://results.jntuh.ac.in/jsp/home.jsp', headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    soup = BeautifulSoup(r.text, 'html.parser')
    exams = []
    
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
        reg = reg_match.group(1) if reg_match else None
        if not reg:
            reg_match2 = re.search(r'R\d{2}', text)
            reg = reg_match2.group(0) if reg_match2 else None
            
        year_match = re.search(r'(I|II|III|IV)\s+Year', text)
        sem_match = re.search(r'(I|II)\s+Semester', text)
        
        if year_match and sem_match:
            yr = romans[year_match.group(1)]
            sm = 1 if sem_match.group(1) == 'I' else 2
            sem_index = (yr - 1) * 2 + sm
        else:
            sem_index = None
            
        exam_type = 'Regular' if 'Regular' in text else ('Supplementary' if 'Supplementary' in text else 'Other')
        
        if reg and sem_index:
            exams.append({
                'code': code,
                'etype': etype,
                'reg': reg,
                'sem': sem_index,
                'type': exam_type,
                'title': text
            })
            
    # Now select codes for this student
    reg = get_student_regulation(roll)
    adm_year = get_regulation_year(roll)
    
    # Filter by regulation
    reg_exams = [e for e in exams if e['reg'] == reg]
    
    # Group by semester
    sem_groups = {}
    for e in reg_exams:
        sem_groups.setdefault(e['sem'], []).append(e)
        
    selected_codes = []
    
    # Calculate batch offset: e.g. 2022 batch under R22 is offset 0
    regulation_start_year = int(reg[1:])  # 'R22' -> 22
    batch_offset = adm_year - regulation_start_year
    
    for sem, group in sorted(sem_groups.items()):
        # Sort chronologically by code number
        group.sort(key=lambda x: int(x['code']))
        
        # Find all regular exams in this semester
        reg_exams_in_sem = [e for e in group if e['type'] == 'Regular']
        
        # The regular exam for this student's batch is at index = batch_offset
        if 0 <= batch_offset < len(reg_exams_in_sem):
            batch_reg = reg_exams_in_sem[batch_offset]
            batch_reg_code = int(batch_reg['code'])
            
            # Select this regular exam, plus any supply or subsequent exams with code >= batch_reg_code
            for e in group:
                if int(e['code']) >= batch_reg_code:
                    selected_codes.append(e)
        elif batch_offset >= len(reg_exams_in_sem):
            # The student has not reached this semester yet or no exam published yet
            pass
        else:
            # Fallback: select all if offset is negative (lateral entry or other edge cases)
            selected_codes.extend(group)
            
    print(f"\n=== Selected Codes for Roll: {roll} (Reg: {reg}, Adm: 20{adm_year}) ===")
    for e in sorted(selected_codes, key=lambda x: (x['sem'], int(x['code']))):
        print(f"Sem {e['sem']} | Code: {e['code']} | EType: {e['etype']} | Title: {e['title']}")

test_selection('22U51A05A6')
