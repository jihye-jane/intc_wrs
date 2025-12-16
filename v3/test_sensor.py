# test_sensors.py
"""센서들만 동시에 테스트하는 스크립트"""
import time
import cv2
import config

from input.lidar_sensor import LidarSensor
from input.depth_camera_sensor import DepthCameraSensor
from input.gps_imu_sensor import GpsImuSensor
from input.manual_input import ManualInput

def main():
    print("=" * 50)
    print(" 센서 동시 작동 테스트 시작")
    print("=" * 50)
    
    # 1. 센서 초기화
    try:
        manual_input = ManualInput()
        manual_input.start()
        print("[Test] 수동 입력 스레드 시작.")
        
        lidar = LidarSensor()
        lidar.start()
        print("[Test] 라이다 스레드 시작.")
        
        camera = DepthCameraSensor()
        camera.start()
        print("[Test] 카메라 스레드 시작.")
        
        gps_imu = GpsImuSensor()
        gps_imu.start()
        print("[Test] GPS/IMU 스레드 시작.")
        
        print("\n[Test] 센서 안정화 3초 대기...")
        time.sleep(3.0)
        
    except Exception as e:
        print(f"[Test] 센서 초기화 실패: {e}")
        return
    
    # 2. 메인 테스트 루프
    print("\n[Test] 센서 데이터 수신 중... (Ctrl+C로 종료)\n")
    
    loop_count = 0
    try:
        while True:
            loop_count += 1
            
            # 모든 센서 데이터 가져오기
            throttle, steering = manual_input.get_control()
            lidar_data = lidar.get_data()
            gps_data = gps_imu.get_data()
            rgb_frame, depth_frame = camera.get_data()
            
            # 1초마다 데이터 출력
            if loop_count % 20 == 0:  # 20Hz 기준 1초
                print(f"[{time.strftime('%H:%M:%S')}] 센서 상태:")
                print(f"  - 수동 입력: throttle={throttle:.2f}, steering={steering:.2f}")
                print(f"  - LiDAR: {len(lidar_data)} points")
                print(f"  - GPS/IMU: yaw={gps_data.get('yaw', 0):.1f}°, pitch={gps_data.get('pitch', 0):.1f}°")
                print(f"  - 카메라: RGB={rgb_frame is not None}, Depth={depth_frame is not None}")
                print()
            
            # 카메라 영상 표시
            if rgb_frame is not None:
                cv2.imshow("RGB Camera", rgb_frame)
            
            if depth_frame is not None:
                depth_color = cv2.applyColorMap(
                    cv2.convertScaleAbs(depth_frame, alpha=0.03),
                    cv2.COLORMAP_JET
                )
                cv2.imshow("Depth Camera", depth_color)
            
            # 'q' 키로 종료
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[Test] 'q' 키 입력. 종료합니다.")
                break
            
            time.sleep(0.05)  # 20Hz
            
    except KeyboardInterrupt:
        print("\n[Test] Ctrl+C 입력. 종료합니다.")
    
    finally:
        # 3. 정리
        print("\n[Test] 모든 센서 정지 중...")
        manual_input.stop()
        lidar.stop()
        camera.stop()
        gps_imu.stop()
        cv2.destroyAllWindows()
        print("[Test] 테스트 완료.")
        print("=" * 50)

if __name__ == "__main__":
    main()
