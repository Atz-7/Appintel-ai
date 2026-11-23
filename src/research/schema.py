from typing import List, Optional
from pydantic import BaseModel, Field


class AppResearch(BaseModel):
    app_name: str

    category: str

    description: str

    auth_methods: List[str] = Field(
        description="Authentication methods supported by the application API."
    )

    access_model: str = Field(
        description=(
            "Describe whether API access is public, self-serve, "
            "approval-based, partner-only, enterprise-only, or restricted."
        )
    )

    api_type: List[str] = Field(
        description="API types such as REST, GraphQL, SOAP, or Webhooks."
    )

    api_breadth: str = Field(
        description=(
            "Describe the breadth of API coverage, important endpoints, "
            "and major limitations."
        )
    )

    existing_mcp: str = Field(
        description=(
            "State whether an official or third-party MCP server exists. "
            "Clearly distinguish between the two."
        )
    )

    buildability: str = Field(
        description=(
            "Assess how practical it would be to build an integration "
            "for this application."
        )
    )

    main_blocker: Optional[str] = None

    evidence_urls: List[str] = Field(
        description="URLs of sources that directly support the findings."
    )

    confidence: float = Field(
        ge=0,
        le=1,
        description="Confidence score between 0 and 1."
    )

    human_review_required: bool = False