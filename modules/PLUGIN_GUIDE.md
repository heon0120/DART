플러그인 시스템 가이드
====================

TDCS의 플러그인 시스템을 사용하여 기능을 확장하는 방법에 대한 완벽한 가이드입니다.

## 개요

플러그인은 메인 애플리케이션을 수정하지 않고도 새로운 기능을 추가할 수 있게 해줍니다.
데코레이터 기반의 간단하고 직관적인 인터페이스를 제공합니다.

## 플러그인 작성 방법

### 1. 기본 구조

플러그인은 `modules/plugins/` 디렉터리에 `.py` 파일로 작성합니다.
`@plugin` 데코레이터를 사용하여 플러그인을 정의합니다.

```python
from modules.plugin_loader import plugin, plugin_print

@plugin(
    name="my_plugin",           # 플러그인 이름 (필수, 유일해야 함)
    stage="pre-main",           # 실행 시점 (선택, 기본값: "pre-main")
    priority=1,                 # 우선순위 (선택, 기본값: 0, 높을수록 먼저 실행)
    enabled=True,               # 활성화 여부 (선택, 기본값: True)
    description="설명",         # 플러그인 설명 (선택)
    version="1.0.0"             # 버전 (선택, 기본값: "1.0.0")
)
def my_plugin_main(context=None, config=None):
    """
    플러그인 메인 함수
    
    Args:
        context (dict): 플러그인 간 데이터 공유용 딕셔너리
        config (dict): 플러그인 설정값
    
    Returns:
        결과값 (자유로운 형태 가능)
    """
    plugin_print("my_plugin", "작업 중...")
    return {"status": "success"}
```

### 2. 실행 시점 (Stage)

플러그인은 다음 단계에서 자동으로 실행됩니다:

- **"pre-main"**: 애플리케이션 시작 직후, 스플래시 화면 표시 전
  - 사용 예: 환경 설정, 초기 데이터 로드
  
- **"splash"**: 스플래시 화면 표시 중
  - 사용 예: 리소스 로드, 데이터베이스 초기화
  
- **"post-main"**: 메인 윈도우 표시 후
  - 사용 예: 추가 초기화, 이벤트 등록

### 3. 우선순위 (Priority)

같은 stage 내에서 여러 플러그인이 있을 경우, `priority` 값이 높을수록 먼저 실행됩니다.

```python
@plugin(name="plugin_a", stage="splash", priority=2)
def plugin_a(context=None, config=None):
    plugin_print("plugin_a", "먼저 실행됨")

@plugin(name="plugin_b", stage="splash", priority=1)
def plugin_b(context=None, config=None):
    plugin_print("plugin_b", "나중에 실행됨")
```

### 4. 출력 함수

플러그인에서 출력하려면 `plugin_print()` 함수를 사용합니다:

```python
from modules.plugin_loader import plugin_print

plugin_print("plugin_name", "일반 메시지")
plugin_print("plugin_name", "경고 메시지", level="warning")
plugin_print("plugin_name", "에러 메시지", level="error")
```

출력 형식: `[Plugin]:plugin_name message`

### 5. 컨텍스트 (Context)

플러그인 간 데이터를 공유하려면 `context` 딕셔너리를 사용합니다:

```python
# Plugin A에서 데이터 추가
@plugin(name="plugin_a", stage="pre-main")
def plugin_a(context=None, config=None):
    if context is not None:
        context['shared_data'] = "공유할 데이터"

# Plugin B에서 데이터 사용
@plugin(name="plugin_b", stage="splash")
def plugin_b(context=None, config=None):
    if context is not None:
        data = context.get('shared_data', '기본값')
        plugin_print("plugin_b", f"받은 데이터: {data}")
```

### 6. 설정값 (Config)

플러그인에 설정값을 전달하려면 `config` 딕셔너리를 사용합니다:

```python
@plugin(name="my_plugin")
def my_plugin(context=None, config=None):
    if config:
        timeout = config.get('timeout', 30)
        debug = config.get('debug', False)
        plugin_print("my_plugin", f"타임아웃: {timeout}초, 디버그: {debug}")
```

main.py에서 설정값 전달:

```python
from modules.plugin_loader import get_plugin_loader

plugin_loader = get_plugin_loader()
config = {
    'my_plugin': {'timeout': 60, 'debug': True}
}
plugin_loader.run_plugins("splash", context=plugin_context, config=config)
```

## 플러그인 예제

