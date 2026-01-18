"""
플러그인 로더 모듈
- 플러그인 자동 탐색, 로드, 실행
- 데코레이터 기반 메타데이터 관리
- 플러그인별 출력 통일화
"""

import os
import sys
import importlib
import traceback
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional
from functools import wraps


# ============================================================================
# 플러그인 데코레이터 및 메타데이터
# ============================================================================

class PluginMetadata:
    """플러그인 메타데이터"""
    def __init__(
        self,
        name: str,
        stage: str = "pre-main",
        priority: int = 0,
        enabled: bool = True,
        description: str = "",
        version: str = "1.0.0",
        permissions: List[str] = None,
    ):
        self.name = name
        self.stage = stage  # "pre-main", "splash", "post-main" 등
        self.priority = priority  # 높을수록 먼저 실행
        self.enabled = enabled
        self.description = description
        self.version = version
        self.permissions = permissions or []  # 요청할 권한 리스트


def plugin(
    name: str,
    stage: str = "pre-main",
    priority: int = 0,
    enabled: bool = True,
    description: str = "",
    version: str = "1.0.0",
    permissions: List[str] = None,
):
    """
    플러그인 데코레이터
    
    Args:
        name: 플러그인 이름
        stage: 실행 시점 ("pre-main", "splash", "post-main" 등)
        priority: 우선순위 (높을수록 먼저 실행, 기본값: 0)
        enabled: 활성화 여부
        description: 설명
        version: 버전
        permissions: 요청할 권한 리스트 ["read_main_locales", "write_locales"]
    
    Example:
        @plugin(name="my_plugin", stage="splash", priority=1, permissions=["read_main_locales"])
        def init_my_plugin(context=None):
            plugin_print("my_plugin", "초기화 중...")
    """
    def decorator(func_or_class):
        # 메타데이터 저장
        metadata = PluginMetadata(
            name=name,
            stage=stage,
            priority=priority,
            enabled=enabled,
            description=description,
            version=version,
            permissions=permissions or [],
        )
        
        # 함수 또는 클래스에 메타데이터 속성 추가
        func_or_class.__plugin_metadata__ = metadata
        
        # 함수인 경우 래퍼 추가
        if callable(func_or_class):
            @wraps(func_or_class)
            def wrapper(*args, **kwargs):
                return func_or_class(*args, **kwargs)
            wrapper.__plugin_metadata__ = metadata
            return wrapper
        
        return func_or_class
    
    return decorator


# ============================================================================
# 플러그인 로더
# ============================================================================

