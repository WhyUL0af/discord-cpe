"""Track linked users across the registered practice pool, without sessions."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models.submission import Submission
from app.providers.submission_provider import SubmissionProvider
from app.repositories.problem_repo import ProblemRepository
from app.repositories.solved_repo import SolvedRepository
from app.repositories.submission_repo import SubmissionRepository
from app.services.submission_service import SubmissionNotification


class ExternalSubmissionService:
    def __init__(self, provider=None):
        self.provider = provider or SubmissionProvider()
        self.cursors = {}  # One committed cursor per linked UVa user and current pool.

    def acknowledge(self, checkpoint):
        key, cursor = checkpoint
        # Called only after the transaction commits. Restart safely reimports history.
        for old_key in list(self.cursors):
            if old_key[0] == key[0] and old_key != key:
                del self.cursors[old_key]
        self.cursors[key] = cursor

    async def sync_user(self, session, user):
        problems = {p.uhunt_pid: p for p in await ProblemRepository.get_all(session) if p.uhunt_pid}
        key = (user.uva_user_id, tuple(sorted(problems)))
        if not user.uva_user_id or not problems:
            return [], (key, 0)
        first_sync = key not in self.cursors
        cursor = self.cursors.get(key, 0)
        pending = await session.scalar(select(func.min(Submission.external_submission_id)).where(
            Submission.user_id == user.id, Submission.source == "uhunt",
            Submission.external_submission_id.isnot(None),
            Submission.verdict.in_(["In queue", "Can't be judged", "Submission error"]),
        ))
        query_cursor = min(cursor, pending - 1) if pending else cursor
        incoming = await self.provider.get_problem_submissions(user.uva_user_id, list(key[1]), query_cursor)
        notifications = []
        for sub in incoming:
            if sub.uhunt_pid not in problems:
                raise ValueError("uHunt returned a submission outside the requested pool")
            problem = problems[sub.uhunt_pid]
            existing = await SubmissionRepository.get_by_external_id(session, sub.submission_id)
            if existing and (existing.user_id != user.id or existing.source != "uhunt"):
                # An external submission cannot be awarded to a second Discord account.
                cursor = max(cursor, sub.submission_id)
                continue
            changed = existing is None or existing.verdict != sub.verdict
            submitted_at = datetime.fromtimestamp(sub.submission_time, tz=timezone.utc)
            if existing:
                existing.verdict = sub.verdict
                existing.runtime = sub.runtime
                existing.language = sub.language
                existing.status = "JUDGING" if sub.verdict == "In queue" else "FINISHED"
            else:
                existing = await SubmissionRepository.record_submission(
                    session, user.id, problem.id, sub.submission_id, sub.verdict,
                    runtime=sub.runtime, submitted_at=submitted_at,
                )
                existing.source = "uhunt"
                existing.language = sub.language
                existing.status = "JUDGING" if sub.verdict == "In queue" else "FINISHED"
            if sub.is_accepted:
                await SolvedRepository.record_solved(session, user.id, problem.id, submitted_at)
            # Initial/backfill imports are silent; do not flood DMs with historical results.
            if changed and not first_sync:
                attempts = await session.scalar(select(func.count(Submission.id)).where(
                    Submission.user_id == user.id, Submission.problem_id == problem.id,
                    Submission.source == "uhunt", Submission.external_submission_id.isnot(None),
                ))
                notifications.append(SubmissionNotification(
                    session_id=0, discord_user_id=user.discord_user_id,
                    problem_number=problem.problem_number, problem_title=problem.title,
                    submission_id=sub.submission_id, language=sub.language, verdict=sub.verdict,
                    display_verdict=sub.display_verdict, runtime=sub.runtime, attempts=attempts or 0,
                    is_accepted=sub.is_accepted, started_at=None,
                    solved_at=submitted_at if sub.is_accepted else None,
                ))
            cursor = max(cursor, sub.submission_id)
        await session.flush()
        return notifications, (key, cursor)
