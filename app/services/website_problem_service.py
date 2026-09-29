"""Public problem projection deliberately excludes judge test cases."""
from fastapi import HTTPException
from app.repositories.problem_repo import ProblemRepository
from app.repositories.solved_repo import SolvedRepository


def public_problem(problem, solved=False):
    return {"id": problem.id, "problem_number": problem.problem_number, "title": problem.title,
            "difficulty": problem.difficulty, "source": problem.source, "solved": solved,
            "description": problem.statement, "input_description": problem.input_description,
            "output_description": problem.output_description,
            "sample_input": problem.sample_input, "sample_output": problem.sample_output,
            "time_limit_ms": problem.time_limit, "memory_limit_kb": problem.memory_limit,
            "external_url": problem.external_url}


class WebsiteProblemService:
    @staticmethod
    async def get(session, problem_id):
        problem = await ProblemRepository.get_by_id(session, problem_id)
        if not problem:
            raise HTTPException(404, "找不到題目")
        return problem

    @staticmethod
    async def search(session, user_id=None, **filters):
        solved = filters.get("solved", "")
        if solved not in {"", "solved", "unsolved"}:
            raise HTTPException(422, "無效的完成狀態篩選")
        if solved and user_id is None:
            raise HTTPException(401, "請先登入才能篩選個人完成狀態")
        items = await ProblemRepository.search(session, user_id, **filters)
        solved_ids = {row.problem_id for row in await SolvedRepository.get_user_solved_problems(session, user_id)} if user_id else set()
        return [public_problem(p, p.id in solved_ids) for p in items]
