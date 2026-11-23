import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


models_to_test = [
    "gemini-3.5-flash-lite"
]


for model in models_to_test:
    print(f"\nTesting: {model}")

    try:
        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly: Gemini connection successful"
        )

        print("SUCCESS")
        print(response.text)

    except Exception as error:
        print("FAILED")
        print(error)