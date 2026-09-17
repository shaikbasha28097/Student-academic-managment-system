import requests
import re
import urllib.parse
from bs4 import BeautifulSoup

def test_classify():
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
            
    print(f"Total classified: {len(exams)}")
    r22 = [e for e in exams if e['reg'] == 'R22']
    print(f"R22 count: {len(r22)}")
    for e in r22[:30]:
        print(f"Sem {e['sem']} | Type: {e['type']} | Code: {e['code']} | Title: {e['title']}")

test_classify()
