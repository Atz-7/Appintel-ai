
import os
import json
import csv
import time

from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any

from dotenv import load_dotenv
from tavily import TavilyClient
from google import genai
from google.genai import types, errors

from src.research.schema import AppResearch


# ============================================================
# 1. PROJECT PATHS AND CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_FILE = PROJECT_ROOT / "data" / "apps.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MASTER_JSON = OUTPUT_DIR / "appintel_master.json"
MASTER_CSV = OUTPUT_DIR / "appintel_master.csv"
FAILURE_LOG = OUTPUT_DIR / "failed_apps.json"

load_dotenv(PROJECT_ROOT / ".env")


# ============================================================
# 2. API CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

PRIMARY_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash"
)

MODEL_FALLBACKS = [
    PRIMARY_MODEL,
]

MAX_RETRIES = 3

# Tavily settings
MAX_SOURCES_PER_APP = 12
MAX_CONTENT_LENGTH = 2000

# Batch settings
MAX_APPS_PER_RUN = 1

# False = skip previously completed applications.
# True = research every application again.
FORCE_RERUN = False

# Only temporary errors are retried.
# 429 is deliberately excluded because it can indicate quota exhaustion.
RETRYABLE_STATUS_CODES = {
    408,
    500,
    502,
    503,
    504
}


class GeminiQuotaExhausted(Exception):
    """Raised when Gemini API quota is exhausted."""
    pass


# ============================================================
# 3. INITIALIZE CLIENTS
# ============================================================

def initialize_clients():

    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is missing from .env"
        )

    if not TAVILY_API_KEY:
        raise ValueError(
            "TAVILY_API_KEY is missing from .env"
        )

    gemini_client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    tavily_client = TavilyClient(
        api_key=TAVILY_API_KEY
    )

    print("Gemini client initialized.")
    print("Tavily client initialized.")
    print("Primary Gemini model:", PRIMARY_MODEL)

    return gemini_client, tavily_client


# ============================================================
# 4. LOAD APPLICATION DATASET
# ============================================================

def load_apps() -> List[Dict[str, Any]]:

    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATA_FILE}"
        )

    with open(
        DATA_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        apps = json.load(file)

    if not isinstance(apps, list):
        raise ValueError(
            "apps.json must contain a JSON list."
        )

    required_fields = {"name", "category"}
    seen_names = set()

    for index, app in enumerate(apps):

        if not isinstance(app, dict):
            raise ValueError(
                f"Invalid application entry at index {index}."
            )

        missing = required_fields - set(app.keys())

        if missing:
            raise ValueError(
                f"Application at index {index} is missing: {missing}"
            )

        if not isinstance(app["name"], str) or not app["name"].strip():
            raise ValueError(
                f"Invalid application name at index {index}."
            )

        if not isinstance(app["category"], str) or not app["category"].strip():
            raise ValueError(
                f"Invalid category for {app['name']}."
            )

        normalized_name = app["name"].strip().lower()

        if normalized_name in seen_names:
            raise ValueError(
                f"Duplicate application: {app['name']}"
            )

        seen_names.add(normalized_name)

    print(f"Applications loaded: {len(apps)}")

    return apps


# ============================================================
# 5. FILE NAMING AND SAFE JSON WRITING
# ============================================================

def get_report_path(app_name: str) -> Path:

    safe_name = "".join(
        character.lower()
        if character.isalnum()
        else "_"
        for character in app_name
    ).strip("_")

    return OUTPUT_DIR / f"{safe_name}_research.json"


def write_json_atomic(
    output_file: Path,
    data: Any
):

    temporary_file = output_file.with_name(
        output_file.name + ".tmp"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )

    os.replace(
        temporary_file,
        output_file
    )


# ============================================================
# 6. TAVILY DOCUMENTATION SEARCH
# ============================================================

def search_app_documentation(
    tavily_client: TavilyClient,
    app_name: str
) -> List[Dict[str, str]]:

    print(
        f"\nSearching documentation for {app_name}..."
    )

    queries = [
        f"{app_name} official developer API documentation",
        f"{app_name} API authentication OAuth API key",
        f"{app_name} official REST GraphQL API documentation",
        f"{app_name} official MCP server documentation",
    ]

    collected_sources = []
    seen_urls = set()

    for query in queries:

        try:

            results = tavily_client.search(
                query=query,
                search_depth="advanced",
                max_results=4,
                include_raw_content=True,
            )

            for result in results.get("results", []):

                url = result.get("url")

                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)

                content = (
                    result.get("raw_content")
                    or result.get("content")
                    or ""
                )

                collected_sources.append({
                    "title": result.get("title", ""),
                    "url": url,
                    "content": content[:MAX_CONTENT_LENGTH],
                })

        except Exception as error:

            print(
                f"Search warning for query '{query}': {error}"
            )

    collected_sources = collected_sources[
        :MAX_SOURCES_PER_APP
    ]

    print(
        f"Unique sources discovered: {len(collected_sources)}"
    )

    return collected_sources


