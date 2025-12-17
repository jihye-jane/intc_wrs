# input/lidar_sensor.py
"""
RPLIDAR C1 센서의 하드웨어 연결 및 데이터 수신을 전담하는 모듈입니다.
별도의 스레드에서 동작하여 메인 프로그램을 방해하지 않습니다.
"""

import threading
import time
from pyrplidar import PyRPlidar
import config  # 프로젝트의 메인 설정 파일 임포트

class LidarSensor(threading.Thread):
    """
    RPLIDAR 센서를 별도 스레드에서 실행하여 360도 스캔 데이터를 지속적으로 수신합니다.
    """
    def __init__(self, logger=None):
        """
        LidarSensor 스레드를 초기화합니다.
        :param logger: 데이터 로깅을 위한 DataLogger 객체 (선택 사항)
        """
        super().__init__()
        self.daemon = True  # 메인 프로그램 종료 시 이 스레드도 함께 종료

        self.lidar = PyRPlidar()
        self.latest_scan = []  # 가장 최근의 [(angle, distance), ...] 스캔 데이터
        self.running = True    # 스레드 실행/종료를 제어하는 플래그
        self.logger = logger
        self.is_connected = False # 라이다 연결 상태 플래그
        print("[Lidar] 라이다 스레드 초기화 완료.")

    def run(self):
        """스레드가 시작될 때 실행되는 메인 루프"""
        print(f"[Lidar] 라이다 연결 시도: {config.LIDAR_PORT}")
        try:
            # 1. 라이다 연결
            self.lidar.connect(port=config.LIDAR_PORT, baudrate=115200, timeout=3)
            self.is_connected = True
            print("[Lidar] 라이다 연결 성공.")

            # 2. 모터 시작 (안정화를 위해 잠시 대기)
            self.lidar.set_motor_pwm(660)
            time.sleep(2)

            # 3. 스캔 시작
            scan_generator = self.lidar.start_scan_express(scan_type='express_4k')
            print("[Lidar] 라이다 스캔 시작.")

            # 4. running 플래그가 True인 동안 계속 스캔
            for scan_data in scan_generator():
                if not self.running:
                    break  # stop() 메서드가 호출되면 루프 탈출
                
                # 수신된 측정값(measurement) 리스트를 (각도, 거리) 튜플 리스트로 변환
                self.latest_scan = [(m.angle, m.distance) for m in scan_data]
                
                # (로깅) 라이다 데이터는 양이 많으므로 필요시 요약 정보만 로깅
                # if self.logger:
                #     self.logger.log_data({'timestamp': time.time(), 'type': 'lidar_summary', ...})

        except Exception as e:
            print(f"[Lidar] 치명적 에러: 라이다 스레드 실행 중 예외 발생: {e}")
            self.latest_scan = [] # 에러 발생 시 데이터 초기화
            self.is_connected = False

        finally:
            # 5. 스레드 종료 시 반드시 하드웨어 정리
            print("[Lidar] 정리 작업 시작...")
            if self.is_connected:
                self.lidar.stop()
                self.lidar.set_motor_pwm(0)
                self.lidar.disconnect()
            print("[Lidar] 라이다 스레드 종료 완료.")

    def get_data(self):
        """
        메인 스레드에서 가장 최근의 스캔 데이터를 가져갈 때 사용하는 함수.
        :return: (각도, 거리) 튜플의 리스트
        """
        return self.latest_scan

    def stop(self):
        """스레드를 안전하게 종료시키기 위해 호출하는 함수"""
        print("[Lidar] 종료 신호 수신.")
        self.running = False

# -----------------------------------------------
# (참고) 이 파일 단독으로 라이다 센서만 테스트할 때 사용
# -----------------------------------------------
if __name__ == '__main__':
    # (주의) 이 파일을 직접 실행하려면 config.py가 상위 폴더에 있어야 하므로
    # 터미널에서 프로젝트의 루트 폴더로 이동한 뒤, 아래와 같이 실행해야 합니다.
    # python -m input.lidar_sensor

    print("라이다 센서 단독 테스트 시작...")
    lidar_sensor = LidarSensor()
    lidar_sensor.start()  # 스레드 시작

    try:
        # 10초 동안 1초마다 데이터 포인트 개수 출력
        for i in range(10):
            time.sleep(1)
            scan = lidar_sensor.get_data()
            if scan:
                print(f"[{i+1}/10초] 현재 스캔 포인트 개수: {len(scan)}, 첫 번째 포인트: {scan[0]}")
            else:
                print(f"[{i+1}/10초] 스캔 데이터를 아직 받지 못했거나 에러 발생.")

    except KeyboardInterrupt:
        print("\n사용자 요청으로 테스트 종료.")
    finally:
        lidar_sensor.stop()  # 스레드 종료 신호
        lidar_sensor.join()  # 스레드가 완전히 끝날 때까지 대기
        print("라이다 센서 테스트 완료.")
