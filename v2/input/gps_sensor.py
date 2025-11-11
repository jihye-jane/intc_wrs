"""
U-blox ZED-F9R GPS 수신기의 데이터 수신을 전담하는 모듈입니다.
pyubx2 라이브러리를 사용하며, 별도의 스레드에서 동작합니다.
(재연결 로직 및 스레드 안전성 강화)
"""

import threading
import time
import serial
import pyubx2
import config # OAK-D 코드와 config를 공유한다고 가정

class GpsSensor(threading.Thread):
    """
    U-blox ZED-F9R GPS 수신기를 별도 스레드에서 실행하여
    NAV-PVT (위치, 속도, 시간) 데이터를 지속적으로 수신합니다.
    (연결 실패 시 자동 재연결 기능 포함)
    """
    
    def __init__(self, port, baudrate, logger=None):
        """
        GpsSensor 스레드를 초기화합니다.
        :param port: 시리얼 포트 (예: 'COM3' 또는 '/dev/ttyUSB0')
        :param baudrate: 시리얼 보드레이트 (예: 38400, 115200, 460800)
        :param logger: 데이터 로깅을 위한 DataLogger 객체 (선택 사항)
        """
        super().__init__()
        self.daemon = True
        
        self.port = port
        self.baudrate = baudrate
        self.logger = logger
        self.running = True
        
        # --- ✨ 수정: IMU 센서와 동일한 스레드 안전 패턴 적용 ---
        self.data_lock = threading.Lock()
        self.latest_data = {
            'timestamp': 0.0,
            'fix_type': 0,
            'num_satellites': 0,
            'lat_deg': 0.0,
            'lon_deg': 0.0,
            'altitude_msl_m': 0.0,
            'ground_speed_kmh': 0.0,
            'heading_deg': 0.0,
            'pDOP': 99.0,
        }
        # --- 수정 끝 ---
        
        print(f"[GPS] ZED-F9R 스레드 초기화 완료 (Port: {port}, Baud: {baudrate})")

    def run(self):
        """
        스레드가 시작될 때 실행되는 메인 루프.
        연결이 끊어지면 5초 후 자동으로 재연결을 시도합니다.
        """
        
        # --- ✨ 수정: 견고한 재연결을 위한 '이중 루프' 구조 ---
        while self.running:
            ser = None
            ubr = None
            try:
                # 1. (바깥쪽 루프) 시리얼 포트 연결 시도
                print(f"[GPS] {self.port} 시리얼 포트 연결 시도 중...")
                ser = serial.Serial(self.port, self.baudrate, timeout=3.0)
                ubr = pyubx2.UBXReader(ser)
                print(f"[GPS] {self.port} 시리얼 포트 연결 성공.")

                # 2. (안쪽 루프) 데이터 읽기
                while self.running:
                    try:
                        (raw_data, parsed_data) = ubr.read()
                        
                        if parsed_data is not None:
                            if parsed_data.identity == "NAV-PVT":
                                # NAV-PVT 메시지 수신 성공
                                self._process_nav_pvt(parsed_data)

                    except (pyubx2.UBXStreamError, pyubx2.UBXParseError) as e:
                        print(f"[GPS] 경고: UBX 메시지 파싱 오류: {e}")
                    except serial.SerialException as e:
                        # (안쪽 루프) 장치 연결 끊김
                        print(f"[GPS] 에러: 시리얼 포트 읽기 오류 (장치 연결 끊김): {e}")
                        break # 안쪽 루프 탈출 -> 재연결 시도
                    except Exception as e:
                        print(f"[GPS] 에러: 데이터 처리 중 알 수 없는 예외: {e}")
                        break # 안쪽 루프 탈출 -> 재연결 시도

            except serial.SerialException as e:
                # (바깥쪽 루프) 포트 연결 자체 실패
                print(f"[GPS] 에러: 시리얼 포트 {self.port} 연결 실패: {e}")
            except Exception as e:
                # (바깥쪽 루프) 그 외 치명적 에러
                print(f"[GPS] 치명적 에러: GPS 스레드 실행 중 예외 발생: {e}")
            finally:
                if ser and ser.is_open:
                    ser.close()
                    print(f"[GPS] {self.port} 시리얼 포트 연결 해제.")
            
            if self.running:
                print("[GPS] 5초 후 재연결을 시도합니다.")
                time.sleep(5)
                
        print("[GPS] GPS 스레드 종료 완료.")
        # --- 수정 끝 ---

    def _process_nav_pvt(self, data):
        """
        파싱된 NAV-PVT 데이터를 처리하고, 스레드 안전하게
        self.latest_data를 업데이트하며 로깅을 수행합니다.
        """
        now = time.time()
        
        # 메인 스레드와 공유하는 데이터이므로 Lock을 잡고 업데이트
        with self.data_lock:
            self.latest_data = {
                'timestamp': now,
                'type': 'gps_nav_pvt',
                'fix_type': data.fixType,
                'num_satellites': data.numSV,
                'lat_deg': data.lat,
                'lon_deg': data.lon,
                # 고도 (mm -> m)
                'altitude_msl_m': data.hMSL / 1000.0,
                # 지상 속도 (mm/s -> km/h)
                'ground_speed_kmh': data.gSpeed * 0.0036,
                # 헤딩 (도)
                'heading_deg': data.headMot,
                'pDOP': data.pDOP,
            }

        # 로거가 있으면 데이터 전송 (Lock 바깥에서 수행)
        if self.logger:
            # log_data 함수는 내부적으로 Queue를 사용한다고 가정
            self.logger.log_data(self.latest_data)

    def get_data(self):
        """
        메인 스레드에서 가장 최근의 파싱된 NAV-PVT 데이터를 가져갈 때 사용하는 함수.
        :return: GPS 데이터 딕셔너리 (IMU와 동일한 형식)
        """
        # --- ✨ 수정: IMU 센서와 동일한 스레드 안전 패턴 적용 ---
        with self.data_lock:
            return self.latest_data.copy()
        # --- 수정 끝 ---

    def stop(self):
        """스레드를 안전하게 종료시키기 위해 호출하는 함수"""
        print("[GPS] 종료 신호 수신.")
        self.running = False

