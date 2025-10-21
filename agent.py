import os
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import noise_cancellation, silero, openai, deepgram
from livekit.plugins import cartesia
from prompt import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from livekit.agents import AgentSession, inference
from datetime import datetime, timedelta, timezone
from mcp_client import MCPServerSse
from mcp_client.agent_tools import MCPToolsIntegration
import os

load_dotenv()



class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=AGENT_INSTRUCTION)


async def entrypoint(ctx: agents.JobContext):
    session = AgentSession(
        stt=deepgram.STT(model="nova-2"),
        llm=openai.LLM(
            model=os.getenv("LLM_CHOICE", "google/gemini-2.0-flash-001"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")),
        tts=cartesia.TTS(
            model="sonic-turbo",
            voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
        ),
        vad=silero.VAD.load(),
    )

    # Check if MCP should be enabled
    enable_mcp = os.getenv("ENABLE_MCP", "false").lower() == "true"
    mcp_url = os.environ.get("N8N_MCP_SERVER_URL")
    
    print(f"🔍 MCP Debug Info:")
    print(f"   ENABLE_MCP: {enable_mcp}")
    print(f"   N8N_MCP_SERVER_URL: {mcp_url}")
    
    if enable_mcp and mcp_url:
        print(f"🚀 Attempting to connect to MCP server: {mcp_url}")
        # Try to create agent with MCP tools, fallback to basic agent if MCP fails
        try:
            mcp_server = MCPServerSse(
                params={"url": mcp_url},
                cache_tools_list=True,
                name="SSE MCP Server"
            )
            
            print("🔌 MCP Server created, attempting integration...")
            agent = await MCPToolsIntegration.create_agent_with_tools(
                agent_class=Assistant,
                mcp_servers=[mcp_server]
            )
            print("✅ MCP tools integration successful")
        except Exception as e:
            print(f"⚠️  MCP connection failed: {str(e)}")
            print(f"⚠️  Exception type: {type(e).__name__}")
            import traceback
            print(f"⚠️  Full traceback: {traceback.format_exc()}")
            print("🔄 Falling back to basic agent without MCP tools")
            agent = Assistant()
    else:
        if not enable_mcp:
            print("🔄 MCP disabled in config, using basic agent")
        else:
            print("🔄 MCP URL not found, using basic agent")
        agent = Assistant()

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` instead for best results
            noise_cancellation=noise_cancellation.BVC(), 
        ),
    )

    await session.generate_reply(instructions=SESSION_INSTRUCTION)


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))