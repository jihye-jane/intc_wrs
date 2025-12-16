# input/gps_sensor.py
"""
U-blox ZED-F9R GPS 수신기의 데이터 수신을 전담하는 모듈입니다.
pyubx2 라이브러리를 사용하며, 별도의 스레드에서 동작합니다.
"""

import threading
import time
import serial
import pyubx2
import config  # OAK-D 코드와 config를 공유한다고 가정

class GpsSensor(threading.Thread):
    """
    U-blox ZED-F9R GPS 수신기를 별도 스레드에서 실행하여
    NAV-PVT (위치, 속도, 시간) 데이터를 지속적으로 수신합니다.
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
        
        self.latest_nav_pvt = None  # 가장 최근의 파싱된 NAV-PVT 메시지
        self.stream = None
        
        print(f"[GPS] ZED-F9R 스레드 초기화 완료 (Port: {port}, Baud: {baudrate})")

    def run(self):
        """스레드가 시작될 때 실행되는 메인 루프"""
        
        try:
            # 시리얼 포트 연결
            with serial.Serial(self.port, self.baudrate, timeout=3.0) as ser:
                print(f"[GPS] {self.port} 시리얼 포트 연결 성공.")
                # pyubx2 리더기 생성
                ubr = pyubx2.UBXReader(ser)
                
                while self.running:
                    try:
                        # UBX 메시지 읽기 및 파싱
                        (raw_data, parsed_data) = ubr.read()
                        
                        if parsed_data is not None:
                            # 우리는 NAV-PVT 메시지에만 관심이 있습니다.
                            if parsed_data.identity == "NAV-PVT":
                                self.latest_nav_pvt = parsed_data
                                
                                # 데이터 로깅 처리
                                self._log_data(parsed_data)

                    except (pyubx2.UBXStreamError, pyubx2.UBXParseError) as e:
                        print(f"[GPS] 경고: UBX 메시지 파싱 오류: {e}")
                    
                    if not self.running:
                        break

        except serial.SerialException as e:
            print(f"[GPS] 치명적 에러: 시리얼 포트 {self.port} 연결 실패: {e}")
            self.running = False
        except Exception as e:
            print(f"[GPS] 치명적 에러: GPS 스레드 실행 중 예외 발생: {e}")
            self.running = False
        finally:
            print("[GPS] GPS 스레드 종료 완료.")

    def _log_data(self, data):
        """설정된 주기에 맞춰 GPS 데이터를 로깅합니다."""
        if not self.logger:
            return

        now = time.time()
        
        # NAV-PVT의 핵심 정보만 추출하여 로깅
        # (pyubx2는 data.lat, data.lon 등으로 속성에 바로 접근하게 해줍니다)
        self.logger.log_data({
            'timestamp': now,
            'type': 'gps_nav_pvt',
            'fix_type': data.fixType,
            'num_satellites': data.numSV,
            'lat_deg': data.lat,
            'lon_deg': data.lon,
            'altitude_msl_mm': data.hMSL,
            'ground_speed_mm_s': data.gSpeed,
            'heading_deg': data.headMot,
            'pDOP': data.pDOP,
        })

    def get_data(self):
        """
        메인 스레드에서 가장 최근의 파싱된 NAV-PVT 데이터를 가져갈 때 사용하는 함수.
        :return: pyubx2.UBXMessage 객체 (NAV-PVT) 또는 None
        """
        return self.latest_nav_pvt

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
    # ZED-F9R는 USB 연결 시 460800, UART1 기본값은 38400 일 수 있습니다.
    # u-center에서 확인한 포트와 보드레이트를 입력하세요.
    GPS_SERIAL_PORT = "COM3"  # (예: 윈도우)
    # GPS_SERIAL_PORT = "/dev/ttyACM0"  # (예: 리눅스 USB)
    # GPS_SERIAL_PORT = "/dev/ttyS0"      # (예: 리눅스 UART)
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
            # 너무 자주 출력되면 성능에 영향을 주므로 주석 처리
            # print(f"LOG: {data}")
            pass

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
            # get_data()로 파싱된 메시지 받아오기
            nav_data = gps_sensor.get_data()
            
            now = time.time()
            # 1초에 한 번만 최신 데이터 출력
            if nav_data and (now - last_print_time >= 1.0):
                last_print_time = now
                
                print(f"\n--- ZED-F9R Status @ {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
                print(f"  Fix Status: {nav_data.fixType} (0=No, 2=2D, 3=3D, 4=3D+DGNSS, 5=Time, ...)")
                print(f"  Satellites: {nav_data.numSV}")
                print(f"  위도 (Lat): {nav_data.lat} deg")
                print(f"  경도 (Lon): {nav_data.lon} deg")
                print(f"  고도 (Alt): {nav_data.hMSL / 1000.0:.2f} m (MSL)")
                print(f"  속도 (Spd): {nav_data.gSpeed * 0.0036:.2f} km/h")
                print(f"  헤딩 (Hdg): {nav_data.headMot:.2f} deg")
                print(f"  정확도(pDOP): {nav_data.pDOP:.2f}")

            time.sleep(0.05) # CPU 사용량 줄이기

    except KeyboardInterrupt:
        print("\n사용자 요청으로 테스트 종료.")
    finally:
        gps_sensor.stop()
        gps_sensor.join()
        print("ZED-F9R 센서 테스트 완료.")
