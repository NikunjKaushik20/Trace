from dataclasses import dataclass


@dataclass
class CUSUMState:
    state: float = 0.0
    fired: bool = False


EMA_ALPHA = 0.3
CUSUM_MU_0 = 0.1
CUSUM_K = 0.25
CUSUM_H = 4.0
CUSUM_PENALTY = 0.4


def update_ema_default_rate(default_flag: int, prev_ema: float) -> float:
    return EMA_ALPHA * default_flag + (1 - EMA_ALPHA) * prev_ema


def update_cusum(default_flag: int, prev_state: float) -> CUSUMState:
    increment = default_flag - CUSUM_MU_0 - CUSUM_K
    new_state = max(0.0, prev_state + increment)
    fired = new_state >= CUSUM_H
    if fired:
        new_state = 0.0
    return CUSUMState(state=new_state, fired=fired)


def compute_default_risk(ema_default_rate: float, cusum_fired: bool) -> float:
    penalty = CUSUM_PENALTY if cusum_fired else 0.0
    return min(1.0, ema_default_rate + penalty)


def process_default_sequence(default_sequence: list[int], initial_ema: float, initial_cusum: float) -> tuple[float, float, bool]:
    ema = initial_ema
    cusum_state = initial_cusum
    cusum_fired = False
    
    for flag in default_sequence:
        ema = update_ema_default_rate(flag, ema)
        cusum_result = update_cusum(flag, cusum_state)
        cusum_state = cusum_result.state
        if cusum_result.fired:
            cusum_fired = True
    
    return ema, cusum_state, cusum_fired