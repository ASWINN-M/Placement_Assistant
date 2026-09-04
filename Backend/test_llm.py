from llm_extractor import extract_placement_info


subject = """
Exxonmobil Online test is scheduled on 05-09-2026 by 09:30 am @ PRP - 713
"""

body = """
Attached is the list of 763 students who have successfully cleared our OBA
test and will now progress for the Aptitude+Technical test on 5th September
2026, 10am onwards.

Vellore campus students must report to PRP - 713.

Late entry may not be permitted, so candidates must be seated before
the scheduled start time.
"""


result = extract_placement_info(
    subject,
    body
)

print("\nExtracted Placement Information:")
print("--------------------------------")

for key, value in result.items():
    print(f"{key}: {value}")