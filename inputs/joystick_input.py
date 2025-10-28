# -*- coding: utf-8 -*-
import os, struct, array, fcntl
# import fcntl as fctl # fcntl을 그대로 사용하는 것이 더 명확할 수 있습니다.
from constants import (
    EVENT_SYS, EVENT_AXIS,
    ACTION_E_STOP, ACTION_SET_MODE,
    DEADZONE, MODE_JOYSTICK,
    THROTTLE_AXIS_NAME, TURN_AXIS_NAME, STEER_AXIS_NAME
)

# [수정 1] 모든 특수 공백을 일반 공백으로 변경했습니다.
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80

axis_names = {
    0x00: 'x', 0x01: 'y', 0x02: 'z', 0x03: 'rx', 0x04: 'ry', 0x05: 'rz',
    0x06: 'throttle', 0x07: 'rudder', 0x08: 'wheel', 0x09: 'gas', 0x0A: 'brake',
    0x10: 'hat0x', 0x11: 'hat0y', 0x12: 'hat1x', 0x13: 'hat1y',
}
button_names = {
    0x130: 'a', 0x131: 'b', 0x132: 'c', 0x133: 'x', 0x134: 'y', 0x135: 'z',
}

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def apply_deadzone(v, dz=0.05):
    return 0.0 if abs(v) < dz else v

def norm_axis_value(raw: int) -> float:
    # 32767.0 으로 나누어 값을 -1.0 ~ 1.0 범위로 정규화
    return max(-1.0, min(1.0, raw / 32767.0))

class JoystickInput:
    def __init__(self, dev_path=None):
        self.is_connected = False
        self.axis_states, self.axis_map = {}, []
        self.button_states, self.button_map = {}, []

        self.dev_path = dev_path or self._find_joystick()
        if not self.dev_path:
            return

        try:
            self.jsdev = open(self.dev_path, 'rb', buffering=0)
        except (FileNotFoundError, PermissionError) as e:
            print(f"Error opening joystick device: {e}")
            return

        try:
            # [개선] device name (사용하지는 않지만 로직은 유지)
            buf = array.array('B', [0] * 64)
            fcntl.ioctl(self.jsdev, 0x80406a13, buf) # JSIOCGNAME(len)
            self.dev_name = buf.tobytes().rstrip(b'\x00').decode('utf-8')

            # num axes/buttons
            b = array.array('B', [0]); fcntl.ioctl(self.jsdev, 0x80016a11, b); num_axes = b[0] # JSIOCGAXES
            b = array.array('B', [0]); fcntl.ioctl(self.jsdev, 0x80016a12, b); num_buttons = b[0] # JSIOCGBUTTONS

            # axis map
            buf = array.array('B', [0] * 0x40); fcntl.ioctl(self.jsdev, 0x80406a32, buf) # JSIOCGAXMAP
            for axis_code in buf[:num_axes]:
                name = axis_names.get(axis_code, f"unknown(0x{axis_code:02x})")
                self.axis_map.append(name); self.axis_states[name] = 0.0

            # button map
            buf = array.array('H', [0] * 200); fcntl.ioctl(self.jsdev, 0x80406a34, buf) # JSIOCGBTNMAP
            for btn_code in buf[:num_buttons]:
                name = button_names.get(btn_code, f"unknown(0x{btn_code:03x})")
                self.button_map.append(name); self.button_states[name] = 0
        except OSError as e:
            print(f"Error during joystick initialization with ioctl: {e}")
            self.jsdev.close()
            return
            
        # non-blocking
        flags = fcntl.fcntl(self.jsdev, fcntl.F_GETFL)
        fcntl.fcntl(self.jsdev, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        self.is_connected = True

    def _find_joystick(self):
        try:
            for fn in sorted(os.listdir('/dev/input')):
                if fn.startswith('js'):
                    return f'/dev/input/{fn}'
        except FileNotFoundError:
            pass
        return None

    def poll(self):
        if not self.is_connected:
            return []
        
        events = []
        axis_event_detected = False # [수정 2] 축 이벤트 발생 여부를 추적하는 플래그
        try:
            # 8바이트의 조이스틱 이벤트 데이터를 읽음
            evbuf = self.jsdev.read(8)
            if evbuf is not None:
                t_ms, value, etype, number = struct.unpack('IhBB', evbuf)

                # 축(Axis) 이벤트 처리
                if (etype & ~JS_EVENT_INIT) == JS_EVENT_AXIS:
                    if number < len(self.axis_map):
                        axis_name = self.axis_map[number]
                        axis_value = norm_axis_value(value)
                        
                        # 상태가 변경되었을 때만 갱신 및 플래그 설정
                        if self.axis_states[axis_name] != axis_value:
                            self.axis_states[axis_name] = axis_value
                            axis_event_detected = True

                # 버튼(Button) 이벤트 처리
                elif (etype & ~JS_EVENT_INIT) == JS_EVENT_BUTTON:
                    if number < len(self.button_map):
                        btn_name = self.button_map[number]
                        is_pressed = (value != 0)
                        self.button_states[btn_name] = is_pressed
                        
                        # 'b' 버튼이 눌렸을 때 비상정지 이벤트 추가
                        if is_pressed and btn_name == 'b':
                            events.append({"type": EVENT_SYS, "action": ACTION_E_STOP})

        except BlockingIOError:
            # 더 이상 읽을 이벤트가 없으면 예외 발생, 정상적인 상황임
            pass
        
        # [수정 2] 루프가 끝난 후, 축 이벤트가 발생했을 경우에만 단일 축 이벤트를 추가
        if axis_event_detected:
            events.append({
                "type": EVENT_AXIS,
                "x": clamp(apply_deadzone(self.axis_states.get(TURN_AXIS_NAME, 0.0), DEADZONE), -1.0, 1.0),
                "y": clamp(apply_deadzone(self.axis_states.get(THROTTLE_AXIS_NAME, 0.0), DEADZONE), -1.0, 1.0),
                "rx": clamp(apply_deadzone(self.axis_states.get(STEER_AXIS_NAME, 0.0), DEADZONE), -1.0, 1.0),
            })
            
        return events