import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.LLM_integrations.qwen.api import QwenApi

qwen = QwenApi()
request_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, qwen.start)
    yield
    await loop.run_in_executor(None, qwen.close)


app = FastAPI(lifespan=lifespan)


class MessageRequest(BaseModel):
    message: str


class MessageResponse(BaseModel):
    response: str


@app.post("/chat", response_model=MessageResponse)
async def chat_endpoint(request: MessageRequest):
    """Send a message to Qwen and return the assistant's reply."""
    async with request_lock:
        loop = asyncio.get_event_loop()
        try:
            # Run the synchronous send_message in a thread pool
            result = await loop.run_in_executor(
                None, qwen.send_message, request.message
            )
            return MessageResponse(response=result)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
