"""
WitMotion WT9011DCL IMU 센서의 BLE(Bluetooth Low Energy) 통신 및
데이터 수신을 전담하는 모듈입니다. (Yaw 보정 기능 추가)
"""

import threading
import asyncio
import time
# import math  <- 사용되지 않으므로 제거
from bleak import BleakScanner, BleakClient
import config

class ImuSensor:
    """
    별도 스레드에서 비동기 BLE 통신을 실행하여
    IMU 데이터(Roll, Pitch, Yaw)를 지속적으로 수신하고,
    외부 요청 시 Yaw 값을 보정합니다.
    """
    def __init__(self, logger=None):
        """
        ImuSensor 스레드를 초기화합니다.
        :param logger: 데이터 로깅을 위한 DataLogger 객체 (선택 사항)
        """
        # --- 개선 사항: 데이터 무결성을 위한 Lock 추가 ---
        self.data_lock = threading.Lock()
        
        # 'latest_data'는 보정된 최종 값
        self.latest_data = {
            "timestamp": 0.0,
            "yaw": 0.0,
            "pitch": 0.0,
            "roll": 0.0
        }
        
        # --- 개선 사항: 보정을 위한 내부 변수 ---
        self.raw_yaw = 0.0     # 센서에서 수신한 원본 Yaw 값
        self.yaw_offset = 0.0  # 보정량 (Offset)
        # --- 개선 사항 끝 ---

        self.running = True
        self.logger = logger
        self.thread = threading.Thread(target=self._run_async_loop, daemon=True)
        print("[IMU] IMU 스레드 (Yaw 보정 기능 탑재) 초기화 완료.")

    def _run_async_loop(self):
        """asyncio 이벤트 루프를 이 스레드에서 실행합니다."""
        try:
            asyncio.run(self._ble_communication_loop())
        except Exception as e:
            print(f"[IMU] 비동기 루프에서 에러 발생: {e}")

    async def _ble_communication_loop(self):
        """실제 BLE 통신이 이루어지는 비동기 루프입니다."""
        while self.running:
            device = None
            try:
                print(f"[IMU] 장치 스캔 중... (이름: {config.IMU_DEVICE_NAME})") 
                device = await BleakScanner.find_device_by_name(
                    config.IMU_DEVICE_NAME, timeout=10.0
                )
                if not device:
                    print("[IMU] 장치를 찾을 수 없습니다. 5초 후 재시도합니다.")
                    await asyncio.sleep(5)
                    continue

                print(f"[IMU] 장치 발견. 연결 시도: {device.address}")
                async with BleakClient(device) as client:
                    if client.is_connected:
                        print("[IMU] BLE 장치 연결 성공.")
                        await client.start_notify(
                            config.IMU_DATA_CHAR_UUID, self._notification_handler
                        )
                        print("[IMU] 데이터 수신 대기 중...")
                        while self.running and client.is_connected:
                            await asyncio.sleep(1.0)
                print("[IMU] 장치 연결 끊김.")

            except Exception as e:
                print(f"[IMU] 통신 에러: {e}")
                if self.running:
                    print("[IMU] 5초 후 재연결을 시도합니다.")
                    await asyncio.sleep(5)

    def _notification_handler(self, sender, data: bytearray):
        """BLE 장치로부터 데이터(notification)가 수신될 때마다 호출되는 콜백 함수."""
        try:
            if len(data) != 11 or data[0] != 0x55:
                return
            
            checksum = sum(data[0:10]) & 0xFF
            if checksum != data[10]:
                return

            tag = data[1]
            if tag == 0x53: # 각도 데이터
                roll_raw = int.from_bytes(data[2:4], 'little', signed=True)
                pitch_raw = int.from_bytes(data[4:6], 'little', signed=True)
                yaw_raw_int = int.from_bytes(data[6:8], 'little', signed=True)

                roll = roll_raw / 32768.0 * 180.0
                pitch = pitch_raw / 32768.0 * 180.0
                yaw = yaw_raw_int / 32768.0 * 180.0
                
                now = time.time()

                # --- 개선 사항: Lock을 잡고 데이터 업데이트 ---
                with self.data_lock:
                    # 1. 센서 원본 값(raw) 저장
                    self.raw_yaw = yaw
                    
                    # 2. 보정(Offset) 적용
                    # -180 ~ +180 범위를 넘지 않도록 wrap-around 처리
                    corrected_yaw = (self.raw_yaw + self.yaw_offset + 180) % 360 - 180

                    # 3. 외부로 전달될 최종 데이터 업데이트
                    self.latest_data = {
                        "timestamp": now,
                        "yaw": corrected_yaw, # 보정된 Yaw
                        "pitch": pitch,
                        "roll": roll
                    }
                # --- 개선 사항 끝 ---

                # 로거가 있으면 최종 데이터 전송
                if self.logger:
                    log_entry = {'type': 'imu_data', **self.latest_data}
                    self.logger.log_data(log_entry)

        except Exception as e:
            print(f"[IMU] 데이터 파싱 에러: {e}, 받은 데이터: {data.hex()}")

    def start(self):
        self.running = True
        self.thread.start()

    def get_data(self):
        """
        메인 스레드에서 가장 최근의 '보정된' 센서 데이터를 가져갑니다.
        :return: {"timestamp": ..., "yaw": ..., "pitch": ..., "roll": ...}
        """
        with self.data_lock:
            return self.latest_data.copy()

    def stop(self):
        print("[IMU] 종료 신호 수신.")
        self.running = False

    # -----------------------------------------------------------------
    # --- 🚀 외부 요청을 처리하는 보정용 메서드 (신규 추가) ---
    # -----------------------------------------------------------------

    def tare_yaw(self):
        """
        [외부 요청 1] 현재 IMU의 Yaw 값을 0으로 강제 설정합니다. (영점 조절)
        (예: 차량이 출발선에 정확히 정렬되었을 때 호출)
        """
        with self.data_lock:
            # --- ✨ 수정된 부분: 데이터 수신 여부 확인 ---
            if self.latest_data["timestamp"] == 0.0:
                print("[IMU] 'Tare' 실패. 아직 IMU 데이터를 수신하지 못했습니다.")
                return
            # --- 수정 끝 ---
            
            # 현재 센서의 원본 값(raw_yaw)을 기준으로,
            # 이 값을 0으로 만들기 위한 offset을 계산합니다.
            self.yaw_offset = -self.raw_yaw
            
        print(f"[IMU] Yaw 'Tared' (영점 설정). "
              f"Raw: {self.raw_yaw:.2f}, New Offset: {self.yaw_offset:.2f}")

    def align_yaw(self, true_heading: float):
        """
        [외부 요청 2] 현재 IMU의 Yaw 값을 'true_heading' 값으로 강제 설정합니다.
        (예: GPS/카메라로 '진짜' 방향이 90도임을 알았을 때 호출)
        :param true_heading: 신뢰할 수 있는 실제 방향 값 (degree)
        """
        with self.data_lock:
            # --- ✨ 수정된 부분: 데이터 수신 여부 확인 ---
            if self.latest_data["timestamp"] == 0.0:
                print(f"[IMU] 'Align' 실패. 아직 IMU 데이터를 수신하지 못했습니다.")
                return
            # --- 수정 끝 ---

            # 최종 값(corrected_yaw)이 true_heading이 되도록 offset을 역산합니다.
            # (raw_yaw + new_offset) = true_heading
            offset = true_heading - self.raw_yaw
            
            # offset 값도 -180 ~ +180 사이로 정규화
            self.yaw_offset = (offset + 180) % 360 - 180
            
        print(f"[IMU] Yaw 'Aligned' (강제 정렬). "
              f"Set to: {true_heading:.2f}, Raw: {self.raw_yaw:.2f}, New Offset: {self.yaw_offset:.2f}")

