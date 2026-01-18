"""
샘플 플러그인
=============

이 플러그인은 DART의 플러그인 시스템 사용법을 보여주는 예시입니다.

기능:
1. pre-main 단계: 초기 설정
2. splash 단계: 스플래시 화면에 메시지 표시
3. post-main 단계: 메인 윈도우에 환영 메시지 표시

파일 위치: modules/plugins/sample_plugin.py
"""

from modules.plugin_loader import plugin, plugin_print
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer


# ============================================================================
# Pre-Main Stage: 애플리케이션 시작 직후
# ============================================================================

@plugin(
    name="sample_init",
    stage="pre-main",
    priority=1,
    description="샘플 플러그인 초기화"
)
def sample_init(context=None, config=None):
    """
    애플리케이션 시작 직후 실행되는 초기화 함수
    Context에 데이터를 추가하여 다른 플러그인과 공유 가능
    """
    plugin_print("sample_init", "=" * 50)
    plugin_print("sample_init", "샘플 플러그인 초기화 시작")
    plugin_print("sample_init", "=" * 50)
    
    # Context에 샘플 데이터 추가
    if context is not None:
        context['sample_plugin_data'] = {
            'initialized': True,
            'message': 'Hello from Sample Plugin!',
            'features': ['splash_message', 'main_window_popup']
        }
        
        plugin_print("sample_init", "Context에 데이터 추가 완료")
    
    # Config 사용 예시
    if config:
        timeout = config.get('timeout', 5)
        plugin_print("sample_init", f"설정값 - 타임아웃: {timeout}초")
    
    plugin_print("sample_init", "초기화 완료!")
    
    return {"status": "initialized", "timestamp": "2026-01-18"}


# ============================================================================
# Splash Stage: 스플래시 화면 표시 중
# ============================================================================

@plugin(
    name="sample_splash",
    stage="splash",
    priority=2,
    description="스플래시 화면에 메시지 표시"
)
def sample_splash(context=None, config=None):
    """
    스플래시 화면이 표시되는 동안 실행
    스플래시 화면에 진행 상황을 표시할 수 있음
    """
    plugin_print("sample_splash", "스플래시 단계 시작")
    
    # Context에서 데이터 가져오기
    if context and 'sample_plugin_data' in context:
        data = context['sample_plugin_data']
        plugin_print("sample_splash", f"받은 메시지: {data['message']}")
    
    # 스플래시 화면 업데이트 (splash 객체가 있다면)
    try:
        import time
        
        # 시뮬레이션: 여러 단계 작업
        steps = [
            (0.88, "샘플 플러그인: 리소스 로드 중..."),
            (0.90, "샘플 플러그인: 설정 파일 읽는 중..."),
            (0.92, "샘플 플러그인: 데이터 검증 중..."),
        ]
        
        for progress, message in steps:
            plugin_print("sample_splash", message)
            
            # 스플래시 화면이 있으면 업데이트
            # (실제로는 메인 윈도우에서 splash 객체를 context에 넣어야 함)
            if context and 'splash' in context:
                splash = context['splash']
                if hasattr(splash, 'set_progress'):
                    splash.set_progress(progress, message)
            
            time.sleep(0.1)  # 시뮬레이션용 대기
        
        plugin_print("sample_splash", "스플래시 작업 완료")
        
    except Exception as e:
        plugin_print("sample_splash", f"에러: {str(e)}", level="error")
    
    return {"status": "splash_complete"}


# ============================================================================
# Post-Main Stage: 메인 윈도우 표시 후
# ============================================================================

@plugin(
    name="sample_main",
    stage="post-main",
    priority=3,
    description="메인 윈도우에 환영 메시지 표시"
)
def sample_main(context=None, config=None):
    """
    메인 윈도우가 표시된 후 실행
    UI 컴포넌트에 접근하거나 추가 초기화 작업 수행
    """
    plugin_print("sample_main", "메인 윈도우 단계 시작")
    
    # Context에서 이전 단계 데이터 확인
    if context and 'sample_plugin_data' in context:
        data = context['sample_plugin_data']
        features = ", ".join(data['features'])
        plugin_print("sample_main", f"기능 목록: {features}")
    
    # 메인 윈도우에 환영 메시지 표시
    try:
        # QTimer를 사용하여 약간 지연 후 메시지 박스 표시
        # (메인 윈도우가 완전히 로드된 후)
        def show_welcome_message():
            plugin_print("sample_main", "환영 메시지 표시")
            
            msg_box = QMessageBox()
            msg_box.setWindowTitle("샘플 플러그인")
            msg_box.setIcon(QMessageBox.Information)
            
            # 메시지 내용
            message = """
<h2 style='color: #00d1b2;'>샘플 플러그인이 로드되었습니다!</h2>

<p>이 플러그인은 다음 단계를 거쳤습니다:</p>

<ul>
<li><b>Pre-Main:</b> 초기화 및 Context 데이터 설정</li>
<li><b>Splash:</b> 로딩 중 진행 상황 표시</li>
<li><b>Post-Main:</b> 메인 윈도우에 환영 메시지 표시 (지금!)</b></li>
</ul>

<p style='color: #808080; font-size: 11px;'>
이 메시지는 <code>modules/plugins/sample_plugin.py</code>에서 생성되었습니다.
</p>

<p style='margin-top: 15px;'>
플러그인을 비활성화하려면 파일을 삭제하거나<br>
<code>enabled=False</code>로 설정하세요.
</p>
            """
            
            msg_box.setText(message)
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # 다크 모드 스타일 적용
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #1a1a1a;
                    color: #e0e0e0;
                }
                QMessageBox QLabel {
                    color: #e0e0e0;
                    min-width: 400px;
                }
                QPushButton {
                    background-color: #00d1b2;
                    color: #121212;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-weight: bold;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #00b89c;
                }
            """)
            
            msg_box.exec_()
            plugin_print("sample_main", "환영 메시지 닫힘")
        
        # 1초 후에 메시지 표시 (메인 윈도우 로드 대기)
        QTimer.singleShot(1000, show_welcome_message)
        
        plugin_print("sample_main", "환영 메시지 예약됨 (1초 후 표시)")
        
    except Exception as e:
        plugin_print("sample_main", f"메시지 표시 실패: {str(e)}", level="error")
    
    # 추가 기능: Context에 메인 윈도우 정보 저장 (선택사항)
    if context:
        context['sample_plugin_completed'] = True
        plugin_print("sample_main", "플러그인 완료 상태 기록")
    
    return {
        "status": "complete",
        "message_shown": True,
        "features_loaded": ["welcome_popup", "context_sharing"]
    }


# ============================================================================
# 추가 예시: 비활성화된 플러그인
# ============================================================================

@plugin(
    name="sample_disabled",
    stage="splash",
    priority=0,
    enabled=False,  # 비활성화됨
    description="비활성화된 샘플 플러그인 (실행되지 않음)"
)
def sample_disabled(context=None, config=None):
    """
    이 플러그인은 enabled=False이므로 실행되지 않습니다.
    """
    plugin_print("sample_disabled", "이 메시지는 표시되지 않아야 합니다!")
    return {"status": "should_not_run"}