### 예제 1: 간단한 초기화 플러그인

```python
from modules.plugin_loader import plugin, plugin_print

@plugin(
    name="simple_init",
    stage="pre-main",
    description="간단한 초기화 작업"
)
def simple_init(context=None, config=None):
    plugin_print("simple_init", "초기화 시작")
    # 초기화 작업...
    plugin_print("simple_init", "초기화 완료")
    return {"initialized": True}
```

### 예제 2: 컨텍스트를 사용한 플러그인

```python
from modules.plugin_loader import plugin, plugin_print

@plugin(name="data_provider", stage="pre-main", priority=1)
def data_provider(context=None, config=None):
    if context is not None:
        context['database'] = "mock_db_instance"
        plugin_print("data_provider", "데이터베이스 전달")

@plugin(name="data_consumer", stage="splash", priority=0)
def data_consumer(context=None, config=None):
    if context is not None and 'database' in context:
        db = context['database']
        plugin_print("data_consumer", f"데이터베이스 사용: {db}")
```

### 예제 3: 에러 처리가 있는 플러그인

```python
from modules.plugin_loader import plugin, plugin_print

@plugin(name="error_example", stage="splash")
def error_example(context=None, config=None):
    try:
        # 작업...
        if not context:
            raise ValueError("Context가 없음")
        plugin_print("error_example", "작업 완료")
    except Exception as e:
        plugin_print("error_example", f"에러 발생: {str(e)}", level="error")
        # 에러 처리...
```

## API 레퍼런스

### @plugin 데코레이터

```python
@plugin(
    name: str,                  # 플러그인 이름 (필수)
    stage: str = "pre-main",    # 실행 시점
    priority: int = 0,          # 우선순위 (높을수록 먼저)
    enabled: bool = True,       # 활성화 여부
    description: str = "",      # 설명
    version: str = "1.0.0"      # 버전
)
```

### plugin_print() 함수

```python
plugin_print(
    plugin_name: str,           # 플러그인 이름
    message: str,               # 출력 메시지
    level: str = "info"         # "info", "warning", "error"
)
```

출력 형식:
- Info: `[Plugin]:plugin_name message`
- Warning: `[Plugin][Warning]:plugin_name message`
- Error: `[Plugin][Error]:plugin_name message`

### PluginLoader 클래스

```python
from modules.plugin_loader import get_plugin_loader

loader = get_plugin_loader()

# 플러그인 로드
count = loader.load_all_plugins()  # -> int (로드된 개수)

# 플러그인 실행
results = loader.run_plugins(
    stage: str,                 # "pre-main", "splash", "post-main"
    context: dict = None,       # 플러그인 간 데이터 공유
    config: dict = None         # 플러그인 설정값
)  # -> dict (실행 결과)

# 플러그인 정보 조회
info = loader.get_plugin_info()  # 모든 플러그인
info = loader.get_plugin_info("plugin_name")  # 특정 플러그인

# 플러그인 활성/비활성화
loader.enable_plugin("plugin_name")
loader.disable_plugin("plugin_name")
```

## 성능 고려사항

1. **Heavy 작업은 "post-main" stage에서**: 스플래시 화면이 표시되는 동안 오래 걸리는 작업을 하지 않도록 주의하세요.

2. **예외 처리**: 플러그인 내 예외가 발생하면 자동으로 로그되고, 다른 플러그인 실행에 영향을 주지 않습니다.

3. **컨텍스트 공유는 신중하게**: 플러그인 간 데이터 공유는 우선순위를 고려하여 설계하세요.

## 문제 해결

### 플러그인이 로드되지 않음
- 파일이 `modules/plugins/` 디렉터리에 있는지 확인
- `@plugin` 데코레이터가 있는지 확인
- 파일명에 `__init__.py` 제외 다른 이름 확인

### 플러그인이 실행되지 않음
- `enabled=False` 설정 확인
- `stage` 이름이 올바른지 확인
- 콘솔 출력 확인 (에러 메시지)

### 플러그인 실행 순서가 예상과 다름
- `priority` 값 확인 (높을수록 먼저)
- 같은 priority이면 파일명 순서로 로드됨

## 다음 단계

1. `modules/plugins/` 디렉터리에 새 `.py` 파일 생성
2. 위의 기본 구조를 참고하여 플러그인 작성
3. `@plugin` 데코레이터 추가
4. 메인 앱 실행 후 콘솔에서 플러그인 메시지 확인

