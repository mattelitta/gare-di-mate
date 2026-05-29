"""
Core scoring engine. All scores are computed dynamically from raw events.

Key rules:
- Problem value = initial_value + time_bonus + error_bonus (up to threshold_minute)
- Time bonus: +1/min while fewer than n teams solved it
- Error bonus: +2 per error, only first k errors per team count
- After threshold_minute: value frozen
- Correct answer: +current_value (dynamic — grows with problem)
- Wrong answer: -10 always (even after solving, even after threshold)
- First delivery bonus: fixed at time of correct submission order
- Full bonus: fixed when team completes all problems
- Jolly: x2 on all contributions for chosen problem
- Penalties: arbitrary additions
- Starting score: 10 x num_problems
- Post-game submissions: treated as game_seconds = duration_minutes * 60

Performance notes:
- Chiamata tipicamente da cache (cache.py), non ad ogni request
- Tutti i dati devono essere già caricati in memoria (eager loading via load_comp_full)
- Complessità O(S) dove S = numero consegne, grazie alla precomputazione
"""

from dataclasses import dataclass, field
from models import Competition


@dataclass
class ProblemState:
    problem_id: int
    number: int
    name: str
    value: float
    solvers: list[int]          # team_ids in ordine di soluzione corretta
    error_counts: dict[int, int] = field(default_factory=dict)  # team_id -> totale errori


@dataclass
class TeamScore:
    team_id: int
    number: int
    name: str
    city: str
    is_guest: bool
    total: float
    problem_contributions: dict[int, float]  # problem_id -> contributo netto
    problem_errors: dict[int, int]           # problem_id -> num errori
    problem_solved: dict[int, bool]          # problem_id -> risolto?
    jolly_problem_id: int | None
    full_bonus_earned: int
    penalty_total: int


