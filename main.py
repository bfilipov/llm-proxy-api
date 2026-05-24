import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Dict, Optional, Any

from fastapi import FastAPI, HTTPException
from openai.types import CompletionUsage
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from pydantic import BaseModel

from src.LLM_integrations.qwen.api import QwenApi
from src.server.middlewares import RequestLoggerMiddleware

qwen = QwenApi()
request_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, qwen.start)
    yield
    await loop.run_in_executor(None, qwen.close)


app = FastAPI(lifespan=lifespan)

# Register middlewares
RequestLoggerMiddleware(app)


class MessageRequest(BaseModel):
    message: str


class MessageResponse(BaseModel):
    response: str


@app.head("/")
@app.get("/")
async def root():
    return {"status": "ok"}


@app.post("/v1/chat", response_model=MessageResponse)
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


# --------------------------------------------------------------
# OpenAI‑compatible endpoint
# --------------------------------------------------------------

class OpenAIChatRequest(BaseModel):
    messages: list[dict]
    model: str = "qwen"
    stream: bool = False


@app.post("/v1/chat/completions", response_model=ChatCompletion)
async def openai_completions(request: OpenAIChatRequest):
    # Extract the last user message (simplest – you can also concatenate history)
    user_message = None
    for msg in reversed(request.messages):
        if msg.get("role") == "user":
            user_message = msg.get("content", "")
            break

    if not user_message:
        raise HTTPException(status_code=400, detail="No user message found in the request")

    async with request_lock:
        loop = asyncio.get_event_loop()
        try:
            assistant_reply = await loop.run_in_executor(None, qwen.send_message, user_message)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Build OpenAI‑style response
    response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_at = int(datetime.now().timestamp())

    choice = Choice(
        index=0,
        message=ChatCompletionMessage(role="assistant", content=assistant_reply),
        finish_reason="stop"
    )

    usage = CompletionUsage(
        prompt_tokens=0,  # we don't have token counts from the browser
        completion_tokens=0,
        total_tokens=0
    )

    response = ChatCompletion(
        id=response_id,
        object="chat.completion",
        created=created_at,
        model=request.model,  # echo back the requested model name
        choices=[choice],
        usage=usage
    )

    return response


# --------------------------------------------------------------
# Claude-Code‑compatible endpoint
# --------------------------------------------------------------

# Add these imports


class ClaudeMessageRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    max_tokens: Optional[int] = 1024
    stream: Optional[bool] = False
    # Allow any other fields like system, tools, output_config, etc.
    class Config:
        extra = "allow"


@app.post("/v1/messages")
async def claude_messages(request: ClaudeMessageRequest, beta: bool = False):
    # 1. Handle structured output requests (e.g., session title generation)
    if hasattr(request, 'output_config') and request.output_config:
        fmt = request.output_config.get('format', {})
        if fmt.get('type') == 'json_schema':
            # Extract the user's original request from the <session> tags
            user_text = extract_user_text(request.messages)
            # Generate a simple title (you can make this smarter)
            title = (user_text[:60] + "...") if len(user_text) > 60 else user_text
            # Return the JSON inside a standard assistant message
            return {
                "id": f"msg_{uuid.uuid4().hex[:12]}",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": json.dumps({"title": title})}],
                "model": request.model,
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0}
            }

    user_message = extract_user_text(request.messages)
    if not user_message:
        raise HTTPException(status_code=400, detail="No user message found")

    async with request_lock:
        loop = asyncio.get_event_loop()
        try:
            assistant_reply = await loop.run_in_executor(None, qwen.send_message, user_message)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Qwen error: {str(e)}")

    return {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": assistant_reply}],
        "model": request.model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0}
    }


def extract_user_text(messages: List[Dict]) -> str:
    """Extract the last user message text from Claude's message array."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        return block.get("text", "")
    return ""
