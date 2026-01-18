# main.py UI 지역화 가이드

## 개요

main.py의 모든 UI 텍스트(버튼, 레이블, 메시지 박스 등)가 지역화되어 있습니다.

- **지원 언어**: 한국어 (ko), 영어 (en)
- **번역 파일 위치**: `locales/{lang}/main.json`
- **자동 Fallback**: ko → en

## 번역 파일 구조

### 한국어 번역 (`locales/ko/main.json`)
```json
{
  "window.title": "DART - Drone Analytics & Routing Tool",
  "window.waypoint_editor.title": "웨이포인트 편집",
  "label.waypoint_name": "웨이포인트 이름",
  "button.save": "SAVE",
  "button.convert": "변환",
  ...
}
```

### 영어 번역 (`locales/en/main.json`)
```json
{
  "window.title": "DART - Drone Analytics & Routing Tool",
  "window.waypoint_editor.title": "WAYPOINT EDITOR",
  "label.waypoint_name": "WAYPOINT NAME",
  "button.save": "SAVE",
  "button.convert": "CONVERT",
  ...
}
```

## 코드에서 번역 사용하기

### 메인 윈도우 (DARTMainWindow)

메인 윈도우에는 `self.loc` (LocalizationManager) 인스턴스가 있습니다.

```python
# 번역 가져오기
title = self.loc.get_text("main.window.title")
label = self.loc.get_text("main.label.waypoint_name")

# 항상 Fallback 제공
title = self.loc.get_text("main.window.title") if self.loc else "DART - Drone Analytics & Routing Tool"
```

### 웨이포인트 편집 다이얼로그 (WaypointEditDialog)

생성자에서 localization_manager를 받아야 합니다:

```python
def __init__(self, waypoint: Waypoint, parent=None, localization_manager=None):
    super().__init__(parent)
    self.waypoint = waypoint
    self.loc = localization_manager
    self.init_ui()

def init_ui(self):
    window_title = self.loc.get_text("main.window.waypoint_editor.title") if self.loc else "WAYPOINT EDITOR"
    self.setWindowTitle(window_title)
```

### 메인 어플리케이션 초기화

```python
# main.py의 main 함수에서
localization_manager = LocalizationManager()
localization_manager.set_language("ko")  # 또는 "en"

window = DARTMainWindow(splash, localization_manager)
```

## 번역 키 목록

### 윈도우 타이틀
- `main.window.title` - 메인 윈도우 제목
- `main.window.waypoint_editor.title` - 웨이포인트 편집 다이얼로그 제목

### 레이블
- `main.label.waypoint_name` - 웨이포인트 이름
- `main.label.nato_phonetic` - NATO 포네틱
- `main.label.latitude` - 위도
- `main.label.longitude` - 경도
- `main.label.mgrs` - MGRS 좌표
- `main.label.altitude` - 고도
- `main.label.task` - 임무
- `main.label.speed` - 속도
- `main.label.target_eta` - 목표 ETA
- `main.label.mission_name` - 미션 이름
- `main.label.mission_details` - 미션 상세정보
- `main.label.id` - ID
- `main.label.name` - 이름
- `main.label.created` - 생성일
- `main.label.waypoints` - 웨이포인트
- `main.label.waypoint_list` - 웨이포인트 목록
- `main.label.start_waypoint` - 시작 웨이포인트
- `main.label.end_waypoint` - 종료 웨이포인트

### 버튼
- `main.button.convert` - 변환
- `main.button.delete` - 삭제
- `main.button.cancel` - 취소
- `main.button.save` - 저장
- `main.button.new_mission` - 새 미션 추가
- `main.button.insert_waypoint` - 웨이포인트 삽입
- `main.button.local_save` - 로컬 저장
- `main.button.export_json` - JSON 내보내기
- `main.button.export_csv` - CSV 내보내기
- `main.button.create_mission` - 미션 생성
- `main.button.mgrs_grid` - MGRS 그리드
- `main.button.coords` - 좌표
- `main.button.control_zone` - 관제권

### 다이얼로그
- `main.dialog.confirm` - 확인
- `main.dialog.delete_confirm` - 정말 삭제하시겠습니까?
- `main.dialog.warning` - 경고
- `main.dialog.success` - 성공
- `main.dialog.create_new_mission` - 새 미션 생성
- `main.dialog.insert_waypoint` - 웨이포인트 삽입

### 메시지
- `main.message.mission_not_selected` - 먼저 미션을 선택하세요
- `main.message.waypoint_not_found` - 웨이포인트를 찾을 수 없습니다
- `main.message.waypoint_inserted` - 웨이포인트가 {wp1}과 {wp2} 사이에 삽입되었습니다
- `main.message.waypoint_min_required` - 웨이포인트가 2개 이상 필요합니다

### 상태 메시지
- `main.status.initializing_main_window` - 메인 창 초기화...
- `main.status.connecting_database` - 데이터베이스 연결...
- `main.status.creating_ui` - UI 컴포넌트 생성...
- `main.status.loading_missions` - 미션 데이터 로딩...

### Placeholder
- `main.placeholder.waypoint_name` - 예: Alpha, Waypoint-1
- `main.placeholder.eta` - HH:MM (예: 14:30)

## 언어 변경

### 런타임에 언어 변경

```python
localization_manager = get_localization_manager()
localization_manager.set_language("en")  # 영어로 변경
```

### 시스템 기본 언어

main.py에서:
```python
localization_manager.set_language("ko")  # 기본값: 한국어
```

## 새로운 번역 추가

1. `locales/ko/main.json`에 새 키 추가
2. `locales/en/main.json`에 동일 키 추가
3. main.py에서 사용:
   ```python
   text = self.loc.get_text("main.new_key") if self.loc else "Default Text"
   ```

## 테스트

번역 파일이 제대로 로드되는지 테스트:

```bash
python test_main_localization.py
```

## 참고

- LocalizationManager는 플러그인별 번역도 지원합니다
- 권한 기반 접근 제어로 플러그인이 메인 번역에 접근할 수 없도록 제한 가능
- 모든 번역은 UTF-8로 인코딩되어 있습니다
