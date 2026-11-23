
from dotenv import load_dotenv
from composio import Composio
from composio_openai_agents import OpenAIAgentsProvider

load_dotenv()

def main():
    print("Connecting to Composio...")

    composio = Composio(
        provider=OpenAIAgentsProvider()
    )

    session = composio.sessions.create(
        user_id="appintel_local",
        mcp=True
    )

    tools = session.tools()

    print("\nSUCCESS: Connected to Composio!")
    print("Session ID:", session.session_id)
    print("Available tools:", len(tools))

    for tool in tools:
        print("-", tool.name)

    print("\nMCP URL generated:", bool(session.mcp.url))

if __name__ == "__main__":
    main()
