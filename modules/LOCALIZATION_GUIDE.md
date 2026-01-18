# 다국어 지원 (Localization) 가이드

## 개요

TDCS 애플리케이션은 완벽한 다국어 지원 시스템을 제공합니다. 

**주요 특징:**
- 한국어 및 영어 지원 (Fallback: 한국어 → 영어)
- 플러그인별 독립적 번역 관리
- 권한 기반 번역 접근 제어
- 런타임 언어 전환 가능
- JSON 기반 간단한 번역 파일 구조

## 디렉터리 구조

```
locales/                              # 메인 애플리케이션 번역
├── ko/                               # 한국어
│   ├── common.json                  # 공통 텍스트
│   └── splash.json                  # 스플래시 화면
├── en/                               # 영어
│   ├── common.json
│   └── splash.json
└── ...

modules/plugins/
├── sample_plugin/
│   ├── plugin.py
│   └── locales/                     # 플러그인 번역
│       ├── ko/
│       │   └── translations.json    # 모든 번역을 하나의 파일에
│       └── en/
│           └── translations.json
```

## 메인 애플리케이션에서 사용하기

### 1. 기본 사용법

```python
from modules.localization import get_localization_manager, _

# 방식 1: 함수 호출
i18n = get_localization_manager()
message = i18n.get_text("common.welcome")

# 방식 2: 약자 함수 사용 (권장)
message = _("common.welcome")
```

### 2. 언어 선택

```python
from modules.localization import set_language

# 언어 설정
set_language("en")  # 영어로 변경

# 지원하는 언어 목록 확인
from modules.localization import get_supported_languages
languages = get_supported_languages()  # ["ko", "en"]
```

### 3. 번역 키 구조

메인 애플리케이션의 번역 파일은 namespace를 사용합니다:

```json
// locales/ko/common.json
{
  "welcome": "환영합니다",
  "title": "TDCS"
}
```

사용할 때는 `파일명.키` 형식으로 접근:

```python
# locales/ko/common.json의 "welcome" 사용
message = _("common.welcome")

# locales/ko/splash.json의 "loading_splash" 사용
message = _("splash.loading_splash")
```

### 4. 기본값 제공

번역이 없을 경우 기본값을 지정할 수 있습니다:

```python
message = _("common.unknown_key", default="Unknown")
```

## 플러그인에서 사용하기

### 1. 플러그인 번역 파일 구조

플러그인은 namespace 없이 번역 키만 사용합니다:

```json
// modules/plugins/my_plugin/locales/ko/translations.json
{
  "greeting": "안녕하세요!",
  "processing": "처리 중..."
}
```

### 2. 플러그인 코드에서 사용

```python
from modules.plugin_loader import plugin, plugin_print
from modules.localization import get_localization_manager

@plugin(name="my_plugin", stage="splash")
def my_plugin_main(context=None, config=None):
    i18n = get_localization_manager()
    
    # 자신의 번역 사용 (항상 가능)
    message = i18n.get_text("greeting", plugin_name="my_plugin")
    plugin_print("my_plugin", message)
    
    # 메인 애플리케이션 번역 사용 (권한 필요)
    main_msg = i18n.get_text("common.welcome", plugin_name="my_plugin")
```

### 3. 메인 애플리케이션 번역 접근 권한

플러그인이 메인 애플리케이션 번역에 접근하려면 권한을 요청해야 합니다:

```python
@plugin(
    name="my_plugin",
    stage="splash",
    permissions=["read_main_locales"]  # 권한 요청
)
def my_plugin_main(context=None, config=None):
    # ...
```

사용자가 권한을 승인하면 메인 번역에 접근 가능:

```python
i18n = get_localization_manager()
main_text = i18n.get_text("common.title", plugin_name="my_plugin")
```

## 번역 파일 작성

### 메인 애플리케이션 번역

```json
// locales/ko/common.json
{
  "welcome": "환영합니다",
  "title": "TDCS (전술 무인항공기 제어 시스템)",
  "ok": "확인",
  "cancel": "취소",
  "yes": "예",
  "no": "아니오",
  "error": "오류",
  "success": "성공"
}
```

### 플러그인 번역

```json
// modules/plugins/my_plugin/locales/ko/translations.json
{
  "greeting": "안녕하세요!",
  "processing": "처리 중...",
  "complete": "완료됨",
  "error_message": "오류가 발생했습니다."
}
```

## API 레퍼런스

### LocalizationManager

```python
from modules.localization import LocalizationManager

manager = LocalizationManager(
    locales_dir="locales",       # 메인 번역 디렉터리
    system_language="ko"          # 기본 언어
)

# 번역 텍스트 가져오기
text = manager.get_text(
    key="common.welcome",         # 번역 키
    plugin_name=None,             # None이면 메인, 플러그인명 가능
    default="기본값"               # 번역 없을 시 기본값
)

# 언어 설정
manager.set_language("en")

# 플러그인 번역 로드
manager.load_plugin_translations(
    "my_plugin",
    "plugins/my_plugin"
)

# 권한 관리
manager.grant_plugin_permission("my_plugin", ["read_main_locales"])
manager.deny_plugin_permission("my_plugin", "read_main_locales")

# 권한 요청 (사용자 확인)
results = manager.request_plugin_permission(
    "my_plugin",
    ["read_main_locales"],
    reason="메인 타이틀 텍스트 필요"
)

# 지원 언어 확인
languages = manager.get_supported_languages()  # ["ko", "en"]

# 현재 언어 확인
current = manager.get_current_language()  # "ko"
```