# -----------------------------------------------
# (참고) 이 파일 단독으로 GPS 센서만 테스트할 때 사용
# -----------------------------------------------
if __name__ == '__main__':
    # 터미널에서 프로젝트 루트 폴더로 이동한 뒤 실행:
    # python -m input.gps_sensor
    
    import serial.tools.list_ports
    
    # --- 중요: 사용자의 ZED-F9R 설정에 맞게 수정하세요 ---
    GPS_SERIAL_PORT = "COM3" 
    # GPS_SERIAL_PORT = "/dev/ttyACM0" 
    GPS_BAUD_RATE = 115200 
    # ---------------------------------------------------

    # 사용 가능한 포트 목록 출력 (참고용)
    print("--- 사용 가능한 시리얼 포트 ---")
    ports = serial.tools.list_ports.comports()
    if ports:
        for port in ports:
            print(f"  {port.device}: {port.description}")
    else:
        print("  사용 가능한 포트 없음.")
    print(f"------------------------------\n")

    # (참고) 로깅 테스트를 위해 임시 Logger 클래스 생성
    class TmpLogger:
        def log_data(self, data):
            pass # 테스트 중에는 출력하지 않음

    print(f"ZED-F9R 센서 단독 테스트 시작 (Port: {GPS_SERIAL_PORT})...")
    
    gps_sensor = GpsSensor(
        port=GPS_SERIAL_PORT, 
        baudrate=GPS_BAUD_RATE, 
        logger=TmpLogger()
    )
    gps_sensor.start()

    last_print_time = 0

    try:
        while True:
            # ✨ 수정: get_data()는 이제 딕셔너리를 반환합니다.
            nav_data = gps_sensor.get_data()
            
            now = time.time()
            # 1초에 한 번만 최신 데이터 출력
            # (timestamp가 0이 아니어야 첫 데이터를 수신한 것임)
            if nav_data['timestamp'] > 0 and (now - last_print_time >= 1.0):
                last_print_time = now
                
                print(f"\n--- ZED-F9R Status @ {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
                print(f"  Fix Status: {nav_data['fix_type']} (0=No, 2=2D, 3=3D, 4=3D+DGNSS, ...)")
                print(f"  Satellites: {nav_data['num_satellites']}")
                print(f"  위도 (Lat): {nav_data['lat_deg']:.7f} deg")
                print(f"  경도 (Lon): {nav_data['lon_deg']:.7f} deg")
                print(f"  고도 (Alt): {nav_data['altitude_msl_m']:.2f} m (MSL)")
                print(f"  속도 (Spd): {nav_data['ground_speed_kmh']:.2f} km/h")
                print(f"  헤딩 (Hdg): {nav_data['heading_deg']:.2f} deg")
                print(f"  정확도(pDOP): {nav_data['pDOP']:.2f}")

            time.sleep(0.05) # CPU 사용량 줄이기

    except KeyboardInterrupt:
        print("\n사용자 요청으로 테스트 종료.")
    finally:
        gps_sensor.stop()
        gps_sensor.join()
        print("ZED-F9R 센서 테스트 완료.")
