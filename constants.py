# -*- coding: utf-8 -*-

# 이벤트 타입
EVENT_SYS  = "sys"   # 시스템 이벤트 (e-stop, 모드변경 등)
EVENT_CMD  = "cmd"   # 버튼/키 입력에 의한 명령
EVENT_AXIS = "axis"  # 축 변화(조이스틱 등)

# 시스템 액션
ACTION_E_STOP   = "e_stop"
ACTION_SET_MODE = "set_mode"

# 명령 액션
ACTION_INC_SPEED   = "inc_speed"
ACTION_DEC_SPEED   = "dec_speed"
ACTION_STEER_LEFT  = "steer_left"
ACTION_STEER_RIGHT = "steer_right"
ACTION_STOP        = "stop"

# 모드
MODE_BUTTON   = "BUTTON"
MODE_JOYSTICK = "JOYSTICK"
MODE_SENSOR   = "SENSOR"

# 입력 공통 설정
DEADZONE = 0.05

# 하드웨어 설정
CTRL_HZ = 50.0

# 서보
SERVO_PIN = 12
SERVO_MIN_US, SERVO_MAX_US = 1000, 2000
SERVO_MIN_DEG, SERVO_MAX_DEG = 0.0, 180.0
STEER_AXIS_NAME = "rx"   # 서보 조향에 사용할 조이스틱 축명

# 모터
I2C_BUS = 1
MOTOR_ADDR = 0x34
MOTOR_TYPE_ADDR = 0x14
MOTOR_ENCODER_POLARITY_ADDR = 0x15
MOTOR_FIXED_SPEED_ADDR = 0x33
MOTOR_TYPE_JGB37_520_12V_110RPM = 3

MAX_MOTOR_SPEED = 50

# 채널 매핑
MOTOR_MAP = {  # Front-Left, Front-Right, Rear-Left, Rear-Right
    "FL": 2,
    "FR": 3,
    "RL": 0,
    "RR": 1,
}
MOTOR_SIGN = {  # 특정 바퀴 반전 필요 시 -1
    "FL": 1,
    "FR": -1,
    "RL": -1,
    "RR": 1,
}

# 조이스틱 축명
THROTTLE_AXIS_NAME = "y"
TURN_AXIS_NAME     = "x"