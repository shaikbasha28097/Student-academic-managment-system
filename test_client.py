import app as flask_app

client = flask_app.app.test_client()

# Mock the session to bypass login
with client.session_transaction() as sess:
    sess['role'] = 'faculty'
    sess['user_id'] = 'FAC123'  # Assuming a fake or real ID

response = client.get('/faculty_dashboard')
html = response.data.decode('utf-8')

with open('rendered_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("Saved to rendered_dashboard.html")
