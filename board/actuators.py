# board/actuators.py
"""
하드웨어(모터, 서보)를 직접 구동하는 액추에이터 모듈입니다.
pigpio 라이브러리를 사용하여 PWM 신호를 안정적으로 생성합니다.

(!!!) 실행 전 'sudo systemctl start pigpiod' 필수!
"""

import pigpio
import time
import config  # 설정 파일 임포트

class ActuatorControl:
    def __init__(self):
        """
        pigpio 데몬에 연결하고 모든 모터 및 서보 핀을 초기화합니다.
        """
        print("[Board] 액추에이터 초기화 시작...")
        
        self.pi = pigpio.pi()
        if not self.pi.connected:
            print("[Board] 에러: pigpio 데몬에 연결할 수 없습니다.")
            print("(!!!) 'sudo systemctl start pigpiod' 명령어를 실행했는지 확인하세요.")
            raise RuntimeError("pigpio 데몬 연결 실패")

        # --- 1. 모터 핀 설정 ---
        # (왼쪽)
        self.pi.set_mode(config.MOTOR_LEFT_PWM, pigpio.OUTPUT)
        self.pi.set_mode(config.MOTOR_LEFT_IN1, pigpio.OUTPUT)
        self.pi.set_mode(config.MOTOR_LEFT_IN2, pigpio.OUTPUT)
        
        # (오른쪽)
        self.pi.set_mode(config.MOTOR_RIGHT_PWM, pigpio.OUTPUT)
        self.pi.set_mode(config.MOTOR_RIGHT_IN1, pigpio.OUTPUT)
        self.pi.set_mode(config.MOTOR_RIGHT_IN2, pigpio.OUTPUT)

        # --- 2. 서보 핀 설정 ---
        self.pi.set_mode(config.STEER_SERVO_PIN, pigpio.OUTPUT)

        # --- 3. 초기 상태 설정 (정지) ---
        print("[Board] 모든 모터 정지 및 서보 중앙 정렬...")
        # 모터 PWM 주파수 설정 (예: 1000Hz. 모터 드라이버에 따라 조절)
        self.pi.set_PWM_frequency(config.MOTOR_LEFT_PWM, 1000)
        self.pi.set_PWM_frequency(config.MOTOR_RIGHT_PWM, 1000)
        
        # 모터 정지 (Dutycycle 0)
        self.pi.set_PWM_dutycycle(config.MOTOR_LEFT_PWM, 0)
        self.pi.set_PWM_dutycycle(config.MOTOR_RIGHT_PWM, 0)
        self.pi.write(config.MOTOR_LEFT_IN1, 0)
        self.pi.write(config.MOTOR_LEFT_IN2, 0)
        self.pi.write(config.MOTOR_RIGHT_IN1, 0)
        self.pi.write(config.MOTOR_RIGHT_IN2, 0)

        # 서보 중앙 정렬 (pigpio 서보 펄스는 500~2500 범위)
        self.pi.set_servo_pulsewidth(config.STEER_SERVO_PIN, config.SERVO_CENTER_PULSE)
        time.sleep(0.5) # 서보가 중앙으로 이동할 시간

        print("[Board] 액추에이터 초기화 완료.")

    def set_throttle(self, speed):
        """
        차량의 스로틀(속도)을 설정합니다.
        :param speed: -1.0 (최대 후진) ~ 1.0 (최대 전진)
        """
        
        # 속도 값을 0 ~ 255 (pigpio PWM dutycycle 범위)로 변환
        pwm_val = int(abs(speed) * 255)
        
        # 0~255 범위 보장
        pwm_val = max(0, min(255, pwm_val)) 

        if speed > 0:
            # 전진 (IN1=1, IN2=0)
            self.pi.write(config.MOTOR_LEFT_IN1, 1)
            self.pi.write(config.MOTOR_LEFT_IN2, 0)
            self.pi.write(config.MOTOR_RIGHT_IN1, 1)
            self.pi.write(config.MOTOR_RIGHT_IN2, 0)
        elif speed < 0:
            # 후진 (IN1=0, IN2=1)
            self.pi.write(config.MOTOR_LEFT_IN1, 0)
            self.pi.write(config.MOTOR_LEFT_IN2, 1)
            self.pi.write(config.MOTOR_RIGHT_IN1, 0)
            self.pi.write(config.MOTOR_RIGHT_IN2, 1)
        else:
            # 정지 (IN1=0, IN2=0)
            self.pi.write(config.MOTOR_LEFT_IN1, 0)
            self.pi.write(config.MOTOR_LEFT_IN2, 0)
            self.pi.write(config.MOTOR_RIGHT_IN1, 0)
            self.pi.write(config.MOTOR_RIGHT_IN2, 0)

        # 양쪽 모터에 동일한 PWM 값 인가
        self.pi.set_PWM_dutycycle(config.MOTOR_LEFT_PWM, pwm_val)
        self.pi.set_PWM_dutycycle(config.MOTOR_RIGHT_PWM, pwm_val)

    def set_steering(self, angle):
        """
        조향 서보의 각도를 설정합니다.
        :param angle: -1.0 (최대 좌회전) ~ 1.0 (최대 우회전)
        """
        
        # 각도(-1.0 ~ 1.0)를 서보 펄스 폭(us)으로 변환
        pulse_width = config.SERVO_CENTER_PULSE + (angle * config.SERVO_RANGE_PULSE)
        
        # 서보 펄스 폭 범위 제한 (500us ~ 2500us)
        pulse_width = max(500, min(2500, pulse_width))
        
        self.pi.set_servo_pulsewidth(config.STEER_SERVO_PIN, pulse_width)

    def stop_all(self):
        """
        비상 정지 및 pigpio 리소스 해제.
        프로그램 종료 시 반드시 호출되어야 합니다.
        """
        print("[Board] 모든 액추에이터 정지 및 리소스 해제...")
        
        # 1. 모터 정지
        self.set_throttle(0)
        
        # 2. 서보 PWM 신호 중지 (0으로 설정)
        self.pi.set_servo_pulsewidth(config.STEER_SERVO_PIN, 0)
        
        # 3. pigpio 연결 해제
        self.pi.stop()
        print("[Board] 정지 완료.")

