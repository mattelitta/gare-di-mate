"""
Core scoring engine. All scores are computed dynamically from raw events.

Key rules:
- Problem value = initial_value + time_bonus + error_bonus (up to threshold_minute)
- Time bonus: +1/min while fewer than n teams solved it
- Error bonus: +2 per error, only first k errors per team count
- After threshold_minute: value frozen
- Correct answer: +current_value (dynamic — grows with problem)
- Wrong answer: -10 always (even after solving, even after threshold)
- First delivery bonus: fixed at time of correct submission
- Full bonus: fixed when team completes all problems
- Jolly: ×2 on all contributions for chosen problem
- Penalties: arbitrary additions
- Starting score: 10 × num_problems
- Post-game submissions: treated as game_seconds = duration_minutes * 60
"""

from dataclasses import dataclass, field
from models import Competition, Submission, JollyChoice, Penalty, Team, Problem


@dataclass
class ProblemState:
    problem_id: int
    number: int
    name: str
    value: float          # current dynamic value
    solvers: list[int]    # team_ids in order of correct submission
    error_counts: dict[int, int] = field(default_factory=dict)  # team_id -> total errors


@dataclass
class TeamScore:
    team_id: int
    number: int
    name: str
    city: str
    is_guest: bool
    total: float
    problem_contributions: dict[int, float]   # problem_id -> net contribution
    problem_errors: dict[int, int]            # problem_id -> num errors
    problem_solved: dict[int, bool]           # problem_id -> solved?
    jolly_problem_id: int | None
    first_delivery_bonuses_earned: dict[int, int]   # problem_id -> bonus value
    full_bonus_earned: int                          # 0 if not earned
    penalty_total: int