# ============================================================
# 7. BUILD RESEARCH PROMPT
# ============================================================

def create_research_prompt(
    app: Dict[str, Any],
    sources: List[Dict[str, str]]
) -> str:

    source_sections = []

    for index, source in enumerate(
        sources,
        start=1
    ):

        source_sections.append(
            f"""
SOURCE {index}

Title: {source['title']}

URL: {source['url']}

Content:
{source['content']}
"""
        )

    source_text = "\n".join(source_sections)

    return f"""
You are AppIntel AI, an application integration research agent.

Your task is to investigate a software application and determine
how practical it would be to build a reliable integration for it.

APPLICATION:
{app['name']}

CATEGORY:
{app['category']}


RESEARCH REQUIREMENTS
=====================

1. DESCRIPTION

Explain what the application does and its primary use cases.


2. AUTHENTICATION METHODS

Identify documented API authentication methods.

Examples:
- OAuth 2.0
- API keys
- Bearer tokens
- Personal access tokens
- Other documented authentication methods

Do not assume that a method exists without evidence.


3. ACCESS MODEL

Classify API access as accurately as possible:

- Public self-serve
- Self-serve with account requirements
- Approval-based
- Partner-only
- Enterprise-only
- Restricted or unavailable

Explain relevant conditions, subscriptions or approvals.


4. API TYPE

Identify documented API types:

- REST
- GraphQL
- SOAP
- Webhooks
- Other API types


5. API BREADTH

Describe:

- Main API resources
- Important endpoints
- Available operations
- API coverage
- Major limitations


6. EXISTING MCP

Investigate whether an MCP server exists.

Distinguish between:

- Official MCP server
- Third-party MCP server
- Community implementation
- No reliable evidence found

Never classify a third-party implementation as official.


7. BUILDABILITY

Assess integration feasibility based on:

- API documentation quality
- Authentication complexity
- API coverage
- Rate limits
- Access restrictions
- MCP availability
- Implementation complexity

Give a practical assessment.


8. MAIN BLOCKER

Identify the most important obstacle to building
a reliable integration.


9. EVIDENCE URLS

Use only URLs included in the supplied research sources.

Do not invent URLs.

Only include sources that directly support your findings.


10. CONFIDENCE

Provide a confidence score between 0 and 1.

Reduce confidence when:
- Evidence is incomplete
- Sources are indirect
- Sources contradict one another
- Documentation is outdated
- Important details cannot be verified


IMPORTANT RULES
================

- Never invent API endpoints.
- Never invent authentication methods.
- Never assume API access is freely available.
- Never assume an MCP server is official.
- Explicitly state when information is unknown.
- Distinguish documented facts from your assessment.
- Flag weak or missing evidence for human review.
- Keep explanations concise but informative.


RESEARCH SOURCES
================

{source_text}

Return the result in the exact structured JSON format
defined by the AppResearch schema.
"""


