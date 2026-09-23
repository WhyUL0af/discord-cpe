from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.problem import Problem
from app.providers.problem_provider import ProblemData


class ProblemRepository:
    @staticmethod
    async def get_by_number(session: AsyncSession, problem_number: int) -> Optional[Problem]:
        stmt = select(Problem).where(Problem.problem_number == problem_number)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_uhunt_pid(session: AsyncSession, uhunt_pid: int) -> Optional[Problem]:
        stmt = select(Problem).where(Problem.uhunt_pid == uhunt_pid)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(session: AsyncSession, problem_id: int) -> Optional[Problem]:
        stmt = select(Problem).where(Problem.id == problem_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_from_data(session: AsyncSession, data: ProblemData) -> Problem:
        problem = await ProblemRepository.get_by_number(session, data.problem_number)
        if not problem:
            problem = Problem(
                problem_number=data.problem_number,
                title=data.title,
                difficulty=data.difficulty,
                uhunt_pid=data.uhunt_pid,
                source=data.source,
                external_url=data.external_url,
                time_limit=data.time_limit,
            )
            session.add(problem)
            await session.flush()
        else:
            # Update fields if new info is available
            if data.title and problem.title != data.title:
                problem.title = data.title
            if data.difficulty and not problem.difficulty:
                problem.difficulty = data.difficulty
            if data.uhunt_pid and not problem.uhunt_pid:
                problem.uhunt_pid = data.uhunt_pid
            if data.external_url and not problem.external_url:
                problem.external_url = data.external_url
            if data.time_limit and not problem.time_limit:
                problem.time_limit = data.time_limit
            await session.flush()
        return problem

    @staticmethod
    async def get_all(session: AsyncSession) -> List[Problem]:
        stmt = select(Problem).order_by(Problem.problem_number)
        result = await session.execute(stmt)
        return list(result.scalars().all())
