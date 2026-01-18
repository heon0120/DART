"""
다국어 지원 (Localization) 모듈
- 번역 파일 관리 (JSON)
- 플러그인별 번역 격리
- 권한 기반 접근 제어
- 자동 Fallback (한국어 → 영어)
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from modules.plugin_loader import plugin_print


# ============================================================================
# 다국어 관리자
# ============================================================================

class LocalizationManager:
    """다국어 (i18n) 관리자"""
    
    # 지원 언어
    SUPPORTED_LANGUAGES = ["ko", "en"]
    DEFAULT_LANGUAGE = "ko"
    FALLBACK_LANGUAGE = "en"
    
    def __init__(self, locales_dir: str = None, system_language: str = None):
        """
        다국어 관리자 초기화
        
        Args:
            locales_dir: 메인 locales 디렉터리 (기본: locales/)
            system_language: 시스템 언어 (기본: ko)
        """
        if locales_dir is None:
            current_dir = Path(__file__).parent.parent
            locales_dir = str(current_dir / "locales")
        
        self.locales_dir = Path(locales_dir)
        self.current_language = system_language or self.DEFAULT_LANGUAGE
        
        # 번역 캐시
        self.translations: Dict[str, Dict[str, Any]] = {}  # {lang: {key: value}}
        
        # 플러그인별 번역 캐시
        self.plugin_translations: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # {plugin_name: {lang: {key: value}}}
        
        # 플러그인별 권한 저장소
        self.plugin_permissions: Dict[str, List[str]] = {}
        # {plugin_name: [granted_permissions]}
        
        # 권한 저장소 (파일 기반 - 재시작 후에도 유지)
        # {plugin_name: {permission: granted}}
        self.permission_storage_dir = Path.home() / ".tdcs"
        self.permission_storage_file = self.permission_storage_dir / "permissions.json"
        
        # 권한 저장소 디렉터리 생성
        self.permission_storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 저장된 권한 로드
        self.permission_cache: Dict[str, Dict[str, bool]] = {}
        self._load_permissions_from_file()
        
        # locales 디렉터리 생성
        self.locales_dir.mkdir(parents=True, exist_ok=True)
        
        # 메인 번역 로드
        self._load_main_translations()
    
    def _load_permissions_from_file(self):
        """저장된 권한 파일에서 로드"""
        if self.permission_storage_file.exists():
            try:
                with open(self.permission_storage_file, 'r', encoding='utf-8') as f:
                    self.permission_cache = json.load(f)
                plugin_print(
                    "LocalizationManager",
                    f"저장된 권한 로드: {self.permission_storage_file}"
                )
            except Exception as e:
                plugin_print(
                    "LocalizationManager",
                    f"[Error] 권한 파일 로드 실패: {str(e)}",
                    level="error"
                )
    
    def _save_permissions_to_file(self):
        """권한을 파일에 저장"""
        try:
            with open(self.permission_storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.permission_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            plugin_print(
                "LocalizationManager",
                f"[Error] 권한 파일 저장 실패: {str(e)}",
                level="error"
            )
    
    def _load_main_translations(self):
        """메인 애플리케이션 번역 파일 로드"""
        for lang in self.SUPPORTED_LANGUAGES:
            lang_dir = self.locales_dir / lang
            if not lang_dir.exists():
                continue
            
            translations = {}
            
            # 각 .json 파일 로드
            for json_file in lang_dir.glob("*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        file_translations = json.load(f)
                        # namespace 추가 (파일명을 prefix로 사용)
                        namespace = json_file.stem
                        for key, value in file_translations.items():
                            translations[f"{namespace}.{key}"] = value
                except Exception as e:
                    plugin_print(
                        "LocalizationManager",
                        f"[Error] 번역 파일 로드 실패: {json_file}",
                        level="error"
                    )
            
            self.translations[lang] = translations
    
    def load_plugin_translations(self, plugin_name: str, plugin_dir: str):
        """
        플러그인 번역 파일 로드
        
        Args:
            plugin_name: 플러그인 이름
            plugin_dir: 플러그인 디렉터리 경로
        """
        plugin_dir = Path(plugin_dir)
        locales_dir = plugin_dir / "locales"
        
        if not locales_dir.exists():
            return  # 번역 파일 없으면 무시
        
        plugin_translations = {}
        
        for lang in self.SUPPORTED_LANGUAGES:
            lang_dir = locales_dir / lang
            if not lang_dir.exists():
                continue
            
            translations = {}
            
            # 각 .json 파일 로드
            for json_file in lang_dir.glob("*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        file_translations = json.load(f)
                        translations.update(file_translations)
                except Exception as e:
                    plugin_print(
                        "LocalizationManager",
                        f"[Error] 플러그인 번역 로드 실패: {plugin_name}",
                        level="error"
                    )
            
            plugin_translations[lang] = translations
        
        if plugin_translations:
            self.plugin_translations[plugin_name] = plugin_translations
            plugin_print(
                "LocalizationManager",
                f"플러그인 번역 로드: {plugin_name}"
            )
    
    def set_language(self, language: str) -> bool:
        """
        현재 언어 설정
        
        Args:
            language: 언어 코드 (ko, en, ...)
        
        Returns:
            성공 여부
        """
        if language in self.SUPPORTED_LANGUAGES:
            self.current_language = language
            return True
        return False
    
    def get_text(
        self,
        key: str,
        plugin_name: str = None,
        default: str = None
    ) -> str:
        """
        번역 텍스트 가져오기
        
        Args:
            key: 번역 키 (예: "common.welcome" 또는 "greeting")
            plugin_name: 플러그인 이름 (None이면 메인 애플리케이션)
            default: 번역 없을 시 기본값
        
        Returns:
            번역된 텍스트 또는 기본값
        """
        # 플러그인 번역 조회
        if plugin_name:
            if not self._check_permission(plugin_name, "read_locales"):
                plugin_print(
                    "LocalizationManager",
                    f"[Error] 권한 없음: {plugin_name}",
                    level="error"
                )
                return default or key
            
            if plugin_name in self.plugin_translations:
                plugin_trans = self.plugin_translations[plugin_name]
                
                # 현재 언어로 조회
                if self.current_language in plugin_trans:
                    if key in plugin_trans[self.current_language]:
                        return plugin_trans[self.current_language][key]
                
                # Fallback: 한국어
                if "ko" in plugin_trans and key in plugin_trans["ko"]:
                    return plugin_trans["ko"][key]
                
                # Fallback: 영어
                if "en" in plugin_trans and key in plugin_trans["en"]:
                    return plugin_trans["en"][key]
        
        else:
            # 메인 애플리케이션 번역 조회
            
            # 현재 언어로 조회
            if self.current_language in self.translations:
                if key in self.translations[self.current_language]:
                    return self.translations[self.current_language][key]
            
            # Fallback: 한국어
            if "ko" in self.translations and key in self.translations["ko"]:
                return self.translations["ko"][key]
            
            # Fallback: 영어
            if "en" in self.translations and key in self.translations["en"]:
                return self.translations["en"][key]
        
        # 모든 Fallback 실패
        return default or key
    
    def _check_permission(self, plugin_name: str, permission: str) -> bool:
        """
        플러그인의 권한 확인 (자신의 번역 읽기는 항상 가능)
        
        Args:
            plugin_name: 플러그인 이름
            permission: 권한 이름
        
        Returns:
            권한 여부
        """
        # 자신의 번역 읽기는 항상 가능
        if permission == "read_locales":
            return True
        
        # 기타 권한 확인
        if plugin_name in self.plugin_permissions:
            return permission in self.plugin_permissions[plugin_name]
        
        return False
    
    def grant_plugin_permission(
        self,
        plugin_name: str,
        permissions: List[str]
    ):
        """
        플러그인 권한 부여
        
        Args:
            plugin_name: 플러그인 이름
            permissions: 권한 리스트
        """
        if plugin_name not in self.plugin_permissions:
            self.plugin_permissions[plugin_name] = []
        
        for perm in permissions:
            if perm not in self.plugin_permissions[plugin_name]:
                self.plugin_permissions[plugin_name].append(perm)
        
        plugin_print(
            "LocalizationManager",
            f"{plugin_name}에 권한 부여: {', '.join(permissions)}"
        )
    
    def deny_plugin_permission(self, plugin_name: str, permission: str):
        """
        플러그인 권한 거부
        
        Args:
            plugin_name: 플러그인 이름
            permission: 권한 이름
        """
        if plugin_name in self.plugin_permissions:
            if permission in self.plugin_permissions[plugin_name]:
                self.plugin_permissions[plugin_name].remove(permission)
        
        plugin_print(
            "LocalizationManager",
            f"{plugin_name}의 권한 거부: {permission}"
        )
    
    def request_plugin_permission(
        self,
        plugin_name: str,
        permissions: List[str],
        reason: str = ""
    ) -> Dict[str, bool]:
        """
        플러그인 권한 요청 (사용자 확인)
        
        Args:
            plugin_name: 플러그인 이름
            permissions: 요청하는 권한 리스트
            reason: 권한 필요 이유
        
        Returns:
            {permission: granted} 딕셔너리
        """
        result = {}
        need_save = False  # 새로운 권한이 추가되었는지 추적
        
        for permission in permissions:
            # 이미 결정된 권한이면 캐시된 결과 사용 (파일에서 로드된 권한 포함)
            if plugin_name in self.permission_cache:
                if permission in self.permission_cache[plugin_name]:
                    result[permission] = self.permission_cache[plugin_name][permission]
                    continue
            
            # 사용자에게 권한 요청
            granted = self._ask_user_permission(
                plugin_name,
                permission,
                reason
            )
            result[permission] = granted
            
            # 캐시에 저장
            if plugin_name not in self.permission_cache:
                self.permission_cache[plugin_name] = {}
            self.permission_cache[plugin_name][permission] = granted
            need_save = True  # 새로운 권한이 추가됨
            
            # 권한 부여
            if granted:
                self.grant_plugin_permission(plugin_name, [permission])
            else:
                self.deny_plugin_permission(plugin_name, permission)
        
        # 새로운 권한이 추가되었으면 파일에 저장
        if need_save:
            self._save_permissions_to_file()
        
        return result
    
    def _ask_user_permission(
        self,
        plugin_name: str,
        permission: str,
        reason: str = ""
    ) -> bool:
        """
        사용자에게 권한 허용 여부 묻기 (콘솔)
        
        Args:
            plugin_name: 플러그인 이름
            permission: 권한 이름
            reason: 이유
        
        Returns:
            사용자 선택
        """
        perm_desc = {
            "read_main_locales": "메인 애플리케이션 번역 읽기",
            "write_locales": "번역 파일 쓰기",
        }
        
        desc = perm_desc.get(permission, permission)
        
        print()
        print("=" * 70)
        print(f"[권한 요청] {plugin_name}")
        print("=" * 70)
        print(f"요청 권한: {desc}")
        if reason:
            print(f"이유: {reason}")
        print()
        
        while True:
            choice = input("이 권한을 허용하시겠습니까? (y/n): ").lower().strip()
            if choice in ('y', 'yes'):
                print("✓ 권한이 부여되었습니다.")
                print("=" * 70)
                return True
            elif choice in ('n', 'no'):
                print("✗ 권한이 거부되었습니다.")
                print("=" * 70)
                return False
            else:
                print("y 또는 n을 입력하세요.")
    
    def get_supported_languages(self) -> List[str]:
        """지원하는 언어 목록 반환"""
        return self.SUPPORTED_LANGUAGES.copy()
    
    def get_current_language(self) -> str:
        """현재 언어 반환"""
        return self.current_language
    
    def get_plugin_permissions(self, plugin_name: str) -> List[str]:
        """플러그인이 가진 권한 조회"""
        return self.plugin_permissions.get(plugin_name, [])


# ============================================================================
# 약자 (Shorthand) 함수
# ============================================================================

_default_manager: Optional[LocalizationManager] = None


def get_localization_manager() -> LocalizationManager:
    """기본 다국어 관리자 인스턴스 반환 (싱글톤)"""
    global _default_manager
    if _default_manager is None:
        _default_manager = LocalizationManager()
    return _default_manager


def _(key: str, plugin_name: str = None, default: str = None) -> str:
    """
    번역 텍스트 가져오기 (약자)
    
    Example:
        message = _("common.welcome")
        plugin_msg = _("greeting", plugin_name="my_plugin")
    """
    manager = get_localization_manager()
    return manager.get_text(key, plugin_name, default)


def set_language(language: str) -> bool:
    """언어 설정"""
    manager = get_localization_manager()
    return manager.set_language(language)


def get_supported_languages() -> List[str]:
    """지원하는 언어 목록"""
    return LocalizationManager.SUPPORTED_LANGUAGES.copy()
