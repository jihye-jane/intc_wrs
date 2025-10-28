# input/manual_input.py
import threading
import time
import sys
import os
import struct
import array

# 운영체제에 따라 필요한 라이브러리가 다를 수 있습니다.
# 이 코드는 리눅스 환경을 기준으로 작성되었습니다.
try:
    import termios
    import tty
    import select
    import fcntl
    IS_LINUX = True
except ImportError:
    IS_LINUX = False
    print("[Input] 경고: 리눅스 전용 라이브러리(termios, tty, fcntl)를 찾을 수 없습니다.")
    print("[Input] 키보드 및 조이스틱 입력이 작동하지 않을 수 있습니다.")


# --- 조이스틱 관련 상수 및 헬퍼 함수 ---
# (!!!) 실제 프로젝트에서는 이 값들을 constants.py 같은 별도 파일에서 가져오세요.
THROTTLE_AXIS_NAME = 'y'  # 스로틀(전/후진)에 사용할 조이스틱 축 이름
STEER_AXIS_NAME = 'rx'    # 조향(좌/우)에 사용할 조이스틱 축 이름
DEADZONE = 0.08           # 조이스틱의 민감도를 조절하기 위한 데드존

# 조이스틱 이벤트 타입
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80

# 조이스틱 축/버튼 이름 맵
AXIS_NAMES = {
    0x00: 'x', 0x01: 'y', 0x02: 'z', 0x03: 'rx', 0x04: 'ry', 0x05: 'rz',
    0x06: 'throttle', 0x07: 'rudder', 0x08: 'wheel', 0x09: 'gas', 0x0A: 'brake',
    0x10: 'hat0x', 0x11: 'hat0y',
}
BUTTON_NAMES = {
    0x130: 'a', 0x131: 'b', 0x133: 'x', 0x134: 'y',
}

def norm_axis(value):
    """조이스틱 축 값을 -1.0 ~ 1.0 범위로 정규화합니다."""
    return value / 32767.0

