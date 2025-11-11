# input/depth_camera_sensor.py
"""
OAK-D Lite 뎁스 카메라의 RGB 및 Depth 데이터 수신을 전담하는 모듈입니다.
depthai 라이브러리를 사용하며, 별도의 스레드에서 동작합니다.
(수정: Gen2 API 최신 설정 및 Depth-RGB 정렬 적용)
(수정: 개별 프레임(RGB/Depth) 요청 메소드 추가)
"""

import threading
import time
import cv2
import depthai as dai
import numpy as np
import config
import os

class DepthCameraSensor(threading.Thread):
    """
    OAK-D Lite 카메라를 별도 스레드에서 실행하여
    RGB 이미지와 Depth 맵을 지속적으로 수신합니다.
    """
    def __init__(self, logger=None):
        """
        DepthCameraSensor 스레드를 초기화합니다.
        :param logger: 데이터 로깅을 위한 DataLogger 객체 (선택 사항)
        """
        super().__init__()
        self.daemon = True

        self.latest_rgb_frame = None    # 가장 최근의 RGB 프레임 (OpenCV Mat 형식)
        self.latest_depth_frame = None # 가장 최근의 Depth 프레임 (raw data)
        self.running = True
        self.logger = logger
        self.pipeline = None
        self.device = None
        
        self.frame_count = 0
        self.last_log_time = 0
        
        print("[Camera] 뎁스 카메라 스레드 초기화 완료.")

    def _create_pipeline(self):
        """DepthAI 파이프라인을 생성하고 구성합니다."""
        pipeline = dai.Pipeline()

        # 1. 컬러 카메라 노드 생성
        cam_rgb = pipeline.create(dai.node.ColorCamera)
        cam_rgb.setPreviewSize(config.OAKD_RGB_RESOLUTION)
        cam_rgb.setBoardSocket(dai.CameraBoardSocket.RGB)
        cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
        cam_rgb.setInterleaved(False)
        cam_rgb.setFps(config.OAKD_RGB_FPS)

        # 2. 스테레오(뎁스) 노드 생성
        mono_left = pipeline.create(dai.node.MonoCamera)
        mono_right = pipeline.create(dai.node.MonoCamera)
        stereo = pipeline.create(dai.node.StereoDepth)

        # 모노 카메라 설정
        for mono_cam in [mono_left, mono_right]:
            mono_cam.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
        mono_left.setBoardSocket(dai.CameraBoardSocket.LEFT)
        mono_right.setBoardSocket(dai.CameraBoardSocket.RIGHT)
        
        # 스테레오 뎁스 설정 (최신 권장 설정 적용)
        stereo.setDefaultProfilePreset(dai.node.StereoDepth.Profile.HIGH_DENSITY)
        stereo.setDepthAlign(dai.CameraBoardSocket.RGB)
        stereo.setSubpixel(True)
        stereo.setExtendedDisparity(False) 
        stereo.setLeftRightCheck(True)
        stereo.setMedianFilter(dai.MedianFilter.KERNEL_7x7)
        
        # 3. 출력(XLinkOut) 노드 생성
        xout_rgb = pipeline.create(dai.node.XLinkOut)
        xout_rgb.setStreamName("rgb")
        xout_depth = pipeline.create(dai.node.XLinkOut)
        xout_depth.setStreamName("depth")

        # 4. 노드 연결
        cam_rgb.preview.link(xout_rgb.input)
        mono_left.out.link(stereo.left)
        mono_right.out.link(stereo.right)
        stereo.depth.link(xout_depth.input)
        
        self.pipeline = pipeline
        print("[Camera] DepthAI 파이프라인 생성 완료. (RGB-Depth 정렬 활성화)")

    def run(self):
        """스레드가 시작될 때 실행되는 메인 루프"""
        self._create_pipeline()

        try:
            # DepthAI 장치에 파이프라인 연결 및 시작
            with dai.Device(self.pipeline) as device:
                self.device = device
                print("[Camera] OAK-D Lite 장치 연결 성공.")
                
                # 출력 큐 가져오기
                q_rgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
                q_depth = device.getOutputQueue(name="depth", maxSize=4, blocking=False)

                while self.running:
                    # 각 큐에서 데이터 가져오기 (non-blocking)
                    in_rgb = q_rgb.tryGet()
                    in_depth = q_depth.tryGet()

                    if in_rgb is not None:
                        # OpenCV에서 사용할 수 있는 BGR 형식으로 변환
                        self.latest_rgb_frame = in_rgb.getCvFrame()

                    if in_depth is not None:
                        # 뎁스 프레임(거리 정보, uint16, mm단위)을 가져옴
                        self.latest_depth_frame = in_depth.getFrame()

                    # 데이터 로깅 처리
                    self._log_data()

        except Exception as e:
            print(f"[Camera] 치명적 에러: 카메라 스레드 실행 중 예외 발생: {e}")
            print("[Camera] 팁: '프로파일 없음(No profile)' 오류는 OAK-1(렌즈 1개) 모델에서")
            print("[Camera]     이 OAK-D(렌즈 3개)용 코드를 실행할 때 발생합니다. 모델을 확인하세요.")
        finally:
            print("[Camera] 카메라 스레드 종료 완료.")

    def _log_data(self):
        """설정된 주기에 맞춰 이미지와 관련 데이터를 로깅합니다."""
        if not self.logger or self.latest_rgb_frame is None:
            return

        now = time.time()
        if (now - self.last_log_time) >= (1.0 / config.LOG_IMAGE_SAVE_HZ):
            self.last_log_time = now
            
            # 파일 이름 생성 (타임스탬프_프레임카운트.jpg)
            img_filename = f"{now:.0f}_{self.frame_count}.jpg"
            img_filepath = os.path.join(config.LOG_IMAGE_DIR_PATH, img_filename)

            # 이미지 저장
            cv2.imwrite(img_filepath, self.latest_rgb_frame)
            self.frame_count += 1

            # CSV 파일에 기록할 데이터 전송
            self.logger.log_data({
                'timestamp': now,
                'type': 'camera_frame',
                'image_file': img_filename
            })

    def get_data(self):
        """
        메인 스레드에서 가장 최근의 프레임 데이터를 가져갈 때 사용하는 함수.
        :return: (RGB 프레임, Depth 프레임) 튜플
        """
        return self.latest_rgb_frame, self.latest_depth_frame

    # --- [추가된 코드] ---
    def get_rgb_frame(self):
        """
        가장 최근의 RGB 프레임만 반환합니다.
        :return: OpenCV Mat 형식의 RGB 프레임
        """
        return self.latest_rgb_frame

    def get_depth_frame(self):
        """
        가장 최근의 Depth 프레임(raw data)만 반환합니다.
        :return: raw Depth 프레임 (uint16 numpy array)
        """
        return self.latest_depth_frame
    # --- [추가 완료] ---

    def stop(self):
        """스레드를 안전하게 종료시키기 위해 호출하는 함수"""
        print("[Camera] 종료 신호 수신.")
        self.running = False

