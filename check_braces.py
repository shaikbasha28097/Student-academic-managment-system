def check_braces(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    stack = []
    lines = content.split('\n')
    
    in_string = False
    string_char = ''
    in_comment = False
    in_line_comment = False
    
    for i, line in enumerate(lines):
        j = 0
        while j < len(line):
            c = line[j]
            
            if not in_string and not in_comment and not in_line_comment:
                if c == '/' and j + 1 < len(line) and line[j+1] == '/':
                    in_line_comment = True
                    j += 1
                elif c == '/' and j + 1 < len(line) and line[j+1] == '*':
                    in_comment = True
                    j += 1
                elif c in ("'", '"', '`'):
                    in_string = True
                    string_char = c
                elif c == '{':
                    stack.append((i+1, j+1, c))
                elif c == '}':
                    if not stack:
                        print(f"Extra closing brace at line {i+1} col {j+1}")
                        return
                    else:
                        stack.pop()
            elif in_string:
                if c == '\\':
                    j += 1 # skip next char
                elif c == string_char:
                    in_string = False
            elif in_comment:
                if c == '*' and j + 1 < len(line) and line[j+1] == '/':
                    in_comment = False
                    j += 1
                    
            j += 1
        in_line_comment = False

    if stack:
        print(f"Unclosed braces: {stack}")
    else:
        print("Braces matched!")

check_braces('script_1.js')
