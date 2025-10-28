# input/gps_imu_sensor.py
"""
WT901BLECL GPS/IMU 센서의 BLE(Bluetooth Low Energy) 통신 및
데이터 수신을 전담하는 모듈입니다.

bleak 라이브러리를 사용하여 비동기(asyncio)로 BLE 통신을 처리하고,
이 비동기 루프를 별도의 스레드에서 실행합니다.
"""

import threading
import asyncio
import time
from bleak import BleakScanner, BleakClient
import config

class GpsImuSensor:
    """
    별도 스레드에서 비동기 BLE 통신을 실행하여
    GPS 및 IMU 데이터를 지속적으로 수신합니다.
    """
    def __init__(self, logger=None):
        """
        GpsImuSensor 스레드를 초기화합니다.
        :param logger: 데이터 로깅을 위한 DataLogger 객체 (선택 사항)
        """
        self.latest_data = {
            "timestamp": 0.0,
            "latitude": 0.0,
            "longitude": 0.0,
            "yaw": 0.0,
            "pitch": 0.0,
            "roll": 0.0
        }
        self.running = True
        self.logger = logger
        self.thread = threading.Thread(target=self._run_async_loop, daemon=True)
        print("[GPS/IMU] GPS/IMU 스레드 초기화 완료.")

    def _run_async_loop(self):
        """asyncio 이벤트 루프를 이 스레드에서 실행합니다."""
        try:
            asyncio.run(self._ble_communication_loop())
        except Exception as e:
            print(f"[GPS/IMU] 비동기 루프에서 에러 발생: {e}")

    async def _ble_communication_loop(self):
        """실제 BLE 통신이 이루어지는 비동기 루프입니다."""
        while self.running:
            device = None
            try:
                print(f"[GPS/IMU] 장치 스캔 중... (이름: {config.GPS_DEVICE_NAME})")
                device = await BleakScanner.find_device_by_name(
                    config.GPS_DEVICE_NAME, timeout=10.0
                )
                if not device:
                    print("[GPS/IMU] 장치를 찾을 수 없습니다. 5초 후 재시도합니다.")
                    await asyncio.sleep(5)
                    continue

                print(f"[GPS/IMU] 장치 발견. 연결 시도: {device.address}")
                async with BleakClient(device) as client:
                    if client.is_connected:
                        print("[GPS/IMU] BLE 장치 연결 성공.")
                        # 데이터 수신을 위한 Notify 시작
                        await client.start_notify(
                            config.GPS_DATA_CHAR_UUID, self._notification_handler
                        )
                        print("[GPS/IMU] 데이터 수신 대기 중... (Ctrl+C로 종료)")
                        
                        while self.running and client.is_connected:
                            await asyncio.sleep(1.0) # 연결 유지
                
                print("[GPS/IMU] 장치 연결 끊김.")

            except Exception as e:
                print(f"[GPS/IMU] 통신 에러: {e}")
                if self.running:
                    print("[GPS/IMU] 5초 후 재연결을 시도합니다.")
                    await asyncio.sleep(5)

    def _notification_handler(self, sender, data: bytearray):
        """BLE 장치로부터 데이터(notification)가 수신될 때마다 호출되는 콜백 함수."""
        # (!!!) 여기가 가장 중요합니다.
        # WT901BLECL의 데이터 시트(매뉴얼)를 보고,
        # bytearray 형식의 'data'를 실제 값(위도, 경도, 각도 등)으로
        # 변환(파싱)하는 로직을 정확하게 구현해야 합니다.

        # --- 아래는 일반적인 9축 센서 데이터 파싱 예시이며, 실제와 다를 수 있습니다 ---
        try:
            # 예시: WitMotion 표준 프로토콜 (실제 프로토콜 확인 필수!)
            if len(data) == 20 and data[0] == 0x55: # 데이터 패킷 시작 확인
                
                # Roll (Z축 각도)
                roll = int.from_bytes(data[2:4], 'little', signed=True) / 32768.0 * 180.0
                # Pitch (Y축 각도)
                pitch = int.from_bytes(data[4:6], 'little', signed=True) / 32768.0 * 180.0
                # Yaw (X축 각도)
                yaw = int.from_bytes(data[6:8], 'little', signed=True) / 32768.0 * 180.0
                
                # 위도/경도 (데이터 시트 확인 필요)
                # lon = int.from_bytes(data[...], 'little', signed=True) / 10000000.0
                # lat = int.from_bytes(data[...], 'little', signed=True) / 10000000.0

                now = time.time()
                self.latest_data = {
                    "timestamp": now,
                    "latitude": 0.0, # lat
                    "longitude": 0.0, # lon
                    "yaw": yaw,
                    "pitch": pitch,
                    "roll": roll
                }

                # 로거가 있으면 데이터 전송
                if self.logger:
                    log_entry = {'type': 'gps_imu', **self.latest_data}
                    self.logger.log_data(log_entry)

        except Exception as e:
            print(f"[GPS/IMU] 데이터 파싱 에러: {e}, 받은 데이터: {data.hex()}")
        # --- 예시 끝 ---

    def start(self):
        """외부에서 호출하여 스레드를 시작합니다."""
        self.running = True
        self.thread.start()

    def get_data(self):
        """메인 스레드에서 가장 최근의 센서 데이터를 가져갈 때 사용하는 함수."""
        return self.latest_data

    def stop(self):
        """스레드를 안전하게 종료시키기 위해 호출하는 함수"""
        print("[GPS/IMU] 종료 신호 수신.")
        self.running = False

# -----------------------------------------------
# (참고) 이 파일 단독으로 GPS/IMU 센서만 테스트할 때 사용
# -----------------------------------------------
if __name__ == '__main__':
    # 터미널에서 프로젝트 루트 폴더로 이동한 뒤 실행:
    # python -m input.gps_imu_sensor
    
    print("GPS/IMU 센서 단독 테스트 시작...")
    gps_sensor = GpsImuSensor()
    gps_sensor.start()

    try:
        # 30초 동안 2초마다 데이터 출력
        for _ in range(15):
            time.sleep(2)
            data = gps_sensor.get_data()
            print(f"[{time.time():.1f}] 현재 데이터: {data}")

    except KeyboardInterrupt:
        print("\n사용자 요청으로 테스트 종료.")
    finally:
        gps_sensor.stop()
        print("GPS/IMU 센서 테스트 완료.")