class PluginLoader:
    """플러그인 로더"""
    
    def __init__(self, plugins_dir: str = None, localization_manager=None):
        """
        플러그인 로더 초기화
        
        Args:
            plugins_dir: 플러그인 디렉터리 경로 (기본: modules/plugins)
            localization_manager: LocalizationManager 인스턴스 (기본: None)
        """
        if plugins_dir is None:
            # main.py 기준 modules/plugins 디렉터리
            current_dir = Path(__file__).parent
            plugins_dir = str(current_dir / "plugins")
        
        self.plugins_dir = Path(plugins_dir)
        self.plugins: Dict[str, Any] = {}  # {name: metadata}
        self.plugin_funcs: Dict[str, List[Callable]] = {}  # {stage: [funcs]}
        self.config: Dict[str, Any] = {}  # 플러그인 설정값
        self.localization_manager = localization_manager  # i18n 관리자
        
        # 플러그인 디렉터리가 없으면 생성
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        # 플러그인 디렉터리를 sys.path에 추가 (임포트 가능하게)
        if str(self.plugins_dir) not in sys.path:
            sys.path.insert(0, str(self.plugins_dir))
    
    def load_all_plugins(self) -> int:
        """
        플러그인 디렉터리에서 모든 플러그인 로드
        
        Returns:
            로드된 플러그인 수
        """
        if not self.plugins_dir.exists():
            plugin_print("PluginLoader", f"플러그인 디렉터리 없음: {self.plugins_dir}")
            return 0
        
        plugin_count = 0
        
        # .py 파일 탐색 (__init__.py 제외)
        for py_file in self.plugins_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            
            module_name = py_file.stem
            
            try:
                # 동적 임포트
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # 모듈 내 @plugin 데코레이터가 붙은 함수/클래스 탐색
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    
                    # __plugin_metadata__ 속성이 있는지 확인
                    if hasattr(attr, "__plugin_metadata__"):
                        metadata = attr.__plugin_metadata__
                        
                        # 플러그인 정보 저장
                        self.plugins[metadata.name] = {
                            "metadata": metadata,
                            "func": attr,
                            "module": module_name,
                            "path": str(py_file.parent),
                        }
                        
                        # stage별로 정렬 (우선순위 높은 순)
                        if metadata.stage not in self.plugin_funcs:
                            self.plugin_funcs[metadata.stage] = []
                        
                        self.plugin_funcs[metadata.stage].append((metadata, attr))
                        
                        # 우선순위순으로 정렬
                        self.plugin_funcs[metadata.stage].sort(
                            key=lambda x: x[0].priority, reverse=True
                        )
                        
                        # 플러그인 번역 파일 로드
                        if self.localization_manager:
                            self.localization_manager.load_plugin_translations(
                                metadata.name,
                                str(py_file.parent)
                            )
                        
                        # 권한 요청
                        if metadata.permissions:
                            self._handle_plugin_permissions(metadata)
                        
                        plugin_count += 1
                
            except Exception as e:
                plugin_print(
                    "PluginLoader",
                    f"[Error] 플러그인 로드 실패: {module_name}",
                    level="error"
                )
                plugin_print("PluginLoader", f"  상세: {str(e)}")
        
        return plugin_count
    
    def run_plugins(
        self,
        stage: str,
        context: Dict[str, Any] = None,
        config: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        특정 stage의 플러그인 실행
        
        Args:
            stage: 실행 stage ("pre-main", "splash", "post-main" 등)
            context: 플러그인에 전달할 컨텍스트 (공유 데이터)
            config: 플러그인 설정값
        
        Returns:
            플러그인 실행 결과 딕셔너리
        """
        if context is None:
            context = {}
        
        if config is None:
            config = {}
        
        self.config = config
        results = {}
        
        if stage not in self.plugin_funcs:
            return results
        
        # 우선순위순 실행
        for metadata, func in self.plugin_funcs[stage]:
            if not metadata.enabled:
                plugin_print(
                    metadata.name,
                    f"[Skip] 비활성화됨",
                    level="info"
                )
                continue
            
            try:
                plugin_print(metadata.name, f"실행 중...")
                
                # 함수 실행 (context와 config 전달)
                result = func(context=context, config=config.get(metadata.name, {}))
                results[metadata.name] = {
                    "status": "success",
                    "result": result,
                }
                
                plugin_print(metadata.name, f"완료")
                
            except Exception as e:
                plugin_print(metadata.name, f"[Error] 실행 중 오류 발생")
                plugin_print(
                    metadata.name,
                    f"  {type(e).__name__}: {str(e)}",
                    level="error"
                )
                
                # 트레이스백 출력
                tb = traceback.format_exc()
                for line in tb.split("\n"):
                    if line.strip():
                        plugin_print(metadata.name, f"  {line}", level="error")
                
                results[metadata.name] = {
                    "status": "error",
                    "error": str(e),
                }
        
        return results
    
    def get_plugin_info(self, name: str = None) -> Dict[str, Any]:
        """
        플러그인 정보 조회
        
        Args:
            name: 플러그인 이름 (None이면 모든 플러그인 정보)
        
        Returns:
            플러그인 정보
        """
        if name:
            if name in self.plugins:
                info = self.plugins[name]
                return {
                    "name": info["metadata"].name,
                    "stage": info["metadata"].stage,
                    "priority": info["metadata"].priority,
                    "enabled": info["metadata"].enabled,
                    "description": info["metadata"].description,
                    "version": info["metadata"].version,
                    "module": info["module"],
                }
            return None
        
        # 모든 플러그인 정보
        all_info = {}
        for pname, info in self.plugins.items():
            all_info[pname] = {
                "name": info["metadata"].name,
                "stage": info["metadata"].stage,
                "priority": info["metadata"].priority,
                "enabled": info["metadata"].enabled,
                "description": info["metadata"].description,
                "version": info["metadata"].version,
                "module": info["module"],
            }
        return all_info
    
    def enable_plugin(self, name: str) -> bool:
        """플러그인 활성화"""
        if name in self.plugins:
            self.plugins[name]["metadata"].enabled = True
            return True
        return False
    
    def disable_plugin(self, name: str) -> bool:
        """플러그인 비활성화"""
        if name in self.plugins:
            self.plugins[name]["metadata"].enabled = False
            return True
        return False
    
    def _handle_plugin_permissions(self, metadata: PluginMetadata):
        """
        플러그인 권한 처리
        
        Args:
            metadata: 플러그인 메타데이터
        """
        if not self.localization_manager:
            return
        
        # 권한 요청
        results = self.localization_manager.request_plugin_permission(
            metadata.name,
            metadata.permissions,
            reason=metadata.description
        )
        
        # 권한 부여 결과 로깅
        for perm, granted in results.items():
            status = "✓ 승인" if granted else "✗ 거부"
            plugin_print(
                metadata.name,
                f"권한 {perm}: {status}"
            )


# ============================================================================
# 플러그인용 출력 함수
# ============================================================================

def plugin_print(
    plugin_name: str,
    message: str,
    level: str = "info"
):
    """
    플러그인 출력 함수
    
    Args:
        plugin_name: 플러그인 이름
        message: 출력 메시지
        level: 로그 레벨 ("info", "warning", "error")
    
    Example:
        plugin_print("my_plugin", "초기화 완료")
        plugin_print("my_plugin", "에러 발생", level="error")
    """
    # 레벨별 프리픽스
    level_prefix = {
        "info": "[Plugin]",
        "warning": "[Plugin][Warning]",
        "error": "[Plugin][Error]",
    }
    
    prefix = level_prefix.get(level, "[Plugin]")
    
    # 플러그인명 추가
    output = f"{prefix}:{plugin_name} {message}"
    
    print(output)


# ============================================================================
# 글로벌 인스턴스
# ============================================================================

# 기본 플러그인 로더 인스턴스
_default_loader: Optional[PluginLoader] = None


def get_plugin_loader(localization_manager=None) -> PluginLoader:
    """
    기본 플러그인 로더 인스턴스 반환 (싱글톤)
    
    Args:
        localization_manager: LocalizationManager 인스턴스
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = PluginLoader(localization_manager=localization_manager)
    elif localization_manager and not _default_loader.localization_manager:
        # Localization manager 설정 (처음 초기화 후)
        _default_loader.localization_manager = localization_manager
    return _default_loader


def init_plugins(localization_manager=None) -> int:
    """
    플러그인 초기화 (모든 플러그인 로드)
    
    Args:
        localization_manager: LocalizationManager 인스턴스
    """
    loader = get_plugin_loader(localization_manager)
    count = loader.load_all_plugins()
    plugin_print("PluginLoader", f"총 {count}개 플러그인 로드됨")
    return count
