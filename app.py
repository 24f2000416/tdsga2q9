from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from typing import Optional
import uuid
import time
import base64

app = FastAPI()

# -------------------------------------------------
# CORS
# -------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

# -------------------------------------------------
# ASSIGNED VALUES
# -------------------------------------------------
TOTAL_ORDERS = 46
RATE_LIMIT = 16
WINDOW = 10  # seconds

# -------------------------------------------------
# STORAGE
# -------------------------------------------------
idempotency_store = {}
client_requests = {}

# -------------------------------------------------
# FIXED ORDERS
# -------------------------------------------------
orders = [
    {
        "id": i,
        "item": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# -------------------------------------------------
# CURSOR HELPERS
# -------------------------------------------------
def encode_cursor(index: int):
    return base64.b64encode(str(index).encode()).decode()


def decode_cursor(cursor: str):
    try:
        return int(base64.b64decode(cursor).decode())
    except Exception:
        return 0


# -------------------------------------------------
# RATE LIMIT MIDDLEWARE
# -------------------------------------------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):

    # Let browser preflight pass
    if request.method == "OPTIONS":
        return await call_next(request)

    client = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()

    history = client_requests.get(client, [])

    history = [t for t in history if now - t < WINDOW]

    if len(history) >= RATE_LIMIT:

        retry = max(1, int(WINDOW - (now - history[0])))

        return Response(
            content="Rate limit exceeded",
            status_code=429,
            headers={
                "Retry-After": str(retry)
            },
        )

    history.append(now)

    client_requests[client] = history

    response = await call_next(request)

    return response


# -------------------------------------------------
# IDEMPOTENT POST
# -------------------------------------------------
@app.post("/orders")
def create_order(
    idempotency_key: Optional[str] = Header(default=None)
):

    if idempotency_key is None:
        raise HTTPException(
            status_code=400,
            detail="Missing Idempotency-Key"
        )

    if idempotency_key in idempotency_store:

        return JSONResponse(
            status_code=201,
            content=idempotency_store[idempotency_key]
        )

    order = {
        "id": str(uuid.uuid4())
    }

    idempotency_store[idempotency_key] = order

    return JSONResponse(
        status_code=201,
        content=order
    )


# -------------------------------------------------
# CURSOR PAGINATION
# -------------------------------------------------
@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None
):

    if limit < 1:
        limit = 1

    start = 0

    if cursor:
        start = decode_cursor(cursor)

    end = min(start + limit, TOTAL_ORDERS)

    items = orders[start:end]

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = encode_cursor(end)

    return {
        "items": items,
        "next_cursor": next_cursor
    }