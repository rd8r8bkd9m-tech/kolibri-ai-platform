from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Header, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal, principal_from_request, principal_from_token
from ..errors import APIError
from ..serializers import response_object
from ..store import json_dumps

router = APIRouter(tags=["responses"])


class ResponseCreate(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = "kolibri"
    input: Any
    project_id: str | None = None
    conversation: str | None = None
    previous_response_id: str | None = None
    background: bool = False
    stream: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_choice: Any = "auto"


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionCreate(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = "kolibri"
    messages: list[ChatMessage]
    stream: bool = False


def _project_for(payload: ResponseCreate, request: Request, principal: Principal) -> dict[str, Any]:
    store = request.app.state.store
    project_id = payload.project_id or payload.conversation
    if project_id:
        project = store.get_project(project_id, principal.session_id)
        if project and not project.get("deleted_at"):
            return project
        raise APIError("Project not found.", 404, "invalid_request_error", "project_id", "project_not_found")
    projects = store.list_projects(principal.session_id)
    return projects[0] if projects else store.create_project(principal.session_id, "Первый проект")


def _request_hash(payload: ResponseCreate) -> str:
    return hashlib.sha256(json_dumps(payload.model_dump(mode="json")).encode()).hexdigest()


async def _event_stream(request: Request, response_id: str, session_id: str, starting_after: int = 0) -> AsyncIterator[bytes]:
    store = request.app.state.store
    cursor = starting_after
    terminal = {"response.completed", "response.failed", "response.cancelled"}
    idle = 0
    while True:
        response = store.get_response(response_id, session_id)
        if not response:
            yield b'event: error\ndata: {"error":{"message":"Response not found","type":"invalid_request_error","code":"response_not_found"}}\n\n'
            return
        events = store.list_response_events(response_id, cursor)
        if events:
            idle = 0
            for event in events:
                cursor = int(event["sequence"])
                payload = {"type": event["type"], "sequence_number": cursor, **event["data"]}
                yield f"event: {event['type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
                if event["type"] in terminal:
                    yield b"data: [DONE]\n\n"
                    return
        else:
            idle += 1
            if response["status"] in {"completed", "failed", "cancelled"}:
                yield b"data: [DONE]\n\n"
                return
            if idle % 15 == 0:
                yield b": keep-alive\n\n"
            await asyncio.sleep(0.05)


@router.post("/v1/responses")
async def create_response(
    payload: ResponseCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(principal_from_request),
):
    if payload.model != "kolibri":
        raise APIError("Only the public model 'kolibri' is available.", 400, "invalid_request_error", "model", "model_not_found")
    project = _project_for(payload, request, principal)
    try:
        row, created = request.app.state.store.create_response(principal.session_id, project["id"], payload.model_dump(), _request_hash(payload), idempotency_key)
    except ValueError as exc:
        if str(exc) == "idempotency_conflict":
            raise APIError("The Idempotency-Key was already used with a different request.", 409, "invalid_request_error", code="idempotency_conflict")
        raise
    if created:
        from ..engine import input_text
        request.app.state.store.add_message(project["id"], "user", input_text(payload.input), row["id"] + ":user")
        request.app.state.store.add_message(project["id"], "assistant", "", row["id"])
    if payload.stream:
        request.app.state.engine.schedule(row["id"])
        return StreamingResponse(_event_stream(request, row["id"], principal.session_id), media_type="text/event-stream")
    if payload.background:
        request.app.state.engine.schedule(row["id"])
        return response_object(request.app.state.store.get_response(row["id"], principal.session_id) or row)
    await request.app.state.engine.run(row["id"])
    return response_object(request.app.state.store.get_response(row["id"], principal.session_id) or row)


@router.get("/v1/responses/{response_id}")
async def get_response(
    response_id: str,
    request: Request,
    stream: bool = Query(default=False),
    starting_after: int = Query(default=0, ge=0),
    principal: Principal = Depends(principal_from_request),
):
    row = request.app.state.store.get_response(response_id, principal.session_id)
    if not row:
        raise APIError("Response not found.", 404, code="response_not_found")
    if stream:
        return StreamingResponse(_event_stream(request, response_id, principal.session_id, starting_after), media_type="text/event-stream")
    return response_object(row)


@router.get("/v1/responses/{response_id}/events")
def response_events(
    response_id: str,
    request: Request,
    starting_after: int = Query(default=0, ge=0),
    principal: Principal = Depends(principal_from_request),
):
    if not request.app.state.store.get_response(response_id, principal.session_id):
        raise APIError("Response not found.", 404, code="response_not_found")
    return {"object": "list", "data": request.app.state.store.list_response_events(response_id, starting_after)}


@router.post("/v1/responses/{response_id}/cancel")
def cancel_response(response_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    row = request.app.state.store.get_response(response_id, principal.session_id)
    if not row:
        raise APIError("Response not found.", 404, code="response_not_found")
    if row["status"] not in {"completed", "failed", "cancelled"}:
        request.app.state.store.update_response(response_id, status="cancelled")
        request.app.state.store.append_response_event(response_id, "response.cancelled", {"status": "cancelled"})
    return response_object(request.app.state.store.get_response(response_id, principal.session_id) or row)


@router.delete("/v1/responses/{response_id}")
def delete_response(response_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    row = request.app.state.store.get_response(response_id, principal.session_id)
    if not row:
        raise APIError("Response not found.", 404, code="response_not_found")
    request.app.state.store.execute("DELETE FROM response_events WHERE response_id=?", (response_id,))
    request.app.state.store.execute("DELETE FROM responses WHERE id=?", (response_id,))
    return {"id": response_id, "object": "response.deleted", "deleted": True}


@router.get("/v1/responses/{response_id}/input_items")
def input_items(response_id: str, request: Request, principal: Principal = Depends(principal_from_request)):
    row = request.app.state.store.get_response(response_id, principal.session_id)
    if not row:
        raise APIError("Response not found.", 404, code="response_not_found")
    return {"object": "list", "data": [{"id": f"input_{response_id}", "type": "message", "role": "user", "content": json.loads(row["input_json"])}]}


@router.post("/v1/responses/input_tokens")
def input_tokens(payload: ResponseCreate, principal: Principal = Depends(principal_from_request)):
    from ..engine import input_text
    text = input_text(payload.input)
    return {"object": "response.input_tokens", "input_tokens": max(1, len(text) // 4)}


@router.post("/v1/responses/compact")
def compact_response(payload: ResponseCreate, principal: Principal = Depends(principal_from_request)):
    from ..engine import input_text
    text = input_text(payload.input)
    return {"object": "response.compaction", "model": "kolibri", "compacted_text": text[-8000:]}


@router.get("/v1/models")
def list_models(principal: Principal = Depends(principal_from_request)):
    return {"object": "list", "data": [{"id": "kolibri", "object": "model", "created": 0, "owned_by": "kolibri"}]}


@router.get("/v1/models/{model_id}")
def get_model(model_id: str, principal: Principal = Depends(principal_from_request)):
    if model_id != "kolibri":
        raise APIError("Model not found.", 404, "invalid_request_error", "model", "model_not_found")
    return {"id": "kolibri", "object": "model", "created": 0, "owned_by": "kolibri"}


@router.delete("/v1/models/{model_id}")
def delete_model(model_id: str, principal: Principal = Depends(principal_from_request)):
    raise APIError("The public model cannot be deleted.", 405, "invalid_request_error", "model", "model_delete_not_supported")


@router.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionCreate, request: Request, principal: Principal = Depends(principal_from_request)):
    text = "\n".join(str(message.content) for message in payload.messages if message.role == "user")
    response_payload = ResponseCreate(model="kolibri", input=text, stream=payload.stream)
    project = _project_for(response_payload, request, principal)
    row, _ = request.app.state.store.create_response(principal.session_id, project["id"], response_payload.model_dump(), _request_hash(response_payload), None)
    request.app.state.store.add_message(project["id"], "user", text, row["id"] + ":user")
    request.app.state.store.add_message(project["id"], "assistant", "", row["id"])
    if payload.stream:
        request.app.state.engine.schedule(row["id"])
        async def stream_chat():
            async for chunk in _event_stream(request, row["id"], principal.session_id):
                if chunk.startswith(b"event: response.output_text.delta"):
                    data = json.loads(chunk.split(b"data: ",1)[1])
                    event = {"id": row["id"], "object": "chat.completion.chunk", "model": "kolibri", "choices": [{"index": 0, "delta": {"content": data.get("delta", "")}, "finish_reason": None}]}
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
                elif chunk == b"data: [DONE]\n\n":
                    yield chunk
            return
        return StreamingResponse(stream_chat(), media_type="text/event-stream")
    await request.app.state.engine.run(row["id"])
    final = request.app.state.store.get_response(row["id"], principal.session_id) or row
    return {"id": row["id"], "object": "chat.completion", "model": "kolibri", "choices": [{"index": 0, "message": {"role": "assistant", "content": final["output_text"]}, "finish_reason": "stop"}], "usage": {"prompt_tokens": max(1,len(text)//4), "completion_tokens": max(1,len(final["output_text"])//4), "total_tokens": max(2,(len(text)+len(final["output_text"]))//4)}}


@router.websocket("/v1/realtime")
async def realtime(websocket: WebSocket):
    authorization = websocket.headers.get("authorization", "")
    token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else websocket.query_params.get("token")
    principal = principal_from_token(websocket.scope["app"], token)
    if not principal:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "error": {
                "message": "A valid bearer token is required.",
                "type": "authentication_error",
                "code": "invalid_api_key",
            },
        })
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        await websocket.send_json({
            "type": "session.created",
            "session": {"model": "kolibri", "role": principal.role},
        })
        while True:
            event = await websocket.receive_json()
            await websocket.send_json({"type": "session.updated", "session": {"model": "kolibri"}})
            if event.get("type") in {"input_audio_buffer.commit", "response.create"}:
                await websocket.send_json({"type": "response.output_text.delta", "delta": "Realtime session is connected to Kolibri."})
                await websocket.send_json({"type": "response.done", "response": {"status": "completed"}})
    except WebSocketDisconnect:
        return
