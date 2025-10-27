import os
import json
import aiohttp
from typing import Optional, List
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, function_tool, RunContext
from livekit.plugins import noise_cancellation, silero, openai, deepgram, cartesia
from livekit.plugins import azure
from prompt import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from livekit.agents import AgentSession, inference
from datetime import datetime, timedelta, timezone


load_dotenv()





class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=AGENT_INSTRUCTION)

    @function_tool()
    async def check_availability(
        self,
        context: RunContext,
        preferred_start: str,
        calendar_id: str = "primary",
        timezone: str = "Europe/Madrid",
        duration_min: int = 30,
        buffer_min_before: int = 30,
        buffer_min_after: int = 30,
        attendees: list[str] = None
    ) -> dict:
        """Check calendar availability for a specific time slot using N8N webhook.
        
        Args:
            preferred_start: Caller's requested start datetime in RFC3339 with timezone (e.g. 2025-10-26T15:00:00+01:00)
            calendar_id: Calendar identifier (default: 'primary')
            timezone: IANA timezone (default: 'Europe/Madrid')
            duration_min: Meeting duration in minutes (default: 30)
            buffer_min_before: Minutes that must be free before the slot (default: 30)
            buffer_min_after: Minutes that must be free after the slot (default: 30)
            attendees: Optional email(s) of attendees to check conflicts against
        """
        webhook_url = os.getenv("CHECK_AVAILABILITY_WEBHOOK")
        if not webhook_url:
            return {"error": "Check availability webhook URL not configured"}
        
        payload = {
            "preferredStart": preferred_start,
            "calendarId": calendar_id,
            "bufferMinBefore": buffer_min_before,
            "timezone": timezone,
            "durationMin": duration_min,
            "bufferMinAfter": buffer_min_after
        }
        
        if attendees:
            payload["attendees"] = attendees
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result
                    else:
                        error_text = await response.text()
                        return {
                            "error": f"Webhook request failed with status {response.status}",
                            "details": error_text
                        }
        except Exception as e:
            return {
                "error": f"Failed to call availability webhook: {str(e)}"
            }

    @function_tool()
    async def create_booking(
        self,
        context: RunContext,
        name: str,
        email: str,
        chosen_start: str,
        calendar_id: str = "primary",
        timezone: str = "Europe/Madrid"
    ) -> dict:
        """Create a calendar booking using N8N webhook.
        
        Args:
            name: The caller's full name
            email: The caller's email address
            chosen_start: The confirmed start time in RFC3339 format
            calendar_id: Target calendar identifier (default: 'primary')
            timezone: IANA timezone (default: 'Europe/Madrid')
        """
        webhook_url = os.getenv("BOOKING_WEBHOOK")
        if not webhook_url:
            return {"error": "Booking webhook URL not configured"}
        
        payload = {
            "name": name,
            "email": email,
            "chosenStart": chosen_start,
            "calendarId": calendar_id,
            "timezone": timezone
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result
                    else:
                        error_text = await response.text()
                        return {
                            "error": f"Booking webhook request failed with status {response.status}",
                            "details": error_text
                        }
        except Exception as e:
            return {
                "error": f"Failed to call booking webhook: {str(e)}"
            }


async def entrypoint(ctx: agents.JobContext):
    # OpenRouter configuration
    openrouter_model = os.getenv("OPENROUTER_MODEL")
    openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    
    agent = Assistant()
    
    session = AgentSession(
        stt=deepgram.STT(model="nova-2"),
        llm=openai.LLM(
            model=openrouter_model,
            base_url=openrouter_base_url,
            api_key=openrouter_api_key
        ),
       tts=azure.TTS(
        speech_key=os.getenv("AZURE_SPEECH_KEY"),
        speech_region=os.getenv("AZURE_SPEECH_REGION"),
        voice="en-US-NancyMultilingualNeural",
        ),
        vad=silero.VAD.load(),

    )

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` instead for best results
            noise_cancellation=noise_cancellation.BVC(), 
        ),
    )
    
    # Send initial greeting and start conversation loop
    await session.say("Hello, this is Alex from impress dental, how can I help you?")
    
    # Generate initial reply to start the conversation loop
    await session.generate_reply(instructions="You are now ready to help the customer. Wait for their response and assist them professionally.")


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))