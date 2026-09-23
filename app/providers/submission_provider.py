import logging
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# uHunt Verdict IDs mapping
# http://uhunt.onlinejudge.org/api
VERDICT_MAP = {
    10: "Submission error",
    15: "Can't be judged",
    20: "In queue",
    30: "Compilation Error",
    35: "Restricted function",
    40: "Runtime Error",
    45: "Output Limit Exceeded",
    50: "Time Limit Exceeded",
    60: "Memory Limit Exceeded",
    70: "Wrong Answer",
    80: "Presentation Error",
    90: "Accepted",
}

VERDICT_DISPLAY_MAP = {
    "Accepted": "✅ Accepted",
    "Wrong Answer": "❌ Wrong Answer",
    "Time Limit Exceeded": "⏱ Time Limit Exceeded",
    "Compilation Error": "🛠 Compilation Error",
    "Runtime Error": "💥 Runtime Error",
    "Memory Limit Exceeded": "💾 Memory Limit Exceeded",
    "Output Limit Exceeded": "📄 Output Limit Exceeded",
    "Presentation Error": "📝 Presentation Error",
    "In queue": "⏳ In Queue / Judging...",
}


class SubmissionData:
    def __init__(
        self,
        submission_id: int,
        uhunt_pid: int,
        verdict_id: int,
        runtime: int,
        submission_time: int,
        language_id: int,
    ) -> None:
        self.submission_id = submission_id
        self.uhunt_pid = uhunt_pid
        self.verdict_id = verdict_id
        self.verdict = VERDICT_MAP.get(verdict_id, f"Unknown ({verdict_id})")
        self.runtime = runtime
        self.submission_time = submission_time
        self.language_id = language_id

    @property
    def is_accepted(self) -> bool:
        return self.verdict == "Accepted"

    @property
    def display_verdict(self) -> str:
        return VERDICT_DISPLAY_MAP.get(self.verdict, f"❓ {self.verdict}")


class SubmissionProvider:
    """Fetches user submissions and parses verdicts from uHunt."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None) -> None:
        self.base_url = (base_url or settings.UHUNT_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.UHUNT_TIMEOUT_SECONDS

    async def get_latest_submission_id(self, uva_user_id: int) -> int:
        """Fetch the most recent submission ID for a user.

        Used when starting a problem session to ignore historical submissions.
        """
        url = f"{self.base_url}/subs-user-last/{uva_user_id}/1"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.get(url)
                if res.status_code != 200:
                    return 0
                data = res.json()
                subs = data.get("subs", [])
                if subs and len(subs) > 0:
                    return int(subs[0][0])
                return 0
        except Exception as e:
            logger.warning(f"Failed to fetch latest submission ID for UID {uva_user_id}: {e}")
            return 0

    async def get_user_submissions_since(
        self,
        uva_user_id: int,
        min_sub_id: int
    ) -> List[SubmissionData]:
        """Fetch all submissions for a user that occurred after min_sub_id."""
        url = f"{self.base_url}/subs-user/{uva_user_id}/{min_sub_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.get(url)
                if res.status_code != 200:
                    logger.warning(f"uHunt subs-user returned {res.status_code} for UID {uva_user_id}")
                    return []
                data = res.json()
                subs = data.get("subs", [])
                results: List[SubmissionData] = []
                for sub in subs:
                    # sub: [sub_id, pid, ver, run, s_time, lang, rank]
                    if len(sub) >= 6:
                        results.append(
                            SubmissionData(
                                submission_id=int(sub[0]),
                                uhunt_pid=int(sub[1]),
                                verdict_id=int(sub[2]),
                                runtime=int(sub[3]),
                                submission_time=int(sub[4]),
                                language_id=int(sub[5]),
                            )
                        )
                # Sort ascending by submission ID so events process chronologically
                results.sort(key=lambda s: s.submission_id)
                return results
        except httpx.TimeoutException:
            logger.warning(f"Timeout querying submissions for UID {uva_user_id}")
            return []
        except Exception as e:
            logger.error(f"Error querying submissions for UID {uva_user_id}: {e}")
            return []