# -----------------------------------------------
# (참고) 단독 테스트용 코드
# -----------------------------------------------
if __name__ == "__main__":
    print("액추에이터 모듈 단독 테스트 시작...")
    
    try:
        act = ActuatorControl()
        
        print("테스트: 3초간 전진 (속도 0.5)")
        act.set_throttle(0.5)
        time.sleep(3.0)
        
        print("테스트: 3초간 후진 (속도 -0.5)")
        act.set_throttle(-0.5)
        time.sleep(3.0)
        
        act.set_throttle(0) # 정지
        
        print("테스트: 3초간 좌회전 (각도 -1.0)")
        act.set_steering(-1.0)
        time.sleep(3.0)
        
        print("테스트: 3초간 우회전 (각도 1.0)")
        act.set_steering(1.0)
        time.sleep(3.0)
        
        act.set_steering(0.0) # 중앙
        
    except Exception as e:
        print(f"테스트 중 에러 발생: {e}")
        
    finally:
        # (중요) 테스트 종료 시에도 반드시 stop_all() 호출
        print("테스트 종료. stop_all() 호출.")
        # (주의: finally 블록에서 'act'가 정의되지 않았을 수 있음)
        # 실제로는 try 블록 안에서 stop_all()을 호출하거나 
        # act가 성공적으로 생성되었는지 확인 후 호출해야 함.
        try:
            if 'act' in locals():
                act.stop_all()
        except Exception as e:
            print(f"종료 중 에러: {e}")

    print("테스트 완료.")
