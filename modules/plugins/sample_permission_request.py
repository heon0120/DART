"""
샘플 플러그인: 권한 요청 (Permission Request)
메인 애플리케이션 번역에 접근하기 위해 권한을 요청하는 플러그인 예제
"""

from modules.plugin_loader import plugin, plugin_print
from modules.localization import get_localization_manager


@plugin(
    name="sample_permission_request",
    stage="splash",
    priority=0,
    description="메인 애플리케이션 번역 접근 권한이 필요한 샘플 플러그인",
    version="1.0.0",
    permissions=["read_main_locales"]  # 권한 요청!
)
def sample_permission_request(context=None, config=None):
    """
    권한 요청 플러그인
    
    이 플러그인은 메인 애플리케이션의 번역에 접근하기 위해
    'read_main_locales' 권한을 요청합니다.
    
    플러그인 로드 시 사용자에게 권한 승인 여부를 묻습니다.
    """
    i18n = get_localization_manager()
    
    # 자신의 번역 (항상 가능 - 권한 필요 없음)
    plugin_print("sample_permission_request", "플러그인 시작")
    greeting = i18n.get_text("greeting", plugin_name="sample_permission_request")
    plugin_print("sample_permission_request", greeting)
    
    # 메인 애플리케이션 번역 접근 (권한 필요)
    # 사용자가 권한을 승인하면 다음 코드 실행 가능
    try:
        title = i18n.get_text("common.title", plugin_name="sample_permission_request")
        welcome = i18n.get_text("common.welcome", plugin_name="sample_permission_request")
        
        plugin_print("sample_permission_request", f"메인 타이틀: {title}")
        plugin_print("sample_permission_request", f"웰컴 메시지: {welcome}")
        plugin_print("sample_permission_request", "메인 번역 접근 성공!")
        
        # 메인 애플리케이션의 번역들 더 사용해보기
        splash_msg = i18n.get_text("splash.loading_splash", plugin_name="sample_permission_request")
        plugin_print("sample_permission_request", f"스플래시 메시지: {splash_msg}")
        
    except Exception as e:
        plugin_print("sample_permission_request", f"메인 번역 접근 실패: {str(e)}", level="warning")
    
    plugin_print("sample_permission_request", "플러그인 완료")
    
    return {
        "status": "completed",
        "has_permission": True,
        "message": "메인 애플리케이션 번역 접근 테스트 완료"
    }
