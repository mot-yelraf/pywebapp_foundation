"""Expose optional job submission, status, and cancellation routes.

All operations are registered server-side and share the foundation security layer.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response

from pwaf_foundation.errors import ERROR_RESPONSES
from pwaf_foundation.jobs import JobRecord, JobSubmission


def job_router() -> APIRouter:
    """Build job routes for an application whose state includes a JobManager."""
    router = APIRouter(prefix="/api/jobs", tags=["jobs"], responses=ERROR_RESPONSES)

    @router.post("", response_model=JobRecord, status_code=202)
    async def submit(
        request: Request,
        response: Response,
        submission: JobSubmission,
        idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ) -> JobRecord:
        """Accept work, or reuse a matching key while its job record is retained."""
        record = request.app.state.jobs.submit(
            submission.operation,
            submission.parameters,
            idempotency_key,
            owner=request.state.identity,
        )
        response.headers["Location"] = record.status_url
        return record

    @router.get("/{job_id}", response_model=JobRecord)
    async def status(request: Request, job_id: str) -> JobRecord:
        """Read ephemeral status; missing/expired/restarted jobs return 404."""
        return request.app.state.jobs.get(job_id, owner=request.state.identity)

    @router.post("/{job_id}/cancel", response_model=JobRecord, status_code=202)
    async def cancel(request: Request, job_id: str) -> JobRecord:
        """Request cancellation; cleanup can finish after this response."""
        return request.app.state.jobs.cancel(job_id, owner=request.state.identity)

    return router
