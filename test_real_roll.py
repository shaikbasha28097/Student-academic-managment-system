"""Test with the user's actual DOB to verify the fix works."""
import asyncio
from playwright.async_api import async_playwright

async def test_with_real_dob(roll, dob):
    """Test fetching results for a specific roll and DOB."""
    from jntuh_scraper import fetch_jntuh_results
    print(f"Testing: roll={roll}, dob={dob}")
    result = fetch_jntuh_results(roll, dob)
    print(f"Success: {result.get('success')}")
    print(f"Error: {result.get('error')}")
    print(f"Name: {result.get('name')}")
    print(f"CGPA: {result.get('cgpa')}")
    print(f"Semesters found: {result.get('semCount')}")
    if result.get('results'):
        for sem in result['results']:
            print(f"  Sem {sem['semester']} ({sem['type']}): SGPA={sem['sgpa']}, Subjects={len(sem['subjects'])}")

# Test the specific roll number with the DOB entered by user
# Replace these with your actual roll number and DOB
import sys
roll = sys.argv[1] if len(sys.argv) > 1 else "22U51A0501"
dob  = sys.argv[2] if len(sys.argv) > 2 else "2004/03/30"

asyncio.run(test_with_real_dob(roll, dob))
