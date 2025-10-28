# -*- coding: utf-8 -*-
import time
import logging
from constants import *

# 각 모듈을 불러올 때 발생할 수 있는 오류를 처리
try:
    from inputs.joystick_input import JoystickInput
    from inputs.keyboard_input import KeyboardInput
    from control.mixer import mix_skid
    from drivers.servo import Servo
    from drivers.motor_driver import MotorDriver
except ImportError as e:
    print(f"필수 모듈을 불러오는 데 실패했습니다: {e}")
    exit()

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("app_rpi")

class RpiRobotApp:
    def __init__(self):
        # [수정 1] 모든 특수 공백을 일반 공백으로 변경했습니다.
        
        # 상태 변수
        self.speed = 0.0      # -1.0 (후진) ~ 1.0 (전진)
        self.steer = 0.0      # -1.0 (좌회전) ~ 1.0 (우회전)
        self.rx = 0.0         # 서보 조향 입력 (-1.0 ~ 1.0)
        self.mode = MODE_JOYSTICK
        self.running = False
        self.hw_ok = False    # [수정 3A] 하드웨어 상태 플래그

        try:
            # 입력 장치 초기화
            self.keyboard = KeyboardInput()
            self.joystick = JoystickInput()
            self.input_source = self.joystick if self.joystick.is_connected else self.keyboard
            log.info(f"기본 입력 소스: {type(self.input_source).__name__}")

            # 드라이버 초기화
            self.servo = Servo()
            self.motor = MotorDriver()
            
            self.servo.neutral() # 서보 중앙 정렬
            self.hw_ok = True
            log.info("하드웨어 초기화 성공.")

        except Exception as e:
            log.critical(f"초기화 실패: {e}")
            self.cleanup() # 실패 시 자원 정리

    def cleanup(self):
        """프로그램 종료 시 호출될 자원 정리 메서드"""
        log.info("프로그램을 종료합니다...")
        if hasattr(self, 'motor'):
            self.motor.stop()
        if hasattr(self, 'servo'):
            # [수정 3C] stop() 대신 cleanup()을 호출하여 pigpio 연결을 안전하게 종료
            self.servo.cleanup()
        if hasattr(self, 'keyboard'):
            self.keyboard.close()

    def handle_event(self, event):
        et = event.get("type")

        if et == EVENT_SYS:
            action = event.get("action")
            if action == ACTION_E_STOP:
                log.critical("!!! 비상 정지(E-STOP) !!!")
                self.running = False # 루프 즉시 종료
            elif action == ACTION_SET_MODE:
                new_mode = event.get("mode")
                if self.mode != new_mode:
                    self.mode = new_mode
                    log.info(f"모드 변경 -> {self.mode}")
                    if self.mode == MODE_BUTTON:
                        self.input_source = self.keyboard
                    elif self.mode == MODE_JOYSTICK:
                        self.input_source = self.joystick
                        if not self.joystick.is_connected:
                            log.warning("조이스틱이 연결되지 않았습니다.")
                    else:
                        self.input_source = None
                        log.warning(f"{new_mode} 모드는 지원되지 않습니다.")
        
        elif et == EVENT_CMD: # 키보드 입력
            action = event.get("action")
            if action == ACTION_INC_SPEED: self.speed = min(1.0, self.speed + 0.1)
            elif action == ACTION_DEC_SPEED: self.speed = max(-1.0, self.speed - 0.1)
            elif action == ACTION_STEER_LEFT: self.steer = -1.0
            elif action == ACTION_STEER_RIGHT: self.steer = 1.0
            elif action == ACTION_STOP: self.speed, self.steer = 0.0, 0.0

        elif et == EVENT_AXIS: # 조이스틱 입력
            if self.mode == MODE_JOYSTICK:
                self.speed = -event.get('y', 0.0) # [수정 3B] Y축 반전
                self.steer = -event.get('x', 0.0)
                self.rx = event.get('rx', 0.0)

    def loop_hw(self):
        """메인 하드웨어 제어 루프"""
        if not self.hw_ok:
            log.error("하드웨어 오류로 인해 메인 루프를 시작할 수 없습니다.")
            return

        self.running = True
        period = 1.0 / max(1.0, CTRL_HZ)
        last_send = 0.0

        try:
            while self.running:
                # [수정 2] 키보드 모드일 때 매번 조향 값을 초기화하여 'sticky' 문제 해결
                if self.mode == MODE_BUTTON:
                    self.steer = 0.0
                
                if self.input_source:
                    for e in self.input_source.poll():
                        self.handle_event(e)
                
                # 서보 즉시 반영: -1..1 -> 0..180
                servo_deg = 90.0 + self.rx * 80.0 # -1 -> 180, 0 -> 90, 1 -> 0
                self.servo.write_angle(servo_deg)

                # 모터는 설정된 주기로 전송 (I2C 부하 감소)
                now = time.time()
                if now - last_send >= period:
                    l, r = mix_skid(self.speed, self.steer)
                    l_i = int(l * MAX_MOTOR_SPEED)
                    r_i = int(r * MAX_MOTOR_SPEED)
                    self.motor.write_lr(l_i, r_i)
                    last_send = now

                # 현재 상태 출력
                print(f"\rMode:{self.mode:<9} Speed:{self.speed:5.2f} Steer:{self.steer:5.2f} Servo:{servo_deg:5.1f}", end="")
                time.sleep(0.01) # CPU 사용량 감소
        
        except KeyboardInterrupt:
            log.info("사용자에 의해 중단되었습니다 (Ctrl+C).")
        
        finally:
            print() # 줄바꿈
            self.cleanup()

if __name__ == "__main__":
    app = RpiRobotApp()
    app.loop_hw()