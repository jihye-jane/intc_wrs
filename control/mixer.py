# -*- coding: utf-8 -*-

def mix_skid(throttle: float, turn: float) -> tuple[float, float]:
    """
    스키드 스티어링을 위해 throttle과 turn 값을 왼쪽/오른쪽 모터 속도로 변환합니다.
    출력 값은 항상 -1.0과 1.0 사이로 정규화됩니다.
    """
    # [수정] 들여쓰기에 사용된 특수 공백 문자를 일반 공백으로 변경했습니다.
    l = throttle + turn
    r = throttle - turn

    # 계산된 값이 1.0을 초과하는 경우를 대비해 정규화 인수를 찾습니다.
    m = max(1.0, abs(l), abs(r))

    # 정규화하여 최종 모터 속도를 반환합니다.
    return l / m, r / m