# ============================================================
# 8. GEMINI GENERATION WITH RETRIES AND FALLBACKS
# ============================================================

def generate_research(
    gemini_client: genai.Client,
    app: Dict[str, Any],
    sources: List[Dict[str, str]]
) -> AppResearch:

    prompt = create_research_prompt(
        app,
        sources
    )

    if not sources:

        print(
            "Warning: No sources found. "
            "Research will require human review."
        )

    unique_models = list(
        dict.fromkeys(MODEL_FALLBACKS)
    )

    last_error = None

    for model_name in unique_models:

        print(
            f"\nTrying Gemini model: {model_name}"
        )

        for attempt in range(
            1,
            MAX_RETRIES + 1
        ):

            try:

                response = gemini_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=AppResearch,
                        temperature=0.1,
                    ),
                )

                if not response.text:
                    raise ValueError(
                        "Gemini returned an empty response."
                    )

                report = AppResearch.model_validate_json(
                    response.text
                )

                # Keep only URLs returned by Tavily.
                valid_urls = {
                    source["url"]
                    for source in sources
                }

                report.evidence_urls = [
                    url
                    for url in report.evidence_urls
                    if url in valid_urls
                ]

                # Preserve identity from the dataset.
                report.app_name = app["name"]
                report.category = app["category"]

                # Flag insufficient evidence.
                if not report.evidence_urls:
                    report.human_review_required = True

                if report.confidence < 0.65:
                    report.human_review_required = True

                if not sources:
                    report.human_review_required = True

                print(
                    f"Research completed using {model_name}"
                )

                return report

            except errors.APIError as error:

                last_error = error

                status_code = getattr(
                    error,
                    "code",
                    None
                )

                error_message = str(error).lower()

                print(
                    f"Gemini API error ({status_code}) "
                    f"on attempt {attempt}: {error}"
                )

                # Stop immediately if Gemini quota is exhausted.
                if status_code == 429 and (
                    "quota" in error_message
                    or "resource_exhausted" in error_message
                    or "resource exhausted" in error_message
                ):

                    raise GeminiQuotaExhausted(
                        f"Gemini quota exhausted: {error}"
                    ) from error

                # Try another model if this model ID is unavailable.
                if status_code == 404:

                    print(
                        f"Model {model_name} unavailable. "
                        "Trying the next model."
                    )

                    break

                # Retry temporary errors only.
                if status_code in RETRYABLE_STATUS_CODES:

                    if attempt < MAX_RETRIES:

                        wait_time = 2 ** attempt

                        print(
                            f"Retrying in {wait_time} seconds..."
                        )

                        time.sleep(wait_time)
                        continue

                    print(
                        f"Retries exhausted for {model_name}."
                    )

                    break

                # Do not hide authentication or permission errors.
                raise

            except Exception as error:

                last_error = error

                print(
                    f"Research generation or validation failed: {error}"
                )

                raise

    raise RuntimeError(
        f"All Gemini models failed. Last error: {last_error}"
    )


# ============================================================
# 9. SAVE INDIVIDUAL RESEARCH REPORT
# ============================================================

def save_report(
    report: AppResearch,
    app_name: str
) -> Path:

    output_file = get_report_path(app_name)

    write_json_atomic(
        output_file,
        report.model_dump()
    )

    print(
        f"\nReport saved: {output_file}"
    )

    return output_file


# ============================================================
# 10. RESEARCH ONE APPLICATION
# ============================================================

def research_app(
    app: Dict[str, Any],
    gemini_client: genai.Client,
    tavily_client: TavilyClient
) -> AppResearch:

    print("\n" + "=" * 60)

    print(
        f"APPINTEL AI: {app['name']}"
    )

    print("=" * 60)

    sources = search_app_documentation(
        tavily_client,
        app["name"]
    )

    report = generate_research(
        gemini_client,
        app,
        sources
    )

    # Save individual report immediately.
    save_report(
        report,
        app["name"]
    )

    return report


