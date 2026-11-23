import json
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "apps.json"


def validate_dataset():

    with open(DATA_FILE, "r", encoding="utf-8") as file:
        apps = json.load(file)

    names = [app["name"] for app in apps]
    categories = [app["category"] for app in apps]

    category_counts = Counter(categories)

    print("\nAPPINTEL AI DATASET VALIDATION")
    print("-" * 40)

    print("Total applications:", len(apps))
    print("Unique applications:", len(set(names)))
    print("Total categories:", len(category_counts))

    print("\nApplications per category:")

    for category, count in category_counts.items():
        print(f"{category}: {count}")

    duplicates = [
        name
        for name, count in Counter(names).items()
        if count > 1
    ]

    if duplicates:
        print("\nDuplicate applications:", duplicates)
    else:
        print("\nNo duplicate applications found.")

    if len(apps) == 100 and len(set(names)) == 100:
        print("\nDataset validation successful.")
    else:
        print("\nDataset validation failed.")


if __name__ == "__main__":
    validate_dataset()