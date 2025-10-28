# input/keyboard_input.py
import threading
import time

# (!!!) 기존 코드에서 사용하던 라이브러리를 여기에 추가하세요.
import sys
import termios
import tty
import select


class ManualInput(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True

        # 제어 값을 저장할 변수
        self.throttle = 0.0  # -1.0 (후진) ~ 1.0 (전진)
        self.steering = 0.0  # -1.0 (좌) ~ 1.0 (우)

        # --------------------------------------------------------
        # (!!!) 여기에 기존 코드의 '초기화' 부분을 붙여넣으세요.
        # 터미널을 non-blocking 모드로 설정하여 키 입력을 바로 읽을 수 있게 합니다.
        self._fd = sys.stdin.fileno()
        self._old_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        # --------------------------------------------------------
        print("[Input] 수동 조작 스레드 초기화 완료.")

    def _read_key(self):
        """논블로킹(non-blocking)으로 키 입력을 확인하고 문자를 반환합니다."""
        if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
            return sys.stdin.read(1)
        return None

    def run(self):
        """스레드가 시작되면 이 함수가 계속 반복 실행됩니다."""

        # --------------------------------------------------------
        # (!!!) 여기에 기존 코드의 '메인 루프(while True:)' 부분을 붙여넣으세요.
        # --------------------------------------------------------
        while self.running:
            key = self._read_key()

            if key:
                # 화살표 키 입력 처리 (ESC 시퀀스)
                if key == '\x1b':
                    key2 = self._read_key()
                    key3 = self._read_key()
                    if key2 == '[':
                        if key3 == 'A':  # 위쪽 화살표
                            self.throttle = 1.0
                        elif key3 == 'B':  # 아래쪽 화살표
                            self.throttle = -1.0
                        elif key3 == 'D':  # 왼쪽 화살표
                            self.steering = -1.0
                        elif key3 == 'C':  # 오른쪽 화살표
                            self.steering = 1.0
                
                # 정지 키: 's' 또는 스페이스바
                elif key in ('s', 'S', ' '):
                    self.throttle = 0.0
                    self.steering = 0.0
                
                # 비상 정지: 'x' (프로그램 종료는 main.py에서 처리)
                # 여기서는 차량을 즉시 멈추는 역할만 합니다.
                elif key in ('x', 'X'):
                    self.throttle = 0.0
                    self.steering = 0.0
                    print("[Input] 비상 정지 신호 감지!")
            
            # (중요) 루프 안에서 throttle과 steering 값을 계속 업데이트합니다.
            # 이 예제에서는 키를 누를 때만 값이 변경되고, 그 상태가 유지됩니다.

            time.sleep(0.02)  # 루프가 너무 빨리 돌지 않도록 약간의 대기시간 추가

        # --------------------------------------------------------
        # (!!!) 여기에 프로그램 종료 시 필요한 '정리'
