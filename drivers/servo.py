# -*- coding: utf-8 -*-
import pigpio
from constants import (
    SERVO_PIN, SERVO_MIN_US, SERVO_MAX_US, SERVO_MIN_DEG, SERVO_MAX_DEG
)

class Servo:
    def __init__(self):
        # [수정 1] 모든 특수 공백을 일반 공백으로 변경했습니다.
        self._pi = pigpio.pi()
        if not self._pi.connected:
            raise RuntimeError("pigpio 연결 실패: 'sudo pigpiod' 명령이 실행되었는지 확인하세요.")

    def __del__(self):
        """객체가 소멸될 때 pigpio 연결을 정리합니다."""
        self.cleanup()

    def angle_to_us(self, angle_deg: float) -> int:
        """각도(degree)를 마이크로초(us) 펄스 폭으로 변환합니다."""
        # 입력 각도를 서보의 최소/최대 각도 범위 내로 제한
        angle = max(SERVO_MIN_DEG, min(SERVO_MAX_DEG, angle_deg))
        
        # 선형 비례식을 사용하여 펄스 폭 계산
        us = SERVO_MIN_US + (angle - SERVO_MIN_DEG) * (SERVO_MAX_US - SERVO_MIN_US) / (SERVO_MAX_DEG - SERVO_MIN_DEG)
        return int(us)

    def write_angle(self, angle_deg: float):
        """주어진 각도로 서보를 움직입니다."""
        pulse_width = self.angle_to_us(angle_deg)
        self._pi.set_servo_pulsewidth(SERVO_PIN, pulse_width)

    def neutral(self):
        """서보를 중간 위치(90도)로 이동시킵니다."""
        self.write_angle(90.0)

    # [수정 2] 메서드 이름과 역할을 명확하게 변경
    def release(self):
        """서보 모터로 가는 신호를 중단하여 전력 소모를 줄입니다. (모터 고정 풀림)"""
        self._pi.set_servo_pulsewidth(SERVO_PIN, 0)

    # [수정 2] pigpio 연결 종료를 위한 별도 메서드 추가
    def cleanup(self):
        """pigpio 라이브러리와의 연결을 안전하게 종료합니다."""
        if self._pi and self._pi.connected:
            self.release() # 종료 전 서보 신호 끄기
            self._pi.stop()
            self._pi = None # 연결 객체 정리