def apply_deadzone(value, deadzone=DEADZONE):
    """데드존을 적용하여 작은 움직임을 무시합니다."""
    return value if abs(value) > deadzone else 0.0


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
        # --------------------------------------------------------
        self.joystick_connected = False
        self.keyboard_active = False

        if IS_LINUX:
            self._init_joystick()
            self._init_keyboard()
        else:
            print("[Input] 수동 조작을 위한 환경이 아니므로 스레드를 시작하지 않습니다.")
            self.running = False # 스레드 실행 방지

        print("[Input] 수동 조작 스레드 초기화 완료.")

    def _init_joystick(self):
        """조이스틱 장치를 찾아 초기화합니다."""
        dev_path = None
        try:
            for fn in sorted(os.listdir('/dev/input')):
                if fn.startswith('js'):
                    dev_path = f'/dev/input/{fn}'
                    break
        except FileNotFoundError:
            print("[Input] 조이스틱 장치를 찾을 수 없습니다. (디렉토리 없음)")
            return

        if not dev_path:
            print("[Input] 연결된 조이스틱이 없습니다. 키보드 입력을 사용합니다.")
            return

        try:
            self.jsdev = open(dev_path, 'rb', buffering=0)
            
            # 축(axis) 정보 가져오기
            buf = array.array('B', [0])
            fcntl.ioctl(self.jsdev, 0x80016a11, buf) # JSIOCGAXES
            num_axes = buf[0]
            self.axis_map = []
            buf = array.array('B', [0] * 0x40)
            fcntl.ioctl(self.jsdev, 0x80406a32, buf) # JSIOCGAXMAP
            for axis_code in buf[:num_axes]:
                self.axis_map.append(AXIS_NAMES.get(axis_code, 'unknown'))
            
            # 논블로킹 모드 설정
            flags = fcntl.fcntl(self.jsdev, fcntl.F_GETFL)
            fcntl.fcntl(self.jsdev, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            self.axis_states = {name: 0.0 for name in self.axis_map}
            self.joystick_connected = True
            print(f"[Input] 조이스틱 '{dev_path}' 연결 성공!")

        except (OSError, FileNotFoundError) as e:
            print(f"[Input] 조이스틱 초기화 실패: {e}. 키보드 입력을 사용합니다.")
            self.joystick_connected = False

    def _init_keyboard(self):
        """키보드 입력을 위한 터미널 설정을 초기화합니다."""
        try:
            self._fd = sys.stdin.fileno()
            self._old_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
            self.keyboard_active = True
        except (termios.error, AttributeError) as e:
            print(f"[Input] 키보드 초기화 실패: {e}. 터미널 환경이 아닐 수 있습니다.")
            self.keyboard_active = False

    def run(self):
        """스레드가 시작되면 이 함수가 계속 반복 실행됩니다."""
        while self.running:
            if self.joystick_connected:
                self._poll_joystick()
            elif self.keyboard_active:
                self._poll_keyboard()

            time.sleep(0.02) # 루프가 너무 빨리 돌지 않도록 약간의 대기시간 추가
        
        # --------------------------------------------------------
        # (!!!) 여기에 프로그램 종료 시 필요한 '정리' 코드를 넣으세요.
        # --------------------------------------------------------
        if self.keyboard_active:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
            print("[Input] 터미널 설정 복원 완료.")
        if self.joystick_connected:
            self.jsdev.close()
            print("[Input] 조이스틱 장치 연결 해제.")

    def _poll_joystick(self):
        """조이스틱 입력을 읽어 throttle과 steering 값을 업데이트합니다."""
        try:
            while True: # 버퍼에 쌓인 모든 이벤트를 처리
                evbuf = self.jsdev.read(8)
                t_ms, value, etype, number = struct.unpack('IhBB', evbuf)

                if (etype & ~JS_EVENT_INIT) == JS_EVENT_AXIS:
                    if number < len(self.axis_map):
                        axis_name = self.axis_map[number]
                        self.axis_states[axis_name] = norm_axis(value)

        except BlockingIOError:
             # 더 이상 읽을 이벤트가 없으면 예외 발생 (정상)
            pass

        # 상태값으로 throttle, steering 업데이트
        # 참고: 조이스틱에 따라 축 값이 반대일 수 있습니다. 그럴 경우 부호를 바꾸세요 (예: -self.axis_states.get(...))
        raw_throttle = self.axis_states.get(THROTTLE_AXIS_NAME, 0.0)
        raw_steering = self.axis_states.get(STEER_AXIS_NAME, 0.0)
        
        self.throttle = -apply_deadzone(raw_throttle) # 보통 y축은 위로 올리면 음수이므로 부호 반전
        self.steering = apply_deadzone(raw_steering)

    def _poll_keyboard(self):
        """키보드 입력을 읽어 throttle과 steering 값을 업데이트합니다."""
        # select를 사용하여 논블로킹으로 키 입력 확인
        if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
            key = sys.stdin.read(1)
            
            # 화살표 키 입력 처리
            if key == '\x1b':
                key2 = sys.stdin.read(1)
                key3 = sys.stdin.read(1)
                if key2 == '[':
                    if key3 == 'A': self.throttle = 1.0   # 전진
                    elif key3 == 'B': self.throttle = -1.0 # 후진
                    elif key3 == 'D': self.steering = -1.0 # 좌회전
                    elif key3 == 'C': self.steering = 1.0  # 우회전
            # 정지 키
            elif key in ('s', 'S', ' '):
                self.throttle = 0.0
            # 조향 초기화 키
            elif key in ('a', 'A', 'd', 'D'):
                 self.steering = 0.0

    def get_control(self):
        """main.py에서 현재 조작값을 가져가기 위해 호출하는 함수"""
        # 키보드 입력의 경우, 키를 떼면 값이 0으로 돌아가도록 수정
        # (조이스틱은 중앙으로 돌아오므로 이 로직이 필요 없음)
        current_throttle, current_steering = self.throttle, self.steering
        
        # 키보드 모드일 때만 값을 초기화
        if not self.joystick_connected and self.keyboard_active:
            self.throttle = 0.0
            self.steering = 0.0

        return current_throttle, current_steering

    def stop(self):
        """프로그램 종료 시 main.py에서 호출하는 함수"""
        self.running = False