# -----------------------------------------------
# (참고) 테스트 코드
# -----------------------------------------------
if __name__ == '__main__':
    # ... (이전 코드와 동일한 TmpConfig 설정) ...
    class TmpConfig:
        IMU_DEVICE_NAME = "WT9011DCL" # <-- 실제 장치 이름
        IMU_DATA_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
    config = TmpConfig() 

    print("IMU 센서 (보정 기능) 단독 테스트 시작...")
    imu_sensor = ImuSensor()
    imu_sensor.start()

    try:
        # 1. 5초간 데이터 관찰
        print("\n--- 5초간 현재 데이터 관찰 ---")
        for i in range(5):
            time.sleep(1)
            data = imu_sensor.get_data()
            print(f"[{i+1}/15] Yaw: {data['yaw']:.2f} (Roll: {data['roll']:.2f}, Pitch: {data['pitch']:.2f})")

        # 2. [외부 요청 1] 현재 방향을 0도로 보정 (Tare)
        print("\n--- [테스트] 현재 방향을 0도로 강제 보정합니다 (tare_yaw) ---")
        imu_sensor.tare_yaw()
        time.sleep(1)
        
        # 3. 5초간 0도로 보정되었는지 관찰
        print("--- 5초간 0도 근처인지 확인 ---")
        for i in range(5):
            time.sleep(1)
            data = imu_sensor.get_data()
            print(f"[{i+6}/15] Yaw: {data['yaw']:.2f} (Roll: {data['roll']:.2f}, Pitch: {data['pitch']:.2f})")

        # 4. [외부 요청 2] 현재 방향을 90도로 보정 (Align)
        print("\n--- [테스트] 현재 방향을 90도로 강제 정렬합니다 (align_yaw(90.0)) ---")
        imu_sensor.align_yaw(90.0)
        time.sleep(1)

        # 5. 5초간 90도로 보정되었는지 관찰
        print("--- 5초간 90도 근처인지 확인 ---")
        for i in range(5):
            time.sleep(1)
            data = imu_sensor.get_data()
            print(f"[{i+11}/15] Yaw: {data['yaw']:.2f} (Roll: {data['roll']:.2f}, Pitch: {data['pitch']:.2f})")

    except KeyboardInterrupt:
        print("\n사용자 요청으로 테스트 종료.")
    finally:
        imu_sensor.stop()
        print("IMU 센서 테스트 완료.")
