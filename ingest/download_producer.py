from redis import Redis

from ingest.database import mark_download_job_queued, get_pending_download_jobs
from ingest.download_queue import add_download_message, get_redis_client, initialize_download_queue
from ingest.models import PendingDownloadJob


def publish_download_job(client: Redis, job_id: int,
                         accession_number: str, manifest_key: str) -> str:

    message_id = add_download_message(client, job_id, accession_number, manifest_key)
    mark_download_job_queued(job_id, message_id)
    return message_id

def publish_pending_download_jobs(client: Redis, limit: int = 100,) -> list[str]:
    jobs: list[PendingDownloadJob] = get_pending_download_jobs(limit)
    message_ids: list[str] = []

    for job in jobs:
        message_id = publish_download_job(
            client, job.job_id, job.accession_number,job.manifest_key,)
        message_ids.append(message_id)

        print(
            f"Published job {job.job_id} "
            f"as Redis message {message_id}"
        )

    return message_ids

def main() -> None:
    with get_redis_client() as redis_client:
        initialize_download_queue(redis_client)

        message_ids = publish_pending_download_jobs(
            redis_client
        )

        print(f"Published {len(message_ids)} job(s).")


if __name__ == "__main__":
    main()
