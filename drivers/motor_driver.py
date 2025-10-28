# -*- coding: utf-8 -*-
import time
import smbus
from constants import (
    I2C_BUS, MOTOR_ADDR, MOTOR_TYPE_ADDR, MOTOR_ENCODER_POLARITY_ADDR, MOTOR_FIXED_SPEED_ADDR,
    MOTOR_TYPE_JGB37_520_12V_110RPM, MAX_MOTOR_SPEED, MOTOR_MAP, MOTOR_SIGN
)

def _to_byte(val: int) -> int:
    """정수 값을 8비트 부호 없는 바이트 값으로 변환합니다. (음수는 2의 보수 형태로)"""
    return val & 0xFF

class MotorDriver:
    def __init__(self):
        # [수정 1] 모든 특수 공백을 일반 공백으로 변경했습니다.
        try:
            self.bus = smbus.SMBus(I2C_BUS)
            self._init_hw()
        except FileNotFoundError:
            raise RuntimeError(f"I2C 버스({I2C_BUS})를 찾을 수 없습니다. I2C가 활성화되었는지 확인하세요.")

    def _init_hw(self):
        """모터 드라이버 하드웨어를 초기화합니다."""
        try:
            self.bus.write_byte_data(MOTOR_ADDR, MOTOR_TYPE_ADDR, MOTOR_TYPE_JGB37_520_12V_110RPM)
            time.sleep(0.05)
            self.bus.write_byte_data(MOTOR_ADDR, MOTOR_ENCODER_POLARITY_ADDR, 0)
        except OSError as e:
            raise RuntimeError(f"모터 드라이버(주소: {MOTOR_ADDR:#04x}) 초기화 실패: {e}")

    def write_lr(self, left_spd: int, right_spd: int):
        """좌/우 모터 속도를 설정합니다."""
        
        # [수정 2] 입력 속도를 MAX_MOTOR_SPEED 범위 내로 제한하여 안정성 확보
        clamped_left = max(-MAX_MOTOR_SPEED, min(MAX_MOTOR_SPEED, left_spd))
        clamped_right = max(-MAX_MOTOR_SPEED, min(MAX_MOTOR_SPEED, right_spd))
        
        # 채널 맵핑 및 부호 보정
        ch = [0, 0, 0, 0]
        ch[MOTOR_MAP["FL"]] = MOTOR_SIGN["FL"] * clamped_left
        ch[MOTOR_MAP["FR"]] = MOTOR_SIGN["FR"] * clamped_right
        ch[MOTOR_MAP["RL"]] = MOTOR_SIGN["RL"] * clamped_left
        ch[MOTOR_MAP["RR"]] = MOTOR_SIGN["RR"] * clamped_right
        
        # 각 채널의 속도 값을 바이트로 변환
        payload = [_to_byte(int(v)) for v in ch]
        
        try:
            self.bus.write_i2c_block_data(MOTOR_ADDR, MOTOR_FIXED_SPEED_ADDR, payload)
        except OSError as e:
            print(f"경고: 모터 속도 쓰기 실패 - {e}")

    def stop(self):
        """모든 모터를 정지시킵니다."""
        try:
            self.bus.write_i2c_block_data(MOTOR_ADDR, MOTOR_FIXED_SPEED_ADDR, [0, 0, 0, 0])
        except OSError:
            # 정지 시 통신 오류는 무시하여 프로그램이 비정상 종료되지 않도록 함
            pass