
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

print("\nAPPINTEL AI - CONFIGURATION CHECK")
print("-" * 45)

required_keys = {
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
    "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
    "COMPOSIO_API_KEY": os.getenv("COMPOSIO_API_KEY"),
}

all_valid = True

for key, value in required_keys.items():

    if value:
        print(f"[OK] {key} is configured.")
    else:
        print(f"[MISSING] {key} is not configured.")
        all_valid = False

print("-" * 45)

if all_valid:
    print("Configuration check successful.")
else:
    print("Please check your .env file.")

