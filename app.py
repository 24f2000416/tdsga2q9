from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uuid
import time
import base64

app = FastAPI()

# -----------------------------
# Enable CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# ASSIGNED VALUES
# -----------------------------
TOTAL_ORDERS = 46
RATE_LIMIT = 16
WINDOW = 10  # seconds

# -----------------------------
# In-memory stores
# -----------------------------
idempotency_store = {}
client_requests = {}

# -----------------------------
# Fixed catalog
# -----------------------------
orders = [
    {
        "id": i,
        "item": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# -----------------------------
# Cursor helpers
# -----------------------------
def encode_cursor(index: int):
    return base64.b64encode(str(index).encode()).decode()

def decode_cursor(cursor: str):
    try:
        return int(base64.b64decode(cursor).decode())
    except:
        return 0

# -----------------------------
# Rate Limiter
# -----------------------------
@app.middleware("http")
async def rate_limit(request, call_next):

    client = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()

    history = client_requests.get(client, [])

    history = [t for t in history if now - t < WINDOW]

    if len(history) >= RATE_LIMIT:

        retry = WINDOW - (now - history[0])

        return Response(
            status_code=429,
            headers={
                "Retry-After": str(int(retry) + 1)
            },
            content="Rate limit exceeded"
        )

    history.append(now)

    client_requests[client] = history

    response = await call_next(request)

    return response

# -----------------------------
# Idempotent POST
# -----------------------------
@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: Optional[str] = Header(default=None)
):

    if idempotency_key is None:
        raise HTTPException(
            status_code=400,
            detail="Missing Idempotency-Key"
        )

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4())
    }

    idempotency_store[idempotency_key] = order

    return order

# -----------------------------
# Pagination
# -----------------------------
@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None
):

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