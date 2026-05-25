"""Redis-backed queue for async pipeline stages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import redis.asyncio as redis
from redis.exceptions import ResponseError


@dataclass(frozen=True)
class QueueMessage:
	message_id: str
	payload: dict[str, Any]


@dataclass(frozen=True)
class RedisQueueConfig:
	url: str = "redis://localhost:6379/0"
	stream_name: str = "trendfinder:queue"
	group_name: str = "trendfinder"
	consumer_name: str = "worker-1"
	max_len: int | None = 10000
	block_ms: int = 5000


class RedisQueue:
	def __init__(self, client: redis.Redis, config: RedisQueueConfig) -> None:
		self._client = client
		self._config = config

	@classmethod
	async def create(cls, config: RedisQueueConfig) -> "RedisQueue":
		client = redis.from_url(config.url, decode_responses=True)
		queue = cls(client, config)
		await queue._ensure_group()
		return queue

	async def enqueue(self, payload: dict[str, Any]) -> str:
		data = {"payload": _serialize_payload(payload)}
		kwargs: dict[str, Any] = {"stream": self._config.stream_name, "fields": data}
		if self._config.max_len is not None:
			kwargs["maxlen"] = self._config.max_len
			kwargs["approximate"] = True
		return await self._client.xadd(**kwargs)

	async def enqueue_many(self, payloads: Iterable[dict[str, Any]]) -> list[str]:
		message_ids: list[str] = []
		for payload in payloads:
			message_ids.append(await self.enqueue(payload))
		return message_ids

	async def dequeue(self, count: int = 1) -> list[QueueMessage]:
		response = await self._client.xreadgroup(
			groupname=self._config.group_name,
			consumername=self._config.consumer_name,
			streams={self._config.stream_name: ">"},
			count=count,
			block=self._config.block_ms,
		)
		return _parse_messages(response)

	async def ack(self, message_ids: Iterable[str]) -> int:
		ids = list(message_ids)
		if not ids:
			return 0
		return await self._client.xack(self._config.stream_name, self._config.group_name, *ids)

	async def close(self) -> None:
		await self._client.close()

	async def _ensure_group(self) -> None:
		try:
			await self._client.xgroup_create(
				name=self._config.stream_name,
				groupname=self._config.group_name,
				id="0",
				mkstream=True,
			)
		except ResponseError as exc:
			if "BUSYGROUP" not in str(exc):
				raise


def _serialize_payload(payload: dict[str, Any]) -> str:
	return json.dumps(payload, ensure_ascii=False)


def _parse_messages(response: Any) -> list[QueueMessage]:
	messages: list[QueueMessage] = []
	for _stream, entries in response or []:
		for message_id, fields in entries:
			raw_payload = fields.get("payload", "{}")
			payload = json.loads(raw_payload)
			messages.append(QueueMessage(message_id=message_id, payload=payload))
	return messages