# ============================================================
# 11. LOAD PREVIOUSLY COMPLETED REPORTS
# ============================================================

def load_completed_reports(
    apps: List[Dict[str, Any]]
) -> Dict[str, AppResearch]:

    completed = {}

    for app in apps:

        report_file = get_report_path(
            app["name"]
        )

        if not report_file.exists():
            continue

        try:

            with open(
                report_file,
                "r",
                encoding="utf-8"
            ) as file:

                report_data = json.load(file)

            report = AppResearch.model_validate(
                report_data
            )

            # Verify application identity and category.
            if (
                report.app_name.strip().lower()
                != app["name"].strip().lower()
            ):

                print(
                    f"Skipping mismatched report: {app['name']}"
                )

                continue

            if report.category != app["category"]:

                print(
                    f"Skipping category mismatch: {app['name']}"
                )

                continue

            completed[app["name"]] = report

        except Exception as error:

            print(
                f"Existing report needs regeneration: "
                f"{app['name']} - {error}"
            )

    return completed


# ============================================================
# 12. LOAD PREVIOUS FAILURE RECORDS
# ============================================================

def load_failure_log() -> Dict[str, Dict[str, Any]]:

    if not FAILURE_LOG.exists():
        return {}

    try:

        with open(
            FAILURE_LOG,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        failures = data.get(
            "failed_applications",
            []
        )

        return {
            item["app_name"]: item
            for item in failures
            if "app_name" in item
        }

    except Exception as error:

        print(
            f"Could not read previous failure log: {error}"
        )

        return {}


# ============================================================
# 13. SAVE FAILURE LOG
# ============================================================

def save_failure_log(
    failures: Dict[str, Dict[str, Any]]
):

    failure_data = {
        "last_updated": datetime.now(
            timezone.utc
        ).isoformat(),

        "total_failures": len(failures),

        "failed_applications": list(
            failures.values()
        )
    }

    write_json_atomic(
        FAILURE_LOG,
        failure_data
    )


# ============================================================
# 14. SAVE MASTER JSON AND CSV
# ============================================================

def save_master_files(
    apps: List[Dict[str, Any]],
    completed: Dict[str, AppResearch]
):

    # Preserve original dataset ordering.
    ordered_reports = [
        completed[app["name"]].model_dump()
        for app in apps
        if app["name"] in completed
    ]

    # Save consolidated JSON.
    write_json_atomic(
        MASTER_JSON,
        ordered_reports
    )

    # Save consolidated CSV.
    if ordered_reports:

        fieldnames = list(
            ordered_reports[0].keys()
        )

        temporary_csv = MASTER_CSV.with_name(
            MASTER_CSV.name + ".tmp"
        )

        with open(
            temporary_csv,
            "w",
            encoding="utf-8-sig",
            newline=""
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames
            )

            writer.writeheader()

            for report in ordered_reports:

                csv_row = report.copy()

                for key, value in csv_row.items():

                    if isinstance(value, list):

                        csv_row[key] = json.dumps(
                            value,
                            ensure_ascii=False
                        )

                writer.writerow(csv_row)

        os.replace(
            temporary_csv,
            MASTER_CSV
        )

    print("\nMASTER FILES UPDATED")

    print(
        f"Reports included: {len(ordered_reports)}"
    )

    print("JSON:", MASTER_JSON)
    print("CSV:", MASTER_CSV)


# ============================================================
# 15. BATCH RESEARCH ENGINE
# ============================================================

def run_batch_research():

    print("\n" + "=" * 65)
    print("APPINTEL AI - BATCH RESEARCH ENGINE")
    print("=" * 65)

    print(
        "Primary model:",
        PRIMARY_MODEL
    )

    # Initialize clients.
    gemini_client, tavily_client = initialize_clients()

    # Load and validate dataset.
    apps = load_apps()

    # Load previously completed reports.
    completed = load_completed_reports(apps)

    print(
        f"\nPreviously completed applications: {len(completed)}"
    )

    # Load persistent failures.
    failures = load_failure_log()

    # Identify applications that need processing.
    pending_apps = []

    for app in apps:

        is_completed = (
            app["name"] in completed
        )

        if FORCE_RERUN or not is_completed:
            pending_apps.append(app)

    # Apply per-run processing limit.
    if MAX_APPS_PER_RUN is not None:

        pending_apps = pending_apps[
            :MAX_APPS_PER_RUN
        ]

    print(
        f"Applications pending: {len(apps) - len(completed)}"
    )

    print(
        f"Applications to process this run: {len(pending_apps)}"
    )

    if not pending_apps:

        print(
            "\nNo pending applications. "
            "All reports are already completed."
        )

        save_master_files(
            apps,
            completed
        )

        save_failure_log(
            failures
        )

        return

    # Process applications one at a time.
    for index, app in enumerate(
        pending_apps,
        start=1
    ):

        print("\n" + "#" * 65)

        print(
            f"PROGRESS: {index}/{len(pending_apps)}"
        )

        print(
            f"APPLICATION: {app['name']}"
        )

        print(
            f"CATEGORY: {app['category']}"
        )

        print("#" * 65)

        try:

            report = research_app(
                app,
                gemini_client,
                tavily_client
            )

            # Mark application as completed.
            completed[app["name"]] = report

            # Remove old failure if it now succeeds.
            failures.pop(
                app["name"],
                None
            )

            print(
                f"\nCHECKPOINT SAVED: {app['name']}"
            )

        except GeminiQuotaExhausted as error:

            print("\n" + "!" * 60)
            print("GEMINI QUOTA EXHAUSTED - PAUSING BATCH")
            print("!" * 60)

            print(str(error))

            failures[app["name"]] = {
                "app_name": app["name"],
                "category": app["category"],
                "error": str(error),
                "status": "deferred_due_to_quota",
                "last_attempt": datetime.now(
                    timezone.utc
                ).isoformat()
            }

            # Save all completed reports and failures before stopping.
            save_master_files(
                apps,
                completed
            )

            save_failure_log(
                failures
            )

            print(
                "\nBatch paused safely. "
                "Run again after the Gemini quota resets."
            )

            break

        except Exception as error:

            print(
                f"\nAPPLICATION FAILED: {app['name']}"
            )

            print(
                "Reason:",
                str(error)
            )

            failures[app["name"]] = {
                "app_name": app["name"],
                "category": app["category"],
                "error": str(error),
                "status": "failed",
                "last_attempt": datetime.now(
                    timezone.utc
                ).isoformat()
            }

        # Save all completed results after every application.
        save_master_files(
            apps,
            completed
        )

        # Save persistent failures.
        save_failure_log(
            failures
        )

        print("\nCURRENT PROGRESS")

        print(
            f"Completed: {len(completed)}/{len(apps)}"
        )

        print(
            f"Remaining: {len(apps) - len(completed)}"
        )

        print(
            f"Recorded failures: {len(failures)}"
        )

    # Final summary.
    print("\n" + "=" * 65)
    print("BATCH RESEARCH RUN FINISHED")
    print("=" * 65)

    print(
        f"Total completed: {len(completed)}/{len(apps)}"
    )

    print(
        f"Remaining: {len(apps) - len(completed)}"
    )

    print(
        f"Total recorded failures: {len(failures)}"
    )

    print("\nOUTPUT FILES")

    print(MASTER_JSON)
    print(MASTER_CSV)
    print(FAILURE_LOG)


# ============================================================
# 16. APPLICATION ENTRY POINT
# ============================================================

def main():

    run_batch_research()


if __name__ == "__main__":
    main()
