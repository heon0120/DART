"""
샘플 플러그인 2: Splash Stage
스플래시 화면 표시 중 실행되는 플러그인 예제
"""

from modules.plugin_loader import plugin, plugin_print
from modules.localization import get_localization_manager


@plugin(
    name="sample_splash",
    stage="splash",
    priority=0,
    description="스플래시 화면 초기화 작업",
    version="1.0.0"
)
def init_splash(context=None, config=None):
    """Splash stage 플러그인 함수"""
    i18n = get_localization_manager()
    
    # 플러그인 번역 사용
    resource_loading = i18n.get_text("resource_loading", plugin_name="sample_splash")
    resources_loaded = i18n.get_text("resources_loaded", plugin_name="sample_splash")
    
    plugin_print("sample_splash", resource_loading)
    
    # 예제: 리소스 로딩 등
    resources_count = 0
    for i in range(1, 6):
        resources_count = i
        plugin_print("sample_splash", f"리소스 로딩... {i}/5")
    
    plugin_print("sample_splash", f"총 {resources_count}개 {resources_loaded}")
    
    return {"resources_loaded": resources_count}