def compute_state(comp: Competition, at_seconds: float | None = None) -> tuple[dict[int, ProblemState], dict[int, TeamScore]]:
    """
    Compute the full game state at a given game-time (seconds).
    If at_seconds is None, uses current elapsed time.
    Returns (problem_states, team_scores).
    """
    if at_seconds is None:
        at_seconds = comp.elapsed_seconds()

    threshold_seconds = comp.threshold_minute * 60
    duration_seconds = comp.duration_minutes * 60

    teams = {t.id: t for t in comp.teams}
    problems = {p.id: p for p in comp.problems}
    num_problems = len(problems)

    # Build jolly map: team_id -> problem_id (last choice wins if multiple)
    jolly_map: dict[int, int] = {}
    for jc in sorted(comp.jolly_choices, key=lambda x: x.submitted_at):
        jolly_map[jc.team_id] = jc.problem_id

    # Sort submissions by game_seconds, then submitted_at (for post-game ordering)
    submissions = sorted(comp.submissions, key=lambda s: (s.game_seconds, s.submitted_at))

    # Filter to submissions that occurred at or before at_seconds
    submissions = [s for s in submissions if s.game_seconds <= at_seconds]

    # --- Build problem states ---
    # Track: for each problem, errors per team (for value calc), and correct submissions in order
    prob_errors: dict[int, dict[int, int]] = {pid: {} for pid in problems}
    prob_solvers: dict[int, list[int]] = {pid: [] for pid in problems}  # ordered team_ids
    # Track which teams have solved each problem (for value calc)
    prob_solver_set: dict[int, set[int]] = {pid: set() for pid in problems}

    # We need to replay submissions to compute problem values at each moment
    # because value at time of correct answer depends on errors/solvers up to that point.
    # We also need the value to grow for teams that solved before n solvers.

    # Strategy:
    # 1. Replay all submissions in order, tracking error counts and solver order.
    # 2. For each problem, compute its value at any given game_second:
    #    value(t) = initial + time_contribution(t) + error_contribution(t)
    # 3. Team's score from a problem = value(current_t) if solved (dynamic),
    #    so we don't fix it at submission time.

    # First pass: collect all events per problem
    for sub in submissions:
        pid = sub.problem_id
        tid = sub.team_id
        if pid not in prob_errors:
            continue
        if not sub.is_correct:
            prob_errors[pid][tid] = prob_errors[pid].get(tid, 0) + 1
            if tid not in prob_solver_set[pid]:
                pass  # errors after solve still count toward k (per spec)
        else:
            if tid not in prob_solver_set[pid]:
                prob_solver_set[pid].add(tid)
                prob_solvers[pid].append(tid)

    # Compute current problem value at at_seconds
    def problem_value(pid: int) -> float:
        p_errors = prob_errors[pid]
        n_solvers = len(prob_solvers[pid])

        # Time bonus: +1/min while fewer than n teams solved it, up to threshold
        effective_t = min(at_seconds, threshold_seconds)
        # We need to find when the nth solver submitted to stop time bonus
        nth_solver_t = None
        if n_solvers >= comp.n:
            # find game_seconds of the nth correct submission for this problem
            correct_subs = [s for s in submissions if s.problem_id == pid and s.is_correct]
            correct_subs_ordered = sorted(correct_subs, key=lambda s: (s.game_seconds, s.submitted_at))
            if len(correct_subs_ordered) >= comp.n:
                nth_solver_t = correct_subs_ordered[comp.n - 1].game_seconds

        if nth_solver_t is not None:
            time_t = min(effective_t, nth_solver_t)
        else:
            time_t = effective_t

        time_bonus = time_t / 60.0  # +1 per minute

        # Error bonus: first k errors per team, up to threshold
        error_bonus = 0
        for tid, err_count in p_errors.items():
            # count errors that happened before threshold
            team_errors_before_threshold = _count_errors_before(submissions, pid, tid, threshold_seconds)
            contributing = min(team_errors_before_threshold, comp.k)
            error_bonus += contributing * 2

        return comp.initial_value + time_bonus + error_bonus

    def _count_errors_before(subs, pid, tid, t_limit):
        count = 0
        for s in subs:
            if s.problem_id == pid and s.team_id == tid and not s.is_correct:
                if s.game_seconds <= t_limit:
                    count += 1
        return count

    # --- First delivery bonuses ---
    # For each problem, assign bonus to solvers in order
    first_delivery_bonus_map: dict[int, dict[int, int]] = {pid: {} for pid in problems}
    fd_bonuses = comp.first_delivery_bonuses
    for pid, solvers in prob_solvers.items():
        for i, tid in enumerate(solvers):
            if i < len(fd_bonuses):
                first_delivery_bonus_map[pid][tid] = fd_bonuses[i]

    # --- Full bonus ---
    # Teams that solved all problems, in order of completing the last problem
    full_bonus_map: dict[int, int] = {}
    if num_problems > 0:
        # For each team, find when they solved their last problem
        team_completion_times: list[tuple[float, int, int]] = []  # (game_sec, submitted_at_ts, team_id)
        for tid in teams:
            solved_problems = {pid for pid in problems if tid in prob_solver_set[pid]}
            if len(solved_problems) == num_problems:
                # Find game_seconds of last solve
                last_t = 0.0
                last_wall = 0
                for sub in submissions:
                    if sub.team_id == tid and sub.is_correct and sub.problem_id in problems:
                        if (sub.game_seconds, sub.submitted_at.timestamp()) > (last_t, last_wall):
                            last_t = sub.game_seconds
                            last_wall = sub.submitted_at.timestamp()
                team_completion_times.append((last_t, last_wall, tid))
        team_completion_times.sort()
        full_bonuses = comp.full_bonuses
        for i, (_, _, tid) in enumerate(team_completion_times):
            if i < len(full_bonuses):
                full_bonus_map[tid] = full_bonuses[i]

    # --- Penalties ---
    penalty_map: dict[int, int] = {}
    for p in comp.penalties:
        penalty_map[p.team_id] = penalty_map.get(p.team_id, 0) + p.value

    # --- Assemble team scores ---
    starting = 10 * num_problems
    team_scores: dict[int, TeamScore] = {}

    for tid, team in teams.items():
        jolly_pid = jolly_map.get(tid)
        prob_contributions: dict[int, float] = {}
        prob_errors_out: dict[int, int] = {}
        prob_solved_out: dict[int, bool] = {}

        for pid in problems:
            errors = prob_errors[pid].get(tid, 0)
            solved = tid in prob_solver_set[pid]
            is_jolly = jolly_pid == pid
            multiplier = 2 if is_jolly else 1

            if solved:
                val = problem_value(pid)
                fd_bonus = first_delivery_bonus_map[pid].get(tid, 0)
                contribution = (val + fd_bonus - 10 * errors) * multiplier
            else:
                contribution = -10 * errors * multiplier

            prob_contributions[pid] = contribution
            prob_errors_out[pid] = errors
            prob_solved_out[pid] = solved

        full_bonus = full_bonus_map.get(tid, 0)
        penalty = penalty_map.get(tid, 0)
        total = starting + sum(prob_contributions.values()) + full_bonus + penalty

        team_scores[tid] = TeamScore(
            team_id=tid,
            number=team.number,
            name=team.name,
            city=team.city,
            is_guest=team.is_guest,
            total=total,
            problem_contributions=prob_contributions,
            problem_errors=prob_errors_out,
            problem_solved=prob_solved_out,
            jolly_problem_id=jolly_pid,
            first_delivery_bonuses_earned=first_delivery_bonus_map,
            full_bonus_earned=full_bonus,
            penalty_total=penalty,
        )

    problem_states: dict[int, ProblemState] = {}
    for pid, prob in problems.items():
        problem_states[pid] = ProblemState(
            problem_id=pid,
            number=prob.number,
            name=prob.name,
            value=problem_value(pid),
            solvers=prob_solvers[pid],
            error_counts=prob_errors[pid],
        )

    return problem_states, team_scores


def rank_teams(team_scores: dict[int, TeamScore], comp: Competition) -> list[TeamScore]:
    """
    Sort teams by ranking rules:
    1. Guests always last (among themselves sorted by total desc)
    2. Non-guests sorted by total desc
    3. Tiebreak: jolly problem contribution desc, then highest single correct answer value desc
    """
    non_guests = [ts for ts in team_scores.values() if not ts.is_guest]
    guests = [ts for ts in team_scores.values() if ts.is_guest]

    def sort_key(ts: TeamScore):
        jolly_contrib = 0.0
        if ts.jolly_problem_id and ts.jolly_problem_id in ts.problem_contributions:
            jolly_contrib = ts.problem_contributions[ts.jolly_problem_id]
        # For tiebreak 2+: sorted contributions of solved problems desc
        solved_vals = sorted(
            [v for pid, v in ts.problem_contributions.items() if ts.problem_solved.get(pid, False)],
            reverse=True
        )
        return (ts.total, jolly_contrib, solved_vals)

    non_guests.sort(key=sort_key, reverse=True)
    guests.sort(key=sort_key, reverse=True)
    return non_guests + guests


def problem_value_at(comp: Competition, problem_id: int, at_seconds: float) -> float:
    """Compute value of a single problem at a given game time."""
    prob_states, _ = compute_state(comp, at_seconds)
    if problem_id in prob_states:
        return prob_states[problem_id].value
    return float(comp.initial_value)
