# Redis Queue Handoff

## Purpose
A generic Redis-backed queue used to decouple pipeline stages and support async workers. The same queue implementation is reused for both discovery (normalization -> pre-check) and generation (cybersec -> Gemini) by configuring different stream names.

## Implementation
- Source: `app/core/queue.py`
- Backend: Redis Streams with consumer groups
- Client: `redis.asyncio`

## Config
`RedisQueueConfig` fields:
- `url`: Redis connection URL (default `redis://localhost:6379/0`)
- `stream_name`: Stream key (default `trendfinder:queue`)
- `group_name`: Consumer group name (default `trendfinder`)
- `consumer_name`: Consumer name (default `worker-1`)
- `max_len`: Stream trim length (default `10000`, approximate)
- `block_ms`: Blocking read timeout (default `5000`)

## Queue Behavior
- Uses `xadd` to enqueue a JSON payload under the `payload` field.
- Uses `xreadgroup` to read messages from the consumer group.
- Requires `ack()` to acknowledge processed messages.
- Automatically creates the stream and consumer group on first use.

## Discovery Queue Handoff
- Normalized posts are intended to be enqueued into a discovery stream (for pre-batch checks).
- When wired to FastAPI, the API can enqueue and immediately return HTTP 202 to close the request.

## Generation Queue Handoff
- Sanitized context parameters are intended to be enqueued into a generation stream (for Gemini generation).
- When wired to FastAPI, the API can return a task token to the UI after enqueueing.

## Message Shape
Each dequeued item is represented as:
- `message_id`: Redis stream ID
- `payload`: JSON-decoded dict
