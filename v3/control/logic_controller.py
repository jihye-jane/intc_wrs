# control/logic_controller.py
"""
차량의 주행 로직을 결정하는 '두뇌' 모듈입니다.
센서 데이터와 수동 입력값을 바탕으로 안전 규칙을 적용하고,
현재 주행 모드에 따라 최종적으로 모터와 서보에 전달할 제어 값을 결정합니다.
"""

import time
import config

class LogicController:
    def __init__(self, actuators, logger=None):
        """
        LogicController를 초기화합니다.

        :param actuators: board/actuators.py의 ActuatorControl 객체
        :param logger: logging/data_logger.py의 DataLogger 객체 (선택 사항)
        """
        self.actuators = actuators
        self.logger = logger
        
        # --- 주행 모드 ---
        self.mode = 'MANUAL'  # 초기 모드는 'MANUAL' (수동)

        # --- 입력 값 저장 변수 ---
        self.manual_throttle = 0.0
        self.manual_steering = 0.0
        
        # --- 센서 데이터 저장 변수 ---
        self.lidar_data = []
        self.gps_data = {}
        self.rgb_frame = None
        self.depth_frame = None

        print(f"[Control] 로직 컨트롤러 초기화 완료. 시작 모드: {self.mode}")

    def update_manual_input(self, throttle, steering):
        """main.py로부터 수동 조작 값을 받아 업데이트합니다."""
        self.manual_throttle = throttle
        self.manual_steering = steering

    def update_sensor_data(self, lidar, gps, rgb, depth):
        """main.py로부터 모든 센서 데이터를 받아 업데이트합니다."""
        self.lidar_data = lidar
        self.gps_data = gps
        self.rgb_frame = rgb
        self.depth_frame = depth

    def execute_step(self):
        """
        메인 루프에서 주기적으로 호출될 메인 로직 함수입니다.
        안전 -> 모드별 제어 순서로 로직을 실행합니다.
        """
        
        # --- 1. 안전 로직 (Safety Logic) - 최우선 순위 ---
        # 안전 로직이 작동하면, 아래의 모드별 로직을 무시하고 안전한 값으로 제어합니다.
        is_safe, final_throttle, final_steering = self._safety_check()

        # is_safe가 False이면, 안전 로직이 제어권을 가져간 것입니다.
        if not is_safe:
            pass # final_throttle, final_steering에 이미 안전한 값이 할당됨
        
        # --- 2. 모드별 로직 (Mode-Specific Logic) ---
        # 안전한 상황일 때만 모드별 로직을 실행합니다.
        else:
            if self.mode == 'MANUAL':
                final_throttle = self.manual_throttle
                final_steering = self.manual_steering

            elif self.mode == 'AUTO':
                # (TODO) 나중에 자율 주행 로직을 여기에 구현합니다.
                # 현재는 정지 상태를 반환합니다.
                auto_throttle, auto_steering = self._run_autonomy_logic()
                final_throttle = auto_throttle
                final_steering = auto_steering
            
            else: # 알 수 없는 모드일 경우 비상 정지
                final_throttle = 0.0
                final_steering = 0.0
        
        # --- 3. 최종 제어 신호 전송 (Actuation) ---
        self.actuators.set_throttle(final_throttle)
        self.actuators.set_steering(final_steering)

        # --- 4. 로깅 (Logging) ---
        if self.logger:
            self.logger.log_data({
                'timestamp': time.time(),
                'type': 'control_output',
                'mode': self.mode,
                'final_throttle': final_throttle,
                'final_steering': final_steering
            })

    def _safety_check(self):
        """
        안전 상태를 확인하고, 위험 시 제어 값을 강제로 변경(override)합니다.
        :return: (is_safe, throttle, steering) 튜플
                 is_safe=False이면 throttle, steering은 강제된 안전 값입니다.
        """
        
        # [안전 규칙 1: 라이다 기반 전방 장애물 충돌 방지]
        # (예시) 전방 0.8미터 이내에 장애물이 있고, 사용자가 전진하려고 할 때 강제 정지
        obstacle_distance = self._get_frontal_obstacle_distance(angle_range=30, max_dist_m=0.8)
        
        if obstacle_distance is not None: # 장애물이 범위 내에 감지됨
            # 사용자가 전진(throttle > 0)을 시도하면
            if self.manual_throttle > 0:
                print(f"[Control][SAFETY] 전방 {obstacle_distance:.2f}m 장애물 감지! 전진 중단!")
                # 스로틀은 0으로 강제하고, 조향은 사용자의 입력을 유지 (회피 기동 가능)
                return False, 0.0, self.manual_steering

        # 모든 안전 규칙을 통과하면, 안전하다고 판단하고 제어권을 넘김
        return True, 0.0, 0.0

    def _get_frontal_obstacle_distance(self, angle_range, max_dist_m):
        """
        라이다 데이터에서 전방 특정 각도 내 가장 가까운 장애물 거리를 찾습니다.
        :param angle_range: 전방을 기준으로 탐색할 좌우 각도 (예: 30 -> -30도 ~ +30도)
        :param max_dist_m: 장애물로 인식할 최대 거리 (미터)
        :return: 가장 가까운 장애물 거리(m). 없으면 None.
        """
        if not self.lidar_data:
            return None

        min_dist = float('inf')
        found = False
        max_dist_mm = max_dist_m * 1000

        for angle, dist_mm in self.lidar_data:
            # 전방 각도 범위 확인 (0~30도, 330~360도)
            if (0 <= angle <= angle_range) or (360 - angle_range <= angle < 360):
                # 유효한 거리(0 아님)이고, 설정된 최대 거리보다 가까우면
                if 0 < dist_mm < max_dist_mm:
                    if dist_mm < min_dist:
                        min_dist = dist_mm
                        found = True
        
        return min_dist / 1000.0 if found else None

    def _run_autonomy_logic(self):
        """
        (확장 영역) 자율 주행 로직을 구현하는 부분입니다.
        센서 데이터를 종합하여 목표 지점까지 주행하는 스로틀, 조향 값을 계산합니다.
        """
        # TODO: 차선 유지, GPS 기반 경로 추종, 장애물 회피 등 알고리즘 구현
        
        # 현재는 아무것도 하지 않고 정지 값을 반환
        return 0.0, 0.0

    def set_mode(self, new_mode):
        """주행 모드를 변경합니다 (나중에 사용)."""
        if new_mode in ['MANUAL', 'AUTO']:
            self.mode = new_mode
            print(f"[Control] 주행 모드가 '{self.mode}'(으)로 변경되었습니다.")
        else:
            print(f"[Control] 경고: 알 수 없는 모드 '{new_mode}'입니다.")