def compute_state(
    comp: Competition,
    at_seconds: float | None = None,
) -> tuple[dict[int, ProblemState], dict[int, TeamScore]]:
    """
    Calcola lo stato completo della gara all'istante at_seconds.
    Se at_seconds è None, usa il tempo elapsed corrente.
    Richiede che comp abbia già tutte le relazioni caricate (eager loading).
    """
    if at_seconds is None:
        at_seconds = comp.elapsed_seconds()

    threshold_seconds = comp.threshold_minute * 60

    teams = {t.id: t for t in comp.teams}
    problems = {p.id: p for p in comp.problems}
    num_problems = len(problems)

    # Jolly: ultimo inserimento per squadra vince
    jolly_map: dict[int, int] = {}
    for jc in sorted(comp.jolly_choices, key=lambda x: x.submitted_at):
        jolly_map[jc.team_id] = jc.problem_id

    # Consegne ordinate per (game_seconds, submitted_at) — garantisce ordine corretto
    # anche per le consegne post-gara che hanno tutte lo stesso game_seconds
    submissions = sorted(
        (s for s in comp.submissions if s.game_seconds <= at_seconds),
        key=lambda s: (s.game_seconds, s.submitted_at),
    )

    # --- Passaggio unico O(S): costruisce tutte le strutture dati necessarie ---

    # Per ogni problema: errori per squadra (tutti), solutori ordinati
    prob_errors: dict[int, dict[int, int]] = {pid: {} for pid in problems}
    prob_solvers: dict[int, list[int]] = {pid: [] for pid in problems}
    prob_solver_set: dict[int, set[int]] = {pid: set() for pid in problems}

    # Errori PRIMA del minuto soglia, per squadra e problema — usati per il valore
    # Precomputati qui in O(S) per evitare loop annidati in problem_value
    errors_pre_threshold: dict[int, dict[int, int]] = {pid: {} for pid in problems}

    # Tempo (game_seconds) della n-esima soluzione corretta per ogni problema
    nth_solver_time: dict[int, float | None] = {pid: None for pid in problems}
    correct_count: dict[int, int] = {pid: 0 for pid in problems}

    for sub in submissions:
        pid = sub.problem_id
        tid = sub.team_id
        if pid not in problems:
            continue

        is_guest = teams[tid].is_guest if tid in teams else False

        if sub.is_correct:
            if tid not in prob_solver_set[pid]:
                prob_solver_set[pid].add(tid)
                prob_solvers[pid].append(tid)
                # Gli ospiti non contano verso n (non bloccano il bonus al minuto)
                if not is_guest:
                    correct_count[pid] += 1
                    if correct_count[pid] == comp.n and nth_solver_time[pid] is None:
                        nth_solver_time[pid] = sub.game_seconds
        else:
            # Errori contano sempre per il punteggio della squadra (-10)
            prob_errors[pid][tid] = prob_errors[pid].get(tid, 0) + 1
            # Gli ospiti non influenzano il valore del problema con i loro errori
            if not is_guest and sub.game_seconds <= threshold_seconds:
                errors_pre_threshold[pid][tid] = errors_pre_threshold[pid].get(tid, 0) + 1

    # --- Calcolo valore problema (O(1) per problema grazie alla precomputazione) ---

    def problem_value(pid: int) -> float:
        effective_t = min(at_seconds, threshold_seconds)

        # Il bonus al minuto si blocca al minuto soglia O quando l'n-esima squadra risolve
        nth_t = nth_solver_time[pid]
        time_t = min(effective_t, nth_t) if nth_t is not None else effective_t
        time_bonus = time_t / 60.0

        # Bonus errori: primi k errori pre-soglia per squadra, ognuno vale +2
        error_bonus = sum(
            min(err_count, comp.k) * 2
            for err_count in errors_pre_threshold[pid].values()
        )

        return comp.initial_value + time_bonus + error_bonus

    # Precalcola tutti i valori una volta sola
    prob_values = {pid: problem_value(pid) for pid in problems}

    # --- Bonus prima consegna ---
    # Ospiti e non-ospiti hanno contatori separati:
    # - non-ospiti: posizione tra i soli non-ospiti (non "occupano" un posto agli ospiti)
    # - ospiti: posizione assoluta nell'ordine di consegna
    # Esempio: sq1 → ospite → sq2 → bonus[0], bonus[1], bonus[1]
    fd_bonuses = comp.first_delivery_bonuses
    first_delivery_bonus_map: dict[int, dict[int, int]] = {pid: {} for pid in problems}
    for pid, solvers in prob_solvers.items():
        non_guest_idx = 0
        for abs_idx, tid in enumerate(solvers):
            is_guest = teams[tid].is_guest if tid in teams else False
            if is_guest:
                if abs_idx < len(fd_bonuses):
                    first_delivery_bonus_map[pid][tid] = fd_bonuses[abs_idx]
            else:
                if non_guest_idx < len(fd_bonuses):
                    first_delivery_bonus_map[pid][tid] = fd_bonuses[non_guest_idx]
                non_guest_idx += 1

    # --- Bonus full ---
    # Stessa logica del bonus prima consegna: ospiti usano posizione assoluta,
    # non-ospiti usano posizione tra i soli non-ospiti.
    full_bonus_map: dict[int, int] = {}
    if num_problems > 0:
        # Per ogni squadra che ha risolto tutto, trova il momento dell'ultima soluzione
        completions: list[tuple[float, float, int]] = []  # (game_sec, wall_ts, team_id)
        for tid in teams:
            if all(tid in prob_solver_set[pid] for pid in problems):
                last_t = 0.0
                last_wall = 0.0
                for sub in submissions:
                    if sub.team_id == tid and sub.is_correct and sub.problem_id in problems:
                        wall = sub.submitted_at.timestamp()
                        if (sub.game_seconds, wall) > (last_t, last_wall):
                            last_t = sub.game_seconds
                            last_wall = wall
                completions.append((last_t, last_wall, tid))
        completions.sort()
        full_bonuses = comp.full_bonuses
        non_guest_idx = 0
        for abs_idx, (_, _, tid) in enumerate(completions):
            is_guest = teams[tid].is_guest if tid in teams else False
            if is_guest:
                if abs_idx < len(full_bonuses):
                    full_bonus_map[tid] = full_bonuses[abs_idx]
            else:
                if non_guest_idx < len(full_bonuses):
                    full_bonus_map[tid] = full_bonuses[non_guest_idx]
                non_guest_idx += 1

    # --- Penalizzazioni ---
    penalty_map: dict[int, int] = {}
    for pen in comp.penalties:
        penalty_map[pen.team_id] = penalty_map.get(pen.team_id, 0) + pen.value

    # --- Assemblaggio punteggi squadre ---
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
            multiplier = 2 if jolly_pid == pid else 1

            if solved:
                val = prob_values[pid]
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
            full_bonus_earned=full_bonus,
            penalty_total=penalty,
        )

    # --- Stato problemi ---
    problem_states: dict[int, ProblemState] = {
        pid: ProblemState(
            problem_id=pid,
            number=prob.number,
            name=prob.name,
            value=prob_values[pid],
            solvers=prob_solvers[pid],
            error_counts=prob_errors[pid],
        )
        for pid, prob in problems.items()
    }

    return problem_states, team_scores


def rank_teams(team_scores: dict[int, TeamScore], comp: Competition) -> list[TeamScore]:
    """
    Ordina le squadre per classifica:
    1. Ospiti sempre in fondo (ordinati tra loro per punteggio decrescente)
    2. Non-ospiti per punteggio decrescente
    3. Spareggi: contributo jolly, poi valore singole risposte corrette (decrescente)
    """
    non_guests = [ts for ts in team_scores.values() if not ts.is_guest]
    guests = [ts for ts in team_scores.values() if ts.is_guest]

    def sort_key(ts: TeamScore):
        jolly_contrib = (
            ts.problem_contributions.get(ts.jolly_problem_id, 0.0)
            if ts.jolly_problem_id else 0.0
        )
        solved_vals = sorted(
            [v for pid, v in ts.problem_contributions.items() if ts.problem_solved.get(pid)],
            reverse=True,
        )
        return (ts.total, jolly_contrib, solved_vals)

    non_guests.sort(key=sort_key, reverse=True)
    guests.sort(key=sort_key, reverse=True)
    return non_guests + guests
