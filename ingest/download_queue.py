from redis import Redis
from redis.exceptions import ResponseError

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

if __name__ == "__main__":
    main()