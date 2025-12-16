# input/gps_imu_sensor.py
"""
WT901BLECL 등 WitMotion IMU 센서의 BLE 통신 및 데이터 파싱 모듈.

- 구조: threading + asyncio (비동기 백그라운드 실행)
- 파싱: WitMotion 0x61 패킷 (가속도, 각속도, 각도 통합 데이터) 처리
"""

import threading
import asyncio
import time
import struct
from bleak import BleakScanner, BleakClient
import config  # config.py가 있다고 가정

class GpsImuSensor:
    """
    별도 스레드에서 비동기 BLE 통신을 실행하여
    IMU(가속도, 각속도, 각도) 데이터를 지속적으로 수신 및 파싱합니다.
    """

    # WitMotion BLE 고유 UUID (Code B에서 가져옴)
    # 장치에 따라 다를 수 있으므로 검색 안 되면 확인 필요
    TARGET_SERVICE_UUID = "0000ffe5-0000-1000-8000-00805f9a34fb"
    TARGET_CHAR_UUID_READ = "0000ffe4-0000-1000-8000-00805f9a34fb"  # Notify
    TARGET_CHAR_UUID_WRITE = "0000ffe9-0000-1000-8000-00805f9a34fb" # Write

    def __init__(self, logger=None):
        self.latest_data = {
            "timestamp": 0.0,
            "acc_x": 0.0, "acc_y": 0.0, "acc_z": 0.0,
            "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
            "roll": 0.0,  # Angle X
            "pitch": 0.0, # Angle Y
            "yaw": 0.0,   # Angle Z
            # GPS 데이터 (필요 시 확장)
            "latitude": 0.0,
            "longitude": 0.0
        }
        self.running = True
        self.logger = logger
        
        # 데이터 처리를 위한 버퍼 (Code B의 TempBytes 역할)
        self.data_buffer = bytearray()
        
        self.thread = threading.Thread(target=self._run_async_loop, daemon=True)
        print("[GPS/IMU] 센서 스레드 초기화 완료.")

    def start(self):
        """스레드 시작"""
        self.running = True
        self.thread.start()

    def stop(self):
        """스레드 종료"""
        print("[GPS/IMU] 종료 신호 수신.")
        self.running = False

    def get_data(self):
        """최신 데이터 반환"""
        return self.latest_data.copy()

    def _run_async_loop(self):
        """asyncio 이벤트 루프 실행"""
        try:
            asyncio.run(self._ble_communication_loop())
        except Exception as e:
            print(f"[GPS/IMU] 비동기 루프 치명적 오류: {e}")

    async def _ble_communication_loop(self):
        """BLE 연결 및 재연결 관리 루프"""
        while self.running:
            device = None
            try:
                print(f"[GPS/IMU] 장치 스캔 중... (Target: {config.GPS_DEVICE_NAME})")
                
                # 1. 장치 검색
                device = await BleakScanner.find_device_by_name(
                    config.GPS_DEVICE_NAME, timeout=10.0
                )
                
                # 이름으로 못 찾을 경우, "WT"가 포함된 장치 검색 (Code B 로직 반영)
                if not device:
                    print("[GPS/IMU] 지정된 이름의 장치를 찾지 못해 'WT'로 검색합니다.")
                    devices = await BleakScanner.discover(timeout=5.0)
                    for d in devices:
                        if d.name and "WT" in d.name:
                            device = d
                            break

                if not device:
                    print("[GPS/IMU] 장치를 찾을 수 없습니다. 5초 후 재시도.")
                    await asyncio.sleep(5)
                    continue

                # 2. 연결 시도
                print(f"[GPS/IMU] 연결 시도: {device.name} ({device.address})")
                async with BleakClient(device, timeout=10.0) as client:
                    if client.is_connected:
                        print("[GPS/IMU] BLE 연결 성공.")
                        
                        # 서비스 확인 및 Notify 설정
                        # config에 UUID가 있다면 그것을 쓰고, 없으면 클래스 상수의 기본값 사용
                        notify_uuid = getattr(config, 'GPS_DATA_CHAR_UUID', self.TARGET_CHAR_UUID_READ)
                        
                        try:
                            await client.start_notify(notify_uuid, self._notification_handler)
                            print(f"[GPS/IMU] 데이터 수신 시작 (UUID: {notify_uuid})")
                        except Exception as e:
                            print(f"[GPS/IMU] Notify 설정 실패. UUID를 확인하세요: {e}")
                            await asyncio.sleep(2)
                            continue

                        # 연결 유지 루프
                        while self.running and client.is_connected:
                            await asyncio.sleep(1.0)
                
                print("[GPS/IMU] 연결 끊김.")

            except Exception as e:
                print(f"[GPS/IMU] 통신 에러: {e}")
                if self.running:
                    await asyncio.sleep(5)

    def _notification_handler(self, sender, data: bytearray):
        """
        [Code B의 핵심 파싱 로직 이식]
        데이터가 들어오면 버퍼에 쌓고 0x61 패킷을 찾아 파싱합니다.
        """
        self.data_buffer.extend(data)

        # WitMotion 0x61 패킷 구조:
        # 헤더(0x55 0x61) + 데이터(18byte) + 체크섬(2byte) = 총 22byte
        FULL_PACKET_LENGTH = 22

        while len(self.data_buffer) >= FULL_PACKET_LENGTH:
            # 1. 헤더(0x55) 찾기
            if self.data_buffer[0] != 0x55:
                del self.data_buffer[0]
                continue
            
            # 2. 두 번째 바이트가 0x61인지 확인 (IMU 통합 데이터)
            # (만약 GPS 데이터 0x57 등 다른 패킷도 처리하려면 여기서 분기)
            if self.data_buffer[1] != 0x61:
                # 0x61이 아니면 이 0x55는 유효한 헤더가 아님 (혹은 처리 안 하는 패킷)
                del self.data_buffer[0]
                continue

            # 3. 전체 패킷 추출
            packet = self.data_buffer[:FULL_PACKET_LENGTH]
            
            # 4. 데이터 파싱 실행
            try:
                # 헤더 2바이트(0,1)를 제외한 데이터 부분(2~) 전달
                self._parse_witmotion_data(packet[2:])
            except Exception as e:
                print(f"[GPS/IMU] 파싱 중 에러: {e}")

            # 5. 처리된 패킷 버퍼에서 제거
            del self.data_buffer[:FULL_PACKET_LENGTH]

    def _parse_witmotion_data(self, data_bytes):
        """
        Code B의 processData 메서드와 동일한 로직
        data_bytes: 20바이트 (데이터 18바이트 + 체크섬 2바이트 포함 가능하지만 인덱스로 접근)
        """
        # 리틀 엔디안 변환 및 스케일링
        # Acc (g)
        ax = self._get_sign_int16(data_bytes[1] << 8 | data_bytes[0]) / 32768.0 * 16.0
        ay = self._get_sign_int16(data_bytes[3] << 8 | data_bytes[2]) / 32768.0 * 16.0
        az = self._get_sign_int16(data_bytes[5] << 8 | data_bytes[4]) / 32768.0 * 16.0
        
        # Gyro (deg/s)
        gx = self._get_sign_int16(data_bytes[7] << 8 | data_bytes[6]) / 32768.0 * 2000.0
        gy = self._get_sign_int16(data_bytes[9] << 8 | data_bytes[8]) / 32768.0 * 2000.0
        gz = self._get_sign_int16(data_bytes[11] << 8 | data_bytes[10]) / 32768.0 * 2000.0
        
        # Angle (deg)
        ang_x = self._get_sign_int16(data_bytes[13] << 8 | data_bytes[12]) / 32768.0 * 180.0
        ang_y = self._get_sign_int16(data_bytes[15] << 8 | data_bytes[14]) / 32768.0 * 180.0
        ang_z = self._get_sign_int16(data_bytes[17] << 8 | data_bytes[16]) / 32768.0 * 180.0

        # 최신 데이터 업데이트
        self.latest_data.update({
            "timestamp": time.time(),
            "acc_x": round(ax, 3),
            "acc_y": round(ay, 3),
            "acc_z": round(az, 3),
            "gyro_x": round(gx, 3),
            "gyro_y": round(gy, 3),
            "gyro_z": round(gz, 3),
            "roll": round(ang_x, 3),
            "pitch": round(ang_y, 3),
            "yaw": round(ang_z, 3)
        })

        if self.logger:
            self.logger.log_data({'type': 'gps_imu', **self.latest_data})

    @staticmethod
    def _get_sign_int16(num):
        """Code B의 getSignInt16 정적 메서드"""
        if num >= 32768:  # 2^15
            num -= 65536  # 2^16
        return num

# -----------------------------------------------
# 테스트 코드
# -----------------------------------------------
if __name__ == '__main__':
    # config 모듈이 없을 경우를 대비한 더미 설정 (테스트용)
    if not hasattr(config, 'GPS_DEVICE_NAME'):
        config.GPS_DEVICE_NAME = "WT901BLE" # 혹은 본인 장치 이름 "WT..."
        
    print("GPS/IMU 센서 통합 테스트 시작...")
    sensor = GpsImuSensor()
    sensor.start()

    try:
        while True:
            time.sleep(0.5)
            data = sensor.get_data()
            # 데이터가 갱신되었을 때만 출력하거나 0이 아닐 때 출력
            if data['timestamp'] > 0:
                print(f"Time: {data['timestamp']:.2f} | "
                      f"Roll: {data['roll']:.2f}, Pitch: {data['pitch']:.2f}, Yaw: {data['yaw']:.2f} | "
                      f"AccX: {data['acc_x']:.2f}")
    except KeyboardInterrupt:
        print("\n종료 중...")
    finally:
        sensor.stop()