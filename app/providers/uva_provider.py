import logging
from typing import Any, Dict, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class UvaApiException(Exception):
    """Base exception for uHunt / UVa API errors."""
    pass


class UvaUserNotFoundException(UvaApiException):
    """Raised when a UVa user does not exist on uHunt."""
    pass


class UvaTimeoutException(UvaApiException):
    """Raised when uHunt API requests time out."""
    pass


class UvaProvider:
    """Provider for interacting with the uHunt (UVa Online Judge) API."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None) -> None:
        self.base_url = (base_url or settings.UHUNT_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.UHUNT_TIMEOUT_SECONDS

    async def _get(self, endpoint: str) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        max_retries = 3
        backoff = 1.0

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    return response.json()
            except httpx.TimeoutException as exc:
                logger.warning(
                    f"uHunt API timeout for {url} (attempt {attempt}/{max_retries}): {exc}"
                )
                if attempt == max_retries:
                    raise UvaTimeoutException(f"uHunt API request timed out after {max_retries} attempts.")
            except httpx.HTTPStatusError as exc:
                logger.error(f"uHunt API HTTP error {exc.response.status_code} for {url}: {exc}")
                if attempt == max_retries or exc.response.status_code < 500:
                    raise UvaApiException(f"uHunt API returned status code {exc.response.status_code}")
            except httpx.RequestError as exc:
                logger.error(f"uHunt API connection error for {url} (attempt {attempt}/{max_retries}): {exc}")
                if attempt == max_retries:
                    raise UvaApiException(f"Failed to connect to uHunt API: {exc}")
            
            # Simple async backoff if retrying
            import asyncio
            await asyncio.sleep(backoff)
            backoff *= 2.0

        raise UvaApiException("uHunt API unreachable.")

    async def get_user_id(self, username: str) -> Optional[int]:
        """Convert UVa username to uHunt user ID.

        Returns:
            int user ID if found, None if username does not exist.
        """
        try:
            result = await self._get(f"uname2uid/{username.strip()}")
            if isinstance(result, int) and result > 0:
                return result
            # Some versions return string or 0
            if str(result).isdigit() and int(result) > 0:
                return int(result)
            return None
        except UvaTimeoutException:
            raise
        except Exception as e:
            logger.error(f"Error fetching UID for username '{username}': {e}")
            raise UvaApiException(f"Failed to verify UVa username: {e}")

    async def get_user_profile(self, uva_user_id: int) -> Dict[str, Any]:
        """Fetch user ranking and solving statistics from uHunt.

        API endpoint: /api/ranklist/{uid}/0/0
        """
        try:
            result = await self._get(f"ranklist/{uva_user_id}/0/0")
            if not result or not isinstance(result, list) or len(result) == 0:
                raise UvaUserNotFoundException(f"No ranklist entry found for UID {uva_user_id}")

            data = result[0]
            solved = int(data.get("ac", 0))
            submissions = int(data.get("nos", 0))
            ac_rate = (solved / submissions * 100.0) if submissions > 0 else 0.0

            return {
                "user_id": uva_user_id,
                "username": data.get("username", ""),
                "name": data.get("name", ""),
                "rank": data.get("rank"),
                "solved": solved,
                "submissions": submissions,
                "ac_rate": round(ac_rate, 1),
            }
        except (UvaTimeoutException, UvaUserNotFoundException):
            raise
        except Exception as e:
            logger.error(f"Error fetching profile for UID '{uva_user_id}': {e}")
            raise UvaApiException(f"Failed to fetch UVa user profile: {e}")
