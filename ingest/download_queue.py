from redis import Redis
from redis.exceptions import ResponseError
from ingest.models import DownloadQueueMessage

DOWNLOAD_STREAM = "investanalysis:downloads"
DOWNLOAD_GROUP = "downloaders"

def get_redis_client() -> Redis:
    return Redis(
        host='localhost', port=6379, db=0,
        decode_responses=True, socket_connect_timeout=5, socket_timeout=10,
    )

def initialize_download_queue(client: Redis) -> None:
    try:
        client.xgroup_create(
            name=DOWNLOAD_STREAM,
            groupname=DOWNLOAD_GROUP,
            id="0-0",
            mkstream=True,
        )
    except ResponseError as error:
        if not str(error).startswith("BUSYGROUP"):
            raise

def main() -> None:
    with get_redis_client() as redis_client:
        print("Connected:", redis_client.ping())

        initialize_download_queue(redis_client)

        groups = redis_client.xinfo_groups(DOWNLOAD_STREAM)
        print("Consumer groups:", groups)

def add_download_message(client: Redis, job_id: int,
                         accession_number: str, manifest_key: str,) -> str:
    return client.xadd(
        name=DOWNLOAD_STREAM,
        fields={
            "job_id": str(job_id),
            "accession_number": accession_number,
            "manifest_key": manifest_key,
        },
    )

def read_new_download_message(client: Redis, consumer_name: str, count: int = 1, block_ms: int = 5_000) -> list[DownloadQueueMessage]:
    if count < 1:
        raise ValueError("count must be greater than zero")
    if block_ms < 0:
        raise ValueError("block_ms cannot be negative")

    raw_batches = client.xreadgroup(
        groupname = DOWNLOAD_GROUP,
        consumername= consumer_name,
        streams={DOWNLOAD_STREAM: ">"},
        count=count,
        block=block_ms,
    )

    messages: list[DownloadQueueMessage] = []
    for stream_name, entries in raw_batches:
        if stream_name != DOWNLOAD_STREAM:
            raise ValueError(f"Unexpected stream name: {stream_name}")

        for message_id, fields in entries:
            try:
                message = DownloadQueueMessage(
                    message_id=message_id,
                    job_id=int(fields["job_id"]),
                    accession_number=fields["accession_number"],
                    manifest_key=fields["manifest_key"],
                )
            except (KeyError, TypeError) as error:
                raise ValueError(f"Invalid download message {message_id}: {fields}") from error
            messages.append(message)
    return messages

# Redis operation
def acknowledge_download_message(client: Redis, message_id: str) -> None:
    acknowledge_count = client.xack(DOWNLOAD_STREAM, DOWNLOAD_GROUP, message_id)
    if acknowledge_count != 1:
        raise ValueError(f"Expected to acknowledge 1 message {message_id}, but acknowledged {acknowledge_count}")


if __name__ == "__main__":
    main()
