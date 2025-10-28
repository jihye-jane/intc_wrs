# main.py
"""
UGV(무인 차량) 시스템의 메인 실행 파일입니다.

모든 모듈(Input, Control, Board, Logging)을 초기화하고,
메인 제어 루프를 실행하며, 안전한 종료를 처리합니다.
"""

import time
import cv2  # OpenCV (디버깅용 영상 표시에 사용)
import config  # 설정 파일 임포트

# 1. 각 모듈 클래스 임포트
from input.sensors import LidarSensor, CameraSensor, GpsImuSensor
from input.manual_input import ManualInput
from board.actuators import ActuatorControl
from control.logic_controller import LogicController
from logging.data_logger import DataLogger

def main():
    """메인 실행 함수"""
    print("===================================")
    print(" 무인 차량(UGV) 시스템을 시작합니다. ")
    print("===================================")
    
    # -----------------------------------------------
    # 1. 로거 모듈 초기화 (가장 먼저)
    # -----------------------------------------------
    logger = None
    if config.LOG_ENABLE:
        try:
            logger = DataLogger()
            logger.start()
            print("[Main] 데이터 로거 스레드 시작.")
        except Exception as e:
            print(f"[Main] 에러: 로거 모듈 시작 실패: {e}")
            # 로깅이 중요하면 여기서 종료할 수도 있음
            # return 
    else:
        print("[Main] 로깅 비활성화됨.")

    # -----------------------------------------------
    # 2. Board 모듈 초기화 (하드웨어 제어)
    # -----------------------------------------------
    try:
        actuators = ActuatorControl()
        print("[Main] 액추에이터(Board) 모듈 초기화 성공.")
    except Exception as e:
        print(f"[Main] 치명적 에러: 액추에이터 초기화 실패: {e}")
        print("(!!!) pigpio 데몬이 실행 중인지 확인하세요 (sudo systemctl start pigpiod)")
        if logger:
            logger.stop()
        return  # 액추에이터 없이는 주행 불가

    # -----------------------------------------------
    # 3. Control 모듈 초기화 (두뇌)
    # -----------------------------------------------
    controller = LogicController(actuators, logger)
    print(f"[Main] 컨트롤러(Control) 모듈 초기화. 시작 모드: {controller.mode}")

    # -----------------------------------------------
    # 4. Input 모듈 초기화 및 스레드 시작
    # -----------------------------------------------
    try:
        # 수동 입력
        manual_input = ManualInput()
        manual_input.start()
        print("[Main] 수동 입력(Input) 스레드 시작.")
        
        # 라이다
        lidar = LidarSensor(logger)
        lidar.start()
        print("[Main] 라이다(Input) 스레드 시작.")
        
        # 뎁스 카메라
        camera = CameraSensor(logger)
        camera.start()
        print("[Main] 카메라(Input) 스레드 시작.")
        
        # GPS/IMU
        gps_imu = GpsImuSensor(logger)
        gps_imu.start()  # 내부적으로 비동기 루프용 스레드 시작
        print("[Main] GPS/IMU(Input) 스레드 시작.")
        
        print("\n[Main] 모든 Input 스레드 시작. (센서 안정화 3초 대기)")
        time.sleep(3.0)
        
    except Exception as e:
        print(f"[Main] 치명적 에러: Input 모듈 시작 실패: {e}")
        # 실패 시 모든 리소스 정리
        actuators.stop_all()
        if logger:
            logger.stop()
        # (시작된 스레드들도 모두 stop() 호출 필요 - 여기서는 단순화)
        return

    # -----------------------------------------------
    # 5. 메인 제어 루프 (Control Loop)
    # -----------------------------------------------
    print("\n[Main] 메인 제어 루프를 시작합니다. (터미널 'q' 또는 Ctrl+C로 종료)")
    
    # 루프 주기 계산
    loop_interval = 1.0 / config.MAIN_LOOP_HZ
    
    try:
        while True:
            loop_start_time = time.time()

            # --- [흐름 1: Input] 모든 입력값 가져오기 ---
            # (각 스레드에서 최신 데이터를 non-blocking으로 가져옴)
            throttle_in, steering_in = manual_input.get_control()
            lidar_data = lidar.get_data()
            gps_data = gps_imu.get_data()
            rgb_frame, depth_frame = camera.get_data()

            # --- [흐름 2: Control] 로직 컨트롤러에 데이터 전달 ---
            controller.update_manual_input(throttle_in, steering_in)
            controller.update_sensor_data(lidar_data, gps_data, rgb_frame, depth_frame)
            
            # --- [흐름 3: Control -> Board] 로직 실행 ---
            # (안전 로직, 모드별 제어 로직이 여기서 실행됨)
            # (실제 모터/서보 제어 신호는 이 함수 내부에서 actuators로 전달됨)
            controller.execute_step()

            # --- [흐름 4: 디버깅] (선택 사항) ---
            
            # (디버깅) 카메라 영상 출력
            if rgb_frame is not None:
                # (필요시 controller.mode 같은 텍스트 추가)
                # cv2.putText(rgb_frame, f"Mode: {controller.mode}", ...)
                cv2.imshow("RGB Camera Feed", rgb_frame)
            
            # (디버깅) 뎁스 영상 출력
            if depth_frame is not None:
                depth_color = cv2.applyColorMap(
                    cv2.convertScaleAbs(depth_frame, alpha=0.03), 
                    cv2.COLORMAP_JET
                )
                cv2.imshow("Depth Feed", depth_color)

            # 'q' 키를 누르면 루프 종료 (OpenCV 창이 활성화되어 있어야 함)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[Main] 'q' 키 입력. 시스템을 종료합니다.")
                break

            # --- [흐름 5: 루프 주기 맞추기] ---
            elapsed_time = time.time() - loop_start_time
            sleep_time = loop_interval - elapsed_time
            
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # (주의) 루프가 설정된 주기(Hz)보다 느리게 실행되고 있음
                print(f"[Main] 경고: 제어 루프가 느립니다! "
                      f"(소요: {elapsed_time:.4f}s > 목표: {loop_interval:.4f}s)")

    except KeyboardInterrupt:
        # 터미널에서 Ctrl+C 입력 시
        print("\n[Main] Ctrl+C 입력. 시스템을 안전하게 종료합니다.")
    except Exception as e:
        # 예상치 못한 에러 발생 시
        print(f"\n[Main] 치명적 에러 발생: {e}")
    finally:
        # -----------------------------------------------
        # 6. 종료 처리 (매우 중요)
        # -----------------------------------------------
        print("\n[Main] 모든 시스템을 정지합니다...")
        
        # (중요) 액추에이터(모터)를 가장 먼저 정지
        actuators.stop_all()
        print("[Main] 액추에이터 정지 완료.")
        
        # 모든 Input 스레드 정지 신호
        manual_input.stop()
        lidar.stop()
        camera.stop()
        gps_imu.stop()
        print("[Main] 모든 Input 스레드 정지 신호 전송.")
        
        # OpenCV 창 닫기
        cv2.destroyAllWindows()
        
        # 로거 스레드 정지 (파일 닫기)
        if logger:
            logger.stop()
            print("[Main] 로거 정지 완료.")
        
        print("===================================")
        print(" 시스템 종료.")
        print("===================================")

# 이 파일이 직접 실행될 때만 main() 함수 호출
if __name__ == "__main__":
    main()