### 약자 함수

```python
from modules.localization import _, set_language, get_supported_languages

# 번역 텍스트 가져오기 (권장)
text = _("common.welcome")
text = _("greeting", plugin_name="my_plugin")
text = _("key", default="기본값")

# 언어 설정
set_language("en")

# 지원 언어 목록
languages = get_supported_languages()
```

## 권한 시스템

### 권한 종류

현재 지원되는 권한:
- `"read_main_locales"`: 메인 애플리케이션 번역 읽기
- `"write_locales"`: 번역 파일 쓰기 (예약)

### 권한 흐름

1. **플러그인 로드 시**
   ```python
   @plugin(name="my_plugin", permissions=["read_main_locales"])
   ```

2. **플러그인 로더가 권한 감지**
   - LocalizationManager에 권한 요청

3. **사용자에게 승인 여부 확인**
   ```
   ================================================== 70자
   [권한 요청] my_plugin
   ==================================================
   요청 권한: 메인 애플리케이션 번역 읽기
   이유: 메인 타이틀 텍스트 필요
   
   이 권한을 허용하시겠습니까? (y/n): 
   ```

4. **권한 결정 저장 (캐싱)**
   - 다음 실행부터 같은 질문을 하지 않음

5. **플러그인 실행**
   - 승인된 권한으로 번역 접근 가능

### 권한 거부 시

플러그인이 권한 없이 접근 시도:

```python
# 권한이 없으면 기본값 또는 키 자체 반환
text = i18n.get_text("common.welcome", plugin_name="my_plugin")
# → 권한 없음 → "common.welcome" 반환
```

## Fallback 메커니즘

번역 순서:

1. 현재 언어의 번역 (예: 한국어)
2. Fallback 언어 1: 한국어 (메인 애프)
3. Fallback 언어 2: 영어
4. 모든 번역 실패 → 기본값 또는 키 자체 반환

```python
# 현재 언어가 영어인 경우
text = _("splash.loading_splash")

# 번역 시도 순서:
# 1. locales/en/splash.json의 "loading_splash" 
# 2. locales/ko/splash.json의 "loading_splash"
# 3. 없으면 "splash.loading_splash" 반환
```

## 새 언어 추가

1. **locales 디렉터리에 언어 폴더 생성**
   ```
   locales/ja/  # 일본어
   ```

2. **번역 파일 추가**
   ```
   locales/ja/common.json
   locales/ja/splash.json
   ```

3. **LocalizationManager의 SUPPORTED_LANGUAGES 수정**
   ```python
   SUPPORTED_LANGUAGES = ["ko", "en", "ja"]
   ```

4. **사용**
   ```python
   set_language("ja")
   ```

## 문제 해결

### 번역이 보이지 않을 때

1. **번역 파일 위치 확인**
   - `locales/언어/파일명.json` 구조 맞는지 확인

2. **번역 키 확인**
   - 파일명 포함 (예: `common.welcome`)
   - 오타 확인

3. **현재 언어 확인**
   - `get_localization_manager().get_current_language()`

### 플러그인 번역 로드 안 될 때

1. **플러그인 디렉터리 구조 확인**
   ```
   plugins/my_plugin/
   ├── plugin.py
   └── locales/
       ├── ko/translations.json
       └── en/translations.json
   ```

2. **JSON 파일 유효성 확인**
   - JSON 포맷 정상 여부

### 권한 요청 반복될 때

1. **권한 캐시 확인**
   - 콘솔에서 "✓ 승인" 또는 "✗ 거부" 확인

2. **플러그인 경로 확인**
   - plugins 디렉터리 위치 정상 여부

## 예제

### 예제 1: 간단한 메인 앱 다국어

```python
from modules.localization import _, set_language

# 한국어 사용
print(_("common.welcome"))  # "환영합니다"

# 영어로 변경
set_language("en")
print(_("common.welcome"))  # "Welcome"
```

### 예제 2: 플러그인 다국어 지원

```python
from modules.plugin_loader import plugin, plugin_print
from modules.localization import get_localization_manager

@plugin(
    name="i18n_example",
    stage="splash",
    permissions=["read_main_locales"]
)
def plugin_main(context=None, config=None):
    i18n = get_localization_manager()
    
    # 자신의 번역
    greeting = i18n.get_text("greeting", plugin_name="i18n_example")
    plugin_print("i18n_example", greeting)
    
    # 메인 번역 (권한 있으면)
    title = i18n.get_text("common.title", plugin_name="i18n_example")
    plugin_print("i18n_example", title)
```

### 예제 3: 런타임 언어 전환

```python
from modules.localization import set_language, get_localization_manager

i18n = get_localization_manager()

# 한국어로 시작
set_language("ko")
print(i18n.get_text("common.welcome"))  # "환영합니다"

# 사용자 설정에 따라 언어 전환
user_language = get_user_preference()  # "en"
set_language(user_language)
print(i18n.get_text("common.welcome"))  # "Welcome"
```

## 다음 단계

1. **메인 애플리케이션 모든 텍스트 번역**
   - UI 텍스트를 locales 파일로 옮기기

2. **플러그인에 번역 추가**
   - 각 플러그인의 locales 폴더에 번역 파일 작성

3. **사용자 언어 선택 UI 추가**
   - 설정에서 언어 변경 가능하게

4. **추가 언어 지원**
   - 일본어, 중국어 등 확장

5. **번역 관리 도구**
   - 번역 파일 일괄 관리 스크립트 개발

Happy coding! 🌍
