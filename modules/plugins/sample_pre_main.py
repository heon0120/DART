"""
샘플 플러그인 1: Pre-Main Stage
main.py 실행 이전에 실행되는 플러그인 예제
"""

from modules.plugin_loader import plugin, plugin_print
from modules.localization import get_localization_manager


@plugin(
    name="sample_pre_main",
    stage="pre-main",
    priority=1,
    description="메인 실행 전 초기화 작업",
    version="1.0.0"
)
def init_pre_main(context=None, config=None):
    """Pre-main stage 플러그인 함수"""
    i18n = get_localization_manager()
    
    # 플러그인 번역 사용
    greeting = i18n.get_text("greeting", plugin_name="sample_pre_main")
    initializing = i18n.get_text("initializing", plugin_name="sample_pre_main")
    context_init = i18n.get_text("context_initialized", plugin_name="sample_pre_main")
    
    plugin_print("sample_pre_main", greeting)
    plugin_print("sample_pre_main", initializing)
    
    # 예제: 환경 변수나 설정값 초기화
    if config:
        plugin_print("sample_pre_main", f"설정값: {config}")
    
    # context에 데이터 추가
    if context is not None:
        context['pre_main_initialized'] = True
        plugin_print("sample_pre_main", context_init)
    
    return {"status": "initialized"}