# -----------------------------------------------
# (참고) 이 파일 단독으로 카메라 센서만 테스트할 때 사용
# -----------------------------------------------
if __name__ == '__main__':
    # 터미널에서 프로젝트 루트 폴더로 이동한 뒤 실행:
    # python -m input.depth_camera_sensor
    
    # (참고) 로깅 테스트를 위해 임시 Logger 클래스 생성
    class TmpLogger:
        def log_data(self, data):
            print(f"LOG: {data}")
    
    if not os.path.exists(config.LOG_IMAGE_DIR_PATH):
        os.makedirs(config.LOG_IMAGE_DIR_PATH)

    print("뎁스 카메라 센서 단독 테스트 시작...")
    cam_sensor = DepthCameraSensor(logger=TmpLogger())
    cam_sensor.start()

    try:
        while True:
            # --- [수정] 새 메소드를 사용하여 각각 데이터 요청 ---
            rgb_frame = cam_sensor.get_rgb_frame()
            depth_frame = cam_sensor.get_depth_frame()
            
            # 받은 프레임이 있으면 화면에 표시
            if rgb_frame is not None:
                cv2.imshow("RGB Test", rgb_frame)

            if depth_frame is not None:
                # 뎁스 프레임 시각화 (Normalize 방식)
                depth_norm = cv2.normalize(depth_frame, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
                depth_color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
                cv2.imshow("Depth Test", depth_color)

            # 1ms 대기, 'q' 누르면 종료
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            
            time.sleep(0.03) # CPU 사용량 줄이기

    except KeyboardInterrupt:
        print("\n사용자 요청으로 테스트 종료.")
    finally:
        cam_sensor.stop()
        cam_sensor.join()
        cv2.destroyAllWindows()
        print("뎁스 카메라 센서 테스트 완료.")
