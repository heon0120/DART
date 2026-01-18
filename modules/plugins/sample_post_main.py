"""
샘플 플러그인 3: Post-Main Stage
메인 앱 실행 후에 실행되는 플러그인 예제
"""

from modules.plugin_loader import plugin, plugin_print
from modules.localization import get_localization_manager


@plugin(
    name="sample_post_main",
    stage="post-main",
    priority=0,
    description="메인 앱 실행 후 후처리 작업",
    version="1.0.0"
)
def init_post_main(context=None, config=None):
    """Post-main stage 플러그인 함수"""
    i18n = get_localization_manager()
    
    # 플러그인 번역 사용
    post_processing = i18n.get_text("post_processing", plugin_name="sample_post_main")
    pre_main_detected = i18n.get_text("pre_main_detected", plugin_name="sample_post_main")
    post_complete = i18n.get_text("post_processing_complete", plugin_name="sample_post_main")
    
    plugin_print("sample_post_main", post_processing)
    
    # 예제: 컨텍스트에서 데이터 확인
    if context is not None and 'pre_main_initialized' in context:
        plugin_print("sample_post_main", pre_main_detected)
    
    plugin_print("sample_post_main", post_complete)
    
    return {"post_main_completed": True}
