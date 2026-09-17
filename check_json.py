import json

try:
    with open('faculty_data.json', 'r', encoding='utf-8') as f:
        data = f.read()
    
    parsed = json.loads(data)
    print("JSON parsed successfully!")
except json.JSONDecodeError as e:
    print(f"JSON Parse Error: {e}")
    # print context around error
    idx = e.pos
    print(data[max(0, idx-50):min(len(data), idx+50)])
