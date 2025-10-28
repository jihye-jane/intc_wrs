# -*- coding: utf-8 -*-
import sys
import termios
import tty
import select
# 'constants' 모듈이 별도의 constants.py 파일에 정의되어 있다고 가정합니다.
from constants import (
    EVENT_SYS, EVENT_CMD,
    ACTION_E_STOP, ACTION_SET_MODE,
    ACTION_INC_SPEED, ACTION_DEC_SPEED, ACTION_STEER_LEFT, ACTION_STEER_RIGHT, ACTION_STOP,
    MODE_BUTTON, MODE_JOYSTICK
)

class KeyboardInput:
    def __init__(self):
        self._fd = sys.stdin.fileno()
        self._old = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        self.is_connected = True

    # [수정 1] 메서드 이름을 __del__ 로 변경
    def __del__(self):
        self.close()

    def close(self):
        try:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)
        except Exception:
            pass

    def _read_key(self):
        # select.select를 사용하여 논블로킹(non-blocking)으로 키 입력을 확인
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    def poll(self):
        events = []
        key = self._read_key()
        if not key:
            return events

        # 모드 전환: '1' 키보드, '2' 조이스틱
        if key == '1':
            events.append({"type": EVENT_SYS, "action": ACTION_SET_MODE, "mode": MODE_BUTTON})
        elif key == '2':
            events.append({"type": EVENT_SYS, "action": ACTION_SET_MODE, "mode": MODE_JOYSTICK})

        # 비상정지: 'x' 또는 'X'
        if key in ('x', 'X'):
            events.append({"type": EVENT_SYS, "action": ACTION_E_STOP})
            return events # 비상정지 시 다른 이벤트 처리를 중단하고 즉시 반환

        # 속도/조향 (화살표 키)
        if key == '\x1b':  # 화살표 키의 시작을 나타내는 ESC 문자
            # 이스케이프 시퀀스의 나머지 부분을 읽음
            key2 = self._read_key()
            key3 = self._read_key()
            if key2 == '[' and key3:
                if key3 == 'A':  # 위쪽 화살표
                    events.append({"type": EVENT_CMD, "action": ACTION_INC_SPEED})
                elif key3 == 'B': # 아래쪽 화살표
                    events.append({"type": EVENT_CMD, "action": ACTION_DEC_SPEED})
                elif key3 == 'D': # 왼쪽 화살표
                    events.append({"type": EVENT_CMD, "action": ACTION_STEER_LEFT})
                elif key3 == 'C': # 오른쪽 화살표
                    events.append({"type": EVENT_CMD, "action": ACTION_STEER_RIGHT})

        # 정지: 스페이스바
        if key == ' ':
            events.append({"type": EVENT_CMD, "action": ACTION_STOP})

        # 정지: 's' 또는 'S'
        if key in ('s', 'S'):
            events.append({"type": EVENT_CMD, "action": ACTION_STOP})

        return events