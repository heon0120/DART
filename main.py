import sys
import json
import sqlite3
import base64
import math
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import uuid

try:
    from geopy.distance import distance
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "geopy"])
    from geopy.distance import distance

try:
    import mgrs
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "mgrs"])
    import mgrs

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QTabWidget, QDialog, QLineEdit, QSpinBox, QDialogButtonBox,
    QMessageBox, QFileDialog, QComboBox, QFormLayout
)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot, pyqtProperty
from PyQt5.QtGui import QFont
from PyQt5.QtWebChannel import QWebChannel

from modules.splash import show_splash_screen
from modules.plugin_loader import init_plugins, get_plugin_loader
from modules.localization import LocalizationManager, get_localization_manager


# ============================================================================
# 다국어 및 플러그인 초기화
# ============================================================================

# LocalizationManager 초기화
localization_manager = LocalizationManager()

# 언어 선택 (시스템 기본값은 한국어, 필요시 변경)
# 향후 사용자 설정에서 변경 가능
localization_manager.set_language("ko")

# 플러그인 초기화 (localization manager 전달)
plugin_context = {}
init_plugins(localization_manager)
plugin_loader = get_plugin_loader(localization_manager)


# ============================================================================
# 데이터 모델
# ============================================================================

@dataclass
class Waypoint:
    lat: float
    lon: float
    alt: float = 100
    task_code: str = "CRUISE"
    wp_id: str = None
    speed: float = 50.0  # Default speed in km/h
    eta: Optional[str] = None  # ETA as a string
    distance: float = 0.0  # Distance from previous waypoint in km
    name: str = None  # Waypoint name (can use NATO phonetic or custom)

    def __post_init__(self):
        if self.wp_id is None:
            self.wp_id = str(uuid.uuid4())[:8]
        if self.name is None:
            self.name = ""

    def to_dict(self):
        return {
            'lat': self.lat,
            'lon': self.lon,
            'alt': self.alt,
            'task_code': self.task_code,
            'wp_id': self.wp_id,
            'speed': self.speed,
            'eta': self.eta,
            'distance': self.distance,
            'name': self.name
        }


@dataclass
class Mission:
    mission_id: str
    mission_name: str
    waypoints: List[Waypoint]
    created_at: str = None
    last_saved_at: str = None  # Track last save time

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.last_saved_at is None:
            self.last_saved_at = self.created_at


# ============================================================================
# 데이터베이스
# ============================================================================

class MissionDatabase:
    def __init__(self, db_path: str = "missions.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 기존 테이블 생성 코드
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS missions
                       (
                           mission_id
                           TEXT
                           PRIMARY
                           KEY,
                           mission_name
                           TEXT
                           NOT
                           NULL,
                           created_at
                           TIMESTAMP,
                           updated_at
                           TIMESTAMP
                       )
                       """)

        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS waypoints
                       (
                           wp_id
                           TEXT
                           PRIMARY
                           KEY,
                           mission_id
                           TEXT
                           NOT
                           NULL,
                           lat
                           REAL
                           NOT
                           NULL,
                           lon
                           REAL
                           NOT
                           NULL,
                           alt
                           REAL,
                           task_code
                           TEXT,
                           sequence_order
                           INTEGER,
                           speed
                           REAL
                           DEFAULT
                           50.0,
                           eta
                           TEXT,
                           name
                           TEXT,
                           FOREIGN
                           KEY
                       (
                           mission_id
                       ) REFERENCES missions
                       (
                           mission_id
                       )
                           )
                       """)

        # 마이그레이션: speed 및 eta 열 추가
        try:
            cursor.execute("ALTER TABLE waypoints ADD COLUMN speed REAL DEFAULT 50.0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE waypoints ADD COLUMN eta TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE waypoints ADD COLUMN name TEXT")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        conn.close()

    def save_mission(self, mission: Mission):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        mission.last_saved_at = datetime.now().isoformat()

        cursor.execute(
            "INSERT OR REPLACE INTO missions (mission_id, mission_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (mission.mission_id, mission.mission_name, mission.created_at, mission.last_saved_at)
        )

        cursor.execute("DELETE FROM waypoints WHERE mission_id = ?", (mission.mission_id,))

        for i, wp in enumerate(mission.waypoints):
            cursor.execute(
                "INSERT INTO waypoints (wp_id, mission_id, lat, lon, alt, task_code, sequence_order, speed, eta, name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (wp.wp_id, mission.mission_id, wp.lat, wp.lon, wp.alt, wp.task_code, i, wp.speed, wp.eta, wp.name)
            )

        conn.commit()
        conn.close()

        # Emit signal to update UI
        if hasattr(self, 'mission_updated'):
            self.mission_updated.emit(mission)

    def load_missions(self) -> List[Mission]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT mission_id, mission_name, created_at FROM missions")
        missions = []

        for mission_id, mission_name, created_at in cursor.fetchall():
            cursor.execute(
                "SELECT wp_id, lat, lon, alt, task_code, speed, eta, name FROM waypoints WHERE mission_id = ? ORDER BY sequence_order",
                (mission_id,)
            )

            waypoints = []
            for row in cursor.fetchall():
                speed_val = row[5] if len(row) > 5 and row[5] is not None else 50.0
                eta_val = row[6] if len(row) > 6 else None
                name_val = row[7] if len(row) > 7 else ""
                waypoints.append(
                    Waypoint(lat=row[1], lon=row[2], alt=row[3], task_code=row[4], wp_id=row[0], speed=speed_val,
                             eta=eta_val, name=name_val))

            mission = Mission(mission_id, mission_name, waypoints, created_at)
            missions.append(mission)

        conn.close()
        return missions


# ============================================================================
# MGRS 좌표 변환
# ============================================================================

class MGRSConverter:
    """MGRS (Military Grid Reference System) 좌표 변환"""

    @staticmethod
    def lat_lon_to_mgrs(lat: float, lon: float) -> str:
        """Convert latitude/longitude to MGRS."""
        try:
            m = mgrs.MGRS()
            mgrs_str = m.toMGRS(lat, lon, MGRSPrecision=5)
            return mgrs_str
        except Exception as e:
            return f"Error: {str(e)}"

    @staticmethod
    def mgrs_to_lat_lon(mgrs_str: str) -> tuple:
        """Convert MGRS to latitude/longitude."""
        try:
            m = mgrs.MGRS()
            lat, lon = m.toLatLon(mgrs_str)
            return (lat, lon)
        except Exception as e:
            return (None, None)


# ============================================================================
# NATO 포네틱 코드 변환
# ============================================================================

class NATOPhoneticConverter:
    PHONETIC_ALPHABET = {
        'A': 'Alpha', 'B': 'Bravo', 'C': 'Charlie', 'D': 'Delta',
        'E': 'Echo', 'F': 'Foxtrot', 'G': 'Golf', 'H': 'Hotel',
        'I': 'India', 'J': 'Juliett', 'K': 'Kilo', 'L': 'Lima',
        'M': 'Mike', 'N': 'November', 'O': 'Oscar', 'P': 'Papa',
        'Q': 'Quebec', 'R': 'Romeo', 'S': 'Sierra', 'T': 'Tango',
        'U': 'Uniform', 'V': 'Victor', 'W': 'Whiskey', 'X': 'Xray',
        'Y': 'Yankee', 'Z': 'Zulu'
    }

    @staticmethod
    def to_phonetic(text: str) -> str:
        """Convert text to NATO phonetic alphabet."""
        result = []
        for char in text.upper():
            if char in NATOPhoneticConverter.PHONETIC_ALPHABET:
                result.append(NATOPhoneticConverter.PHONETIC_ALPHABET[char])
            elif char == ' ':
                result.append(' ')
            elif char.isdigit():
                result.append(char)
        return ' '.join(result)

    @staticmethod
    def get_phonetic_for_index(index: int) -> str:
        """Get phonetic code for waypoint index (A, B, C, ... Z, AA, AB, ...)."""
        result = ""
        index += 1  # 1-based indexing
        while index > 0:
            index -= 1
            result = NATOPhoneticConverter.PHONETIC_ALPHABET[chr(ord('A') + (index % 26))] + (
                ' ' + result if result else '')
            index //= 26
        return result.strip()


class MilitarySymbolGenerator:
    COLORS = {
        'RECON': '#00d1b2',  # Turquoise
        'STRIKE': '#ff3860',  # Red
        'RALLY': '#48c774',  # Green
        'LANDING': '#ffdd57',  # Yellow
        'TAKE_OFF': '#209cee',  # Blue
        'CRUISE': '#e0e0e0',  # White/Grey
        'INFANTRY': '#3273dc',  # Blue
        'ARMOR': '#ffdd57',  # Yellow
        'ARTILLERY': '#ff3860',  # Red
        'AIR': '#209cee',  # Cyan
        'MEDEVAC': '#ffffff',  # White
    }

    @staticmethod
    def get_color(task_code: str) -> str:
        return MilitarySymbolGenerator.COLORS.get(task_code, '#7a7a7a')

    @staticmethod
    def create_svg(task_code: str, size: int = 40) -> str:
        color = MilitarySymbolGenerator.get_color(task_code)
        padding = 4
        s = size - (padding * 2)
        center = size // 2

        # 기본 프레임 및 내부 심볼 정의
        symbols = {
            'RECON': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <rect x="{padding}" y="{padding}" width="{s}" height="{s}" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <line x1="{padding}" y1="{padding}" x2="{size - padding}" y2="{size - padding}" stroke="#121212" stroke-width="2"/>
                </svg>
            """,
            'STRIKE': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <polygon points="{center},{padding} {size - padding},{center} {center},{size - padding} {padding},{center}" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <path d="M{center - 5},{center - 5} L{center + 5},{center + 5} M{center + 5},{center - 5} L{center - 5},{center + 5}" stroke="#121212" stroke-width="3"/>
                </svg>
            """,
            'RALLY': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <rect x="{padding}" y="{padding}" width="{s}" height="{s}" rx="2" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <circle cx="{center}" cy="{center}" r="4" fill="#121212"/>
                </svg>
            """,
            'LANDING': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="{center}" cy="{center}" r="{s // 2}" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <path d="M{center - 8},{center + 4} L{center},{center - 8} L{center + 8},{center + 4}" fill="none" stroke="#121212" stroke-width="3" transform="rotate(180, {center}, {center})"/>
                </svg>
            """,
            'TAKE_OFF': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="{center}" cy="{center}" r="{s // 2}" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <path d="M{center - 8},{center + 4} L{center},{center - 8} L{center + 8},{center + 4}" fill="none" stroke="#121212" stroke-width="3"/>
                </svg>
            """,
            'CRUISE': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="{center}" cy="{center}" r="{s // 2}" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <path d="M{center - 8},{center} L{center + 8},{center} M{center + 2},{center - 6} L{center + 8},{center} L{center + 2},{center + 6}" fill="none" stroke="#121212" stroke-width="2"/>
                </svg>
            """,
            'INFANTRY': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <rect x="{padding}" y="{padding}" width="{s}" height="{s}" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <line x1="{padding}" y1="{padding}" x2="{size - padding}" y2="{size - padding}" stroke="#121212" stroke-width="1.5"/>
                    <line x1="{size - padding}" y1="{padding}" x2="{padding}" y2="{size - padding}" stroke="#121212" stroke-width="1.5"/>
                </svg>
            """,
            'ARMOR': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <rect x="{padding}" y="{padding}" width="{s}" height="{s}" rx="{s // 2}" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <ellipse cx="{center}" cy="{center}" rx="{s // 3}" ry="{s // 6}" fill="none" stroke="#121212" stroke-width="2"/>
                </svg>
            """,
            'ARTILLERY': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <rect x="{padding}" y="{padding}" width="{s}" height="{s}" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <circle cx="{center}" cy="{center}" r="4" fill="#121212"/>
                </svg>
            """,
            'AIR': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <path d="M{padding},{center} Q{center},{padding} {size - padding},{center} Q{center},{size - padding} {padding},{center}" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <path d="M{center - 10},{center} L{center + 10},{center}" stroke="#121212" stroke-width="2"/>
                </svg>
            """,
            'MEDEVAC': f"""
                <svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
                    <rect x="{padding}" y="{padding}" width="{s}" height="{s}" fill="{color}" stroke="#121212" stroke-width="2"/>
                    <path d="M{center}, {padding + 4} L{center}, {size - padding - 4} M{padding + 4}, {center} L{size - padding - 4}, {center}" stroke="#ff3860" stroke-width="4"/>
                </svg>
            """
        }

        return symbols.get(task_code, symbols['RECON'])


# ============================================================================
# Leaflet.js 기반 맵 뷰
# ============================================================================

class TacticalMapView(QWebEngineView):
    waypoint_added = pyqtSignal(float, float)
    waypoint_deleted = pyqtSignal(str)  # wp_id
    waypoint_updated = pyqtSignal(str, float, str, float)  # wp_id, alt, task_code, speed
    waypoint_moved = pyqtSignal(str, float, float)  # wp_id, lat, lon
    geojson_layers_loaded = pyqtSignal()  # GeoJSON 레이어 로드 완료 시그널

    _modal = False
    _windowModality = Qt.NonModal

    modalChanged = pyqtSignal()
    windowModalityChanged = pyqtSignal()

    @pyqtProperty(bool, notify=modalChanged)
    def modal(self):
        return self._modal

    @modal.setter
    def modal(self, value):
        if self._modal != value:
            self._modal = value
            self.modalChanged.emit()

    @pyqtProperty(Qt.WindowModality, notify=windowModalityChanged)
    def windowModality(self):
        return self._windowModality

    @windowModality.setter
    def windowModality(self, value):
        if self._windowModality != value:
            self._windowModality = value
            self.windowModalityChanged.emit()

    def __init__(self, parent=None, splash=None, localization_manager=None):
        super().__init__(parent)
        self.loc = localization_manager
        self.current_mission = None
        self.is_map_ready = False
        self.mgrs_grid_visible = False
        self.coords_display_visible = False
        self.control_zone_visible = False
        self.compass_visible = False
        self.splash = splash  # 스플래시 화면 객체 저장
        self.setup_channel()
        self.load_initial_map()

    def contextMenuEvent(self, event):
        pass

    def setup_channel(self):
        self.channel = QWebChannel()
        self.channel.registerObject("backend", self)
        self.page().setWebChannel(self.channel)

    def load_initial_map(self):
        """지도를 처음 한 번만 로드합니다."""
        html = self.generate_map_html()
        self.setHtml(html)

    def load_mission(self, mission: Mission):
        """미션을 로드합니다. 지도가 준비되지 않았으면 설정만 하고, 준비되었으면 JS로 업데이트합니다."""
        self.current_mission = mission
        if self.is_map_ready:
            self.refresh_map(mission, fit_bounds=True)

    def generate_map_html(self) -> str:
        """Leaflet.js 맵의 기반 HTML 생성 (데이터 없이 구조만)"""

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" />
            <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <style>
                * {{ margin: 0; padding: 0; }}
                html, body {{ height: 100%; background: #121212; overflow: hidden; font-family: 'Segoe UI', sans-serif; }}
                #map {{ width: 100%; height: 100%; cursor: crosshair; }}
                .leaflet-container {{ background: #121212; }}
                /* 웨이포인트 레이더 라벨 */
                .waypoint-label {{
                    background-color: transparent;
                    border: none;
                    box-shadow: none;
                    color: #00d1b2;
                    font-weight: bold;
                    font-size: 11px;
                    padding: 2px 4px;
                    border-radius: 3px;
                    font-family: 'Courier New', monospace;
                    letter-spacing: 0.5px;
                    text-shadow: 0 0 3px rgba(0, 0, 0, 0.8);
                }}
                .leaflet-tooltip {{
                    background-color: transparent;
                    border: none;
                    box-shadow: none;
                }}
                /* MGRS 그리드 라벨 */
                .mgrs-grid-label {{
                    background-color: rgba(0, 255, 0, 0.2);
                    border: 1px solid rgba(0, 255, 0, 0.5);
                    box-shadow: none;
                    color: #00ff00;
                    font-weight: bold;
                    font-size: 10px;
                    padding: 2px 4px;
                    border-radius: 2px;
                    font-family: 'Courier New', monospace;
                    text-shadow: 0 0 2px rgba(0, 0, 0, 0.8);
                }}
                /* 마우스 좌표 표시 */
                #mouse-coords {{
                    position: fixed;
                    bottom: 10px;
                    left: 10px;
                    background-color: rgba(18, 18, 18, 0.95);
                    border: 1px solid #00d1b2;
                    color: #00d1b2;
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-family: 'Courier New', monospace;
                    font-size: 12px;
                    font-weight: bold;
                    line-height: 1.4;
                    pointer-events: none;
                    z-index: 1000;
                    text-shadow: 0 0 2px rgba(0, 0, 0, 0.8);
                    letter-spacing: 0.5px;
                    display: none;
                }}
                #mouse-coords.visible {{
                    display: block;
                }}
                /* 미션 정보 오버레이 */
                #mission-info {{
                    position: fixed;
                    top: 80px;
                    left: 20px;
                    color: #00d1b2;
                    padding: 0;
                    font-family: 'Courier New', monospace;
                    font-size: 11px;
                    line-height: 1.4;
                    pointer-events: none;
                    z-index: 999;
                    text-shadow: 0 0 2px rgba(0, 0, 0, 0.8);
                    letter-spacing: 0.3px;
                    display: none;
                    white-space: pre-line;
                    font-weight: bold;
                }}
                #mission-info.visible {{
                    display: block;
                }}
                #mission-info .mission-header {{
                    display: none;
                }}
                #mission-info .mission-row {{
                    display: block;
                    margin: 2px 0;
                }}
                #mission-info .mission-label {{
                    display: none;
                }}
                #mission-info .mission-value {{
                    color: #00d1b2;
                    font-weight: bold;
                    display: inline;
                }}
                /* 레이어 컨트롤 스타일 */
                .leaflet-control-layers {{
                    background-color: #1a1a1a;
                    border: 1px solid #00d1b2;
                    border-radius: 4px;
                }}
                .leaflet-control-layers-list {{
                    background-color: #1a1a1a;
                }}
                .leaflet-control-layers label {{
                    color: #e0e0e0;
                    font-family: 'Segoe UI', sans-serif;
                }}
                .leaflet-control-layers input[type="radio"] {{
                    accent-color: #00d1b2;
                }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            <div id="mouse-coords">LAT: -- LON: -- MGRS: --</div>
            <div id="mission-info">
                <div class="mission-row"><span class="mission-value" id="mission-name">--</span></div>
                <div class="mission-row"><span class="mission-value" id="mission-wp">0</span></div>
                <div class="mission-row"><span class="mission-value" id="mission-dist">0 km</span></div>
                <div class="mission-row"><span class="mission-value" id="mission-spd">0 km/h</span></div>
                <div class="mission-row"><span class="mission-value" id="mission-eta">0h 0m</span></div>
            </div>
            <script>
                var backend = null;
                var map = null;
                var markers = {{}};
                var polyline = null;
                var waypoints = [];
                var symbols = {{}};
                var mgrsGridLayer = null;
                var mgrsLabels = [];
                var mgrsGridVisible = false;
                var lastMouseCoords = null;
                var coordsDisplay = null;
                var coordsDisplayVisible = false;
                var geoJsonLayers = {{}};
                var geoJsonVisible = {{}};
                var controlZoneLayers = {{}};  // 관제권 레이어들을 저장
                var controlZoneVisible = false;  // 관제권 표시 상태
                var compassMarkers = {{}};  // 나침반 마커들을 저장
                var compassVisible = false;  // 나침반 표시 상태

                // 1. WebChannel 초기화
                new QWebChannel(qt.webChannelTransport, function(channel) {{
                    backend = channel.objects.backend;
                    initMap();
                }});

                function initMap() {{
                    // 지도 초기화 (기본 좌표: 서울)
                    map = L.map('map', {{
                        contextmenu: true,
                        contextmenuInheritItems: false,
                        zoomControl: false 
                    }}).setView([37.5665, 126.9780], 10);

                    L.control.zoom({{ position: 'bottomright' }}).addTo(map);

                    // 여러 타일 레이어 정의
                    var darkLayer = L.tileLayer('https://cartodb-basemaps-{{s}}.global.ssl.fastly.net/dark_all/{{z}}/{{x}}/{{y}}.png', {{
                        attribution: '&copy; CartoDB',
                        maxZoom: 19,
                        minZoom: 0
                    }});

                    var lightLayer = L.tileLayer('https://cartodb-basemaps-{{s}}.global.ssl.fastly.net/light_all/{{z}}/{{x}}/{{y}}.png', {{
                        attribution: '&copy; CartoDB',
                        maxZoom: 19,
                        minZoom: 0
                    }});

                    var osmLayer = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                        attribution: '&copy; OpenStreetMap contributors',
                        maxZoom: 19,
                        minZoom: 0
                    }});

                    var satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                        attribution: 'Tiles &copy; Esri',
                        maxZoom: 18,
                        minZoom: 0
                    }});

                    var hybridLayer = L.layerGroup([
                        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                            attribution: 'Tiles &copy; Esri'
                        }}),
                        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                            attribution: 'Tiles &copy; Esri'
                        }})
                    ]);

                    // 기본 레이어를 다크 모드로 설정
                    darkLayer.addTo(map);

                    // 레이어 선택 컨트롤 추가
                    var baseLayers = {{
                        'Dark Mode': darkLayer,
                        'Light Mode': lightLayer,
                        'OpenStreetMap': osmLayer,
                        'Satellite': satelliteLayer,
                        'Hybrid': hybridLayer
                    }};

                    L.control.layers(baseLayers, null, {{ position: 'topleft' }}).addTo(map);

                    // 2. 지도 자체 우클릭 이벤트 (웨이포인트 추가)
                    map.on('contextmenu', function(e) {{
                        if (backend) {{
                            // Python의 on_map_click(lat, lon) 호출
                            backend.on_map_click(e.latlng.lat, e.latlng.lng);
                        }}
                    }});

                    // 3. 마우스 움직임 이벤트 (좌표 표시)
                    coordsDisplay = document.getElementById('mouse-coords');
                    map.on('mousemove', function(e) {{
                        lastMouseCoords = e.latlng;
                        var lat = e.latlng.lat.toFixed(5);
                        var lon = e.latlng.lng.toFixed(5);

                        // MGRS 변환 요청 (캐시된 데이터 사용)
                        var mgrsCoord = '계산 중...';
                        if (window.cachedMgrsCoords && window.cachedMgrsCoords[lat + '_' + lon]) {{
                            mgrsCoord = window.cachedMgrsCoords[lat + '_' + lon];
                        }}

                        coordsDisplay.textContent = `LAT: ${{lat}} LON: ${{lon}} MGRS: ${{mgrsCoord}}`;

                        // Python에 MGRS 변환 요청 (비동기)
                        if (backend && (!window.cachedMgrsCoords || !window.cachedMgrsCoords[lat + '_' + lon])) {{
                            backend.convert_single_mgrs(parseFloat(lat), parseFloat(lon), lat + '_' + lon);
                        }}
                    }});

                    map.on('mouseout', function() {{
                        if (coordsDisplay) {{
                            coordsDisplay.textContent = 'LAT: -- LON: -- MGRS: --';
                        }}
                    }});

                    // 맵 준비 완료를 Python에 알림
                    if (backend) {{
                        backend.on_map_ready();
                    }}
                }}

                // GeoJSON 데이터 추가 함수
                window.addGeoJsonLayer = function(layerName, geoJsonData) {{
                    if (!geoJsonData) {{
                        console.error('GeoJSON 데이터가 없음:', layerName);
                        return;
                    }}
                    
                    console.log('GeoJSON 레이어 로드 시작:', layerName, 'features:', geoJsonData.features ? geoJsonData.features.length : 0);
                    
                    var styleColors = {{
                        'apt': '#ff6b6b',    // 빨강 - Airport
                        'nav': '#4ecdc4',    // 청록 - Navigation
                        'obs': '#ffe66d',    // 노랑 - Obstacle
                        'raa': '#ff69b4',    // 핫핑크 - Restricted Area (더 눈에 띄는 색상)
                        'rca': '#ffd3b6'     // 주황 - R-Class Area
                    }};
                    
                    var color = styleColors[layerName] || '#888888';
                    
                    try {{
                        // 공항인 경우 관제권 레이어 미리 생성
                        if (layerName === 'apt') {{
                            var controlZoneGroup = L.layerGroup();
                            
                            // 공항 관제권 생성을 위한 임시 처리
                            geoJsonData.features.forEach(function(feature) {{
                                if (feature.geometry && feature.geometry.type === 'Point') {{
                                    var latlng = L.latLng(feature.geometry.coordinates[1], feature.geometry.coordinates[0]);
                                    
                                    // 5NM = 9.26km (정확한 값)
                                    var controlZoneRadius = 9260; // 미터 단위
                                    
                                    // 관제권 원형 오버레이 생성
                                    var controlZoneCircle = L.circle(latlng, {{
                                        radius: controlZoneRadius,
                                        color: '#ff0000',
                                        weight: 2,
                                        opacity: 0.6,
                                        fill: true,
                                        fillColor: '#ff0000',
                                        fillOpacity: 0.1,
                                        dashArray: '10, 5'
                                    }});
                                    
                                    // 공항 정보 라벨 생성
                                    var airportName = feature.properties.name || '공항';
                                    var icaoCode = feature.properties.icaoCode || '';
                                    var labelText = airportName + (icaoCode ? ' (' + icaoCode + ')' : '');
                                    
                                    var controlZoneLabel = L.marker(latlng, {{
                                        icon: L.divIcon({{
                                            className: 'control-zone-label',
                                            html: '<div style="background: rgba(255,255,255,0.9); color: #cc0000; padding: 3px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; white-space: nowrap; pointer-events: none; border: 1px solid #ff0000; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">' + labelText + '</div>',
                                            iconSize: null,
                                            iconAnchor: [0, -20]
                                        }})
                                    }});
                                    
                                    // 관제권 원형과 라벨에 클릭 이벤트 추가 - 공항 정보 표시
                                    controlZoneCircle.on('click', function() {{
                                        // GeoJSON 레이어의 apt 마커에서 해당 공항의 팝업을 표시
                                        if (geoJsonLayers['apt']) {{
                                            geoJsonLayers['apt'].eachLayer(function(layer) {{
                                                if (layer.getLatLng && layer.getLatLng().equals(latlng)) {{
                                                    layer.openPopup();
                                                }}
                                            }});
                                        }}
                                    }});
                                    
                                    controlZoneLabel.on('click', function() {{
                                        // GeoJSON 레이어의 apt 마커에서 해당 공항의 팝업을 표시
                                        if (geoJsonLayers['apt']) {{
                                            geoJsonLayers['apt'].eachLayer(function(layer) {{
                                                if (layer.getLatLng && layer.getLatLng().equals(latlng)) {{
                                                    layer.openPopup();
                                                }}
                                            }});
                                        }}
                                    }});
                                    
                                    // 관제권 그룹에 추가
                                    controlZoneGroup.addLayer(controlZoneCircle);
                                    controlZoneGroup.addLayer(controlZoneLabel);
                                }}
                            }});
                            
                            // 관제권 레이어 저장
                            controlZoneLayers[layerName] = controlZoneGroup;
                        }}
                        
                        var geoJsonLayer = L.geoJSON(geoJsonData, {{
                            style: function(feature) {{
                                // Polygon/Polyline 스타일
                                return {{
                                    color: color,
                                    weight: 3,
                                    opacity: 1.0,
                                    fill: true,
                                    fillColor: color,
                                    fillOpacity: 0.4
                                }};
                            }},
                            pointToLayer: function(feature, latlng) {{                                
                                // 더 큰 마커로 표시
                                return L.marker(latlng, {{
                                    icon: L.divIcon({{
                                        className: 'geojson-marker',
                                        html: '<div style="background-color: ' + color + '; width: 12px; height: 12px; border-radius: 50%; border: 2px solid #000; cursor: pointer;"></div>',
                                        iconSize: [16, 16],
                                        iconAnchor: [8, 8]
                                    }})
                                }});
                            }},
                        onEachFeature: function(feature, layer) {{
                            var popupContent = '<div style="max-height: 400px; overflow-y: auto; font-family: Arial, sans-serif; font-size: 12px;">';
                            var props = feature.properties;
                            
                            if (props) {{
                                // 헤더 섹션 - 이름과 타입
                                if (props.name) {{
                                    popupContent += '<h3 style="margin: 0 0 10px 0; color: #2c3e50; border-bottom: 2px solid ' + color + '; padding-bottom: 5px;">' + props.name + '</h3>';
                                }}
                                
                                // 레이어별 맞춤 정보 표시
                                if (layerName === 'apt') {{
                                    // 공항 정보
                                    if (props.icaoCode) popupContent += '<div><strong>ICAO Code:</strong> ' + props.icaoCode + '</div>';
                                    if (props.elevation && props.elevation.value !== undefined) {{
                                        popupContent += '<div><strong>고도:</strong> ' + props.elevation.value + ' ft MSL</div>';
                                    }}
                                    if (props.magneticDeclination) {{
                                        popupContent += '<div><strong>자기편각:</strong> ' + props.magneticDeclination + '°</div>';
                                    }}
                                    if (props.trafficType && props.trafficType.length > 0) {{
                                        var trafficTypes = {{'0': '군용', '1': '민간'}};
                                        var types = props.trafficType.map(t => trafficTypes[t] || t).join(', ');
                                        popupContent += '<div><strong>교통 형태:</strong> ' + types + '</div>';
                                    }}
                                    if (props.private) popupContent += '<div><strong>사설 공항:</strong> 예</div>';
                                    if (props.ppr) popupContent += '<div><strong>사전 허가 필요:</strong> 예</div>';
                                    
                                    // 관제권 드론 비행 제한 정보
                                    popupContent += '<div style="margin-top: 10px; padding: 8px; background-color: #ffe6e6; border: 1px solid #ff6b6b; border-radius: 4px;"><strong style="color: #cc0000;">드론 비행 제한구역</strong><br><span style="font-size: 11px; color: #666;">관제권 반경 5NM(9.3km) 내 드론 비행 금지</span></div>';
                                    
                                    // 활주로 정보
                                    if (props.runways && props.runways.length > 0) {{
                                        popupContent += '<div style="margin-top: 10px;"><strong>활주로:</strong></div>';
                                        props.runways.forEach(function(rw) {{
                                            popupContent += '<div style="margin-left: 10px; margin-top: 3px;">• ' + rw.designator + ': ' + 
                                                (rw.dimension ? rw.dimension.length.value + 'm × ' + rw.dimension.width.value + 'm' : '') + 
                                                (rw.surface ? ' (' + (rw.surface.composition && rw.surface.composition[0] ? getSurfaceType(rw.surface.composition[0]) : '알 수 없음') + ')' : '') + '</div>';
                                        }});
                                    }}
                                }} else if (layerName === 'nav') {{
                                    // 네비게이션 정보
                                    if (props.identifier) popupContent += '<div><strong>식별자:</strong> ' + props.identifier + '</div>';
                                    if (props.frequency) {{
                                        popupContent += '<div><strong>주파수:</strong> ' + props.frequency.value + ' ' + (props.frequency.unit === 2 ? 'MHz' : 'kHz') + '</div>';
                                    }}
                                    if (props.channel) popupContent += '<div><strong>채널:</strong> ' + props.channel + '</div>';
                                    if (props.elevation && props.elevation.value !== undefined) {{
                                        popupContent += '<div><strong>고도:</strong> ' + props.elevation.value + ' ft MSL</div>';
                                    }}
                                    if (props.magneticDeclination) {{
                                        popupContent += '<div><strong>자기편각:</strong> ' + props.magneticDeclination + '°</div>';
                                    }}
                                    var navTypes = {{'0': 'NDB', '1': 'VOR', '2': 'VORDME', '3': 'DME', '4': 'TACAN'}};
                                    if (props.type !== undefined) {{
                                        popupContent += '<div><strong>타입:</strong> ' + (navTypes[props.type] || props.type) + '</div>';
                                    }}
                                }} else if (layerName === 'obs') {{
                                    // 장애물 정보
                                    if (props.elevation && props.elevation.value !== undefined) {{
                                        popupContent += '<div><strong>고도:</strong> ' + props.elevation.value + ' ft MSL</div>';
                                    }}
                                    if (props.elevationGeoid && props.elevationGeoid.hae !== undefined) {{
                                        popupContent += '<div><strong>해발 고도:</strong> ' + Math.round(props.elevationGeoid.hae) + ' ft</div>';
                                    }}
                                    var obsTypes = {{'1': '안테나', '2': '건물', '3': '굴뚝', '4': '냉각탑', '5': '기타', '6': '기둥', '7': '풍력 터빈'}};
                                    if (props.type !== undefined) {{
                                        popupContent += '<div><strong>타입:</strong> ' + (obsTypes[props.type] || '기타') + '</div>';
                                    }}
                                    if (props.osmTags && props.osmTags.power) {{
                                        popupContent += '<div><strong>전력 관련:</strong> ' + props.osmTags.power + '</div>';
                                    }}
                                }} else if (layerName === 'raa') {{
                                    // 제한구역 정보
                                    if (props.activity !== undefined) {{
                                        var activities = {{'0': '공역 이용', '1': '군사 훈련', '2': '위험 구역', '3': '항공기 시험'}};
                                        popupContent += '<div><strong>활동:</strong> ' + (activities[props.activity] || props.activity) + '</div>';
                                    }}
                                    if (props.icaoClass !== undefined) {{
                                        var classes = {{'1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E', '6': 'F', '7': 'G'}};
                                        popupContent += '<div><strong>ICAO 등급:</strong> ' + (classes[props.icaoClass] || props.icaoClass) + '</div>';
                                    }}
                                    if (props.upperLimit && props.upperLimit.value !== undefined) {{
                                        popupContent += '<div><strong>상한:</strong> ' + props.upperLimit.value + ' ft</div>';
                                    }}
                                    if (props.lowerLimit && props.lowerLimit.value !== undefined) {{
                                        popupContent += '<div><strong>하한:</strong> ' + props.lowerLimit.value + ' ft</div>';
                                    }}
                                    if (props.onRequest) popupContent += '<div><strong>요청 시 운용:</strong> 예</div>';
                                    if (props.byNotam) popupContent += '<div><strong>NOTAM 발행:</strong> 예</div>';
                                    if (props.remarks) popupContent += '<div><strong>비고:</strong> ' + props.remarks + '</div>';
                                }} else if (layerName === 'rca') {{
                                    // R-Class 구역 정보
                                    if (props.elevation && props.elevation.value !== undefined) {{
                                        popupContent += '<div><strong>지상 고도:</strong> ' + props.elevation.value + ' ft MSL</div>';
                                    }}
                                    if (props.permittedAltitude && props.permittedAltitude.value !== undefined) {{
                                        popupContent += '<div><strong>허용 고도:</strong> ' + props.permittedAltitude.value + ' ft</div>';
                                    }}
                                    if (props.turbine) popupContent += '<div><strong>터빈:</strong> 예</div>';
                                    if (props.combustion) popupContent += '<div><strong>연소:</strong> 예</div>';
                                    if (props.electric) popupContent += '<div><strong>전기:</strong> 예</div>';
                                    if (props.osmTags && props.osmTags.sport) {{
                                        popupContent += '<div><strong>스포츠:</strong> ' + props.osmTags.sport + '</div>';
                                    }}
                                }}
                                
                                // 공통 정보
                                if (props.country) popupContent += '<div style="margin-top: 8px;"><strong>국가:</strong> ' + props.country + '</div>';
                                
                                // 좌표 정보 (geometry에서)
                                if (feature.geometry && feature.geometry.coordinates) {{
                                    var coords = feature.geometry.coordinates;
                                    if (feature.geometry.type === 'Point') {{
                                        popupContent += '<div style="margin-top: 8px; font-size: 11px; color: #666;"><strong>좌표:</strong> ' + 
                                            coords[1].toFixed(6) + '°N, ' + coords[0].toFixed(6) + '°E</div>';
                                    }}
                                }}
                            }}
                            
                            popupContent += '</div>';
                            
                            // Surface type helper function
                            function getSurfaceType(code) {{
                                var surfaces = {{
                                    '0': '아스팔트',
                                    '1': '콘크리트', 
                                    '2': '흙',
                                    '12': '자갈',
                                    '22': '잔디'
                                }};
                                return surfaces[code] || '알 수 없음';
                            }}
                            
                            layer.bindPopup(popupContent);
                        }}
                    }});
                    
                    // GeoJSON 레이어를 기본적으로 숨김 상태로 로드
                    // geoJsonLayer.addTo(map);  // 기본 렌더 비활성화
                    
                    // 모든 레이어를 GeoJSON 레이어만 저장 (관제권 분리)
                    geoJsonLayers[layerName] = geoJsonLayer;
                    
                    geoJsonVisible[layerName] = false;  // 기본값을 false로 변경
                    console.log('GeoJSON 레이어 로드 완료 (숨김 상태):', layerName);
                    }} catch (e) {{
                        console.error('GeoJSON 레이어 로드 오류:', layerName, e);
                    }}
                }};
                
                // GeoJSON 레이어 토글
                window.toggleGeoJsonLayer = function(layerName) {{
                    if (!geoJsonLayers[layerName]) {{
                        console.warn('GeoJSON 레이어를 찾을 수 없음:', layerName);
                        return false;
                    }}
                    
                    if (geoJsonVisible[layerName]) {{
                        map.removeLayer(geoJsonLayers[layerName]);
                        geoJsonVisible[layerName] = false;
                    }} else {{
                        map.addLayer(geoJsonLayers[layerName]);
                        geoJsonVisible[layerName] = true;
                    }}
                    return geoJsonVisible[layerName];
                }};
                
                // 관제권 토글 함수
                window.toggleControlZone = function() {{
                    if (controlZoneVisible) {{
                        // 모든 관제권 레이어 숨김
                        for (var layerName in controlZoneLayers) {{
                            if (controlZoneLayers[layerName] && map.hasLayer(controlZoneLayers[layerName])) {{
                                map.removeLayer(controlZoneLayers[layerName]);
                            }}
                        }}
                        controlZoneVisible = false;
                    }} else {{
                        // 공항 레이어가 표시된 상태에서만 관제권 표시
                        for (var layerName in controlZoneLayers) {{
                            if (controlZoneLayers[layerName]) {{
                                map.addLayer(controlZoneLayers[layerName]);
                            }}
                        }}
                        controlZoneVisible = true;
                    }}
                    return controlZoneVisible;
                }};

                // 좌표 표시 토글 함수
                window.toggleCoordsDisplay = function() {{
                    coordsDisplayVisible = !coordsDisplayVisible;
                    if (coordsDisplayVisible) {{
                        coordsDisplay.classList.add('visible');
                    }} else {{
                        coordsDisplay.classList.remove('visible');
                    }}
                    return coordsDisplayVisible;
                }};

                // 나침반 토글 함수
                window.toggleCompass = function() {{
                    if (compassVisible) {{
                        removeCompass();
                        compassVisible = false;
                    }} else {{
                        drawCompass();
                        compassVisible = true;
                    }}
                    return compassVisible;
                }};

                // 나침반 그리기 함수
                function drawCompass() {{
                    // 기존 나침반 마커 제거
                    for (var wpId in compassMarkers) {{
                        if (compassMarkers[wpId]) {{
                            map.removeLayer(compassMarkers[wpId]);
                        }}
                    }}
                    compassMarkers = {{}};

                    // 기존 나침반 라벨 모두 제거 (방향 라벨 + 각도 라벨 + 내부 원) - 잔상 방지
                    map.eachLayer(function(layer) {{
                        if (layer instanceof L.Marker && layer.getIcon() && 
                            (layer.getIcon().options.className === 'compass-direction-label' || 
                             layer.getIcon().options.className === 'compass-degree-label')) {{
                            map.removeLayer(layer);
                        }}
                        if (layer instanceof L.Circle && layer.options.dashArray === '3, 3') {{
                            map.removeLayer(layer);
                        }}
                    }});

                    // 줌 레벨에 따라 나침반 크기 조정
                    var zoomLevel = map.getZoom();
                    var baseRadius = 800; // 기본 반경
                    var compassRadius = baseRadius;
                    
                    // 줌 레벨에 따른 반경 조정
                    if (zoomLevel < 8) {{
                        compassRadius = baseRadius * 0.6; // 축소 줌에서는 더 작게
                    }} else if (zoomLevel >= 14) {{
                        compassRadius = baseRadius * 1.5; // 확대 줌에서는 더 크게
                    }}

                    waypoints.forEach(function(wp) {{
                        // 각 웨이포인트마다 나침반(각도기) 원형 오버레이 생성
                        var compassCircle = L.circle([wp.lat, wp.lon], {{
                            radius: compassRadius,
                            color: '#00d1b2',
                            weight: 2,
                            opacity: 0.7,
                            fill: false,
                            dashArray: '5, 5'
                        }});

                        // 8개 주요 방향: N, NE, E, SE, S, SW, W, NW
                        var directions = [
                            {{ angle: 0, label: 'N' }},
                            {{ angle: 45, label: 'NE' }},
                            {{ angle: 90, label: 'E' }},
                            {{ angle: 135, label: 'SE' }},
                            {{ angle: 180, label: 'S' }},
                            {{ angle: 225, label: 'SW' }},
                            {{ angle: 270, label: 'W' }},
                            {{ angle: 315, label: 'NW' }}
                        ];

                        // 주요 방향 라벨 표시
                        directions.forEach(function(dir) {{
                            // 올바른 각도 계산: 0°=북쪽(위), 90°=동쪽(오른쪽), 180°=남쪽(아래), 270°=서쪽(왼쪽)
                            var rad = (90 - dir.angle) * Math.PI / 180;
                            var distance = compassRadius * 1.15; // 반경보다 조금 더 바깥에 표시
                            var lat = wp.lat + (Math.sin(rad) * distance / 111000); // 위도 변환
                            var lon = wp.lon + (Math.cos(rad) * distance / (111000 * Math.cos(wp.lat * Math.PI / 180))); // 경도 변환

                            var marker = L.marker([lat, lon], {{
                                icon: L.divIcon({{
                                    className: 'compass-direction-label',
                                    html: '<div style="background: transparent; color: #00d1b2; padding: 2px 6px; font-size: 12px; font-weight: bold; border: none; border-radius: 2px; pointer-events: none; font-family: Courier New, monospace; text-shadow: 0 0 3px rgba(0,0,0,0.8);">' + dir.label + '</div>',
                                    iconSize: null,
                                    iconAnchor: [12, 12]
                                }})
                            }});
                            marker.addTo(map);
                        }});

                        // 30도마다 각도 마크 추가 (숫자 표시)
                        for (var angle = 0; angle < 360; angle += 30) {{
                            // 주요 방향(8개)은 이미 라벨이 있으므로 건너뛰기
                            if (angle % 45 === 0) continue;
                            
                            var rad = (90 - angle) * Math.PI / 180;
                            var markDistance = compassRadius * 1.0; // 원 위에 표시
                            var lat = wp.lat + (Math.sin(rad) * markDistance / 111000);
                            var lon = wp.lon + (Math.cos(rad) * markDistance / (111000 * Math.cos(wp.lat * Math.PI / 180)));

                            var markerDiv = L.divIcon({{
                                className: 'compass-degree-label',
                                html: '<div style="background: transparent; color: #00a896; padding: 0px 2px; font-size: 9px; font-weight: bold; border: none; pointer-events: auto; cursor: pointer; font-family: Courier New, monospace; text-shadow: 0 0 2px rgba(0,0,0,0.8); transition: all 0.2s;" data-angle="' + angle + '">' + angle + '°</div>',
                                iconSize: null,
                                iconAnchor: [10, 10]
                            }});

                            var marker = L.marker([lat, lon], {{ icon: markerDiv }});
                            
                            // 호버 이벤트 추가
                            marker.on('mouseover', function(e) {{
                                var el = e.target._icon.querySelector('div');
                                if (el) {{
                                    el.style.background = 'rgba(0, 209, 178, 0.3)';
                                    el.style.fontSize = '11px';
                                    el.style.padding = '2px 4px';
                                    el.style.borderRadius = '4px';
                                    el.style.border = '1px solid #00d1b2';
                                    el.style.color = '#ffffff';
                                }}
                            }});
                            
                            marker.on('mouseout', function(e) {{
                                var el = e.target._icon.querySelector('div');
                                if (el) {{
                                    el.style.background = 'transparent';
                                    el.style.fontSize = '9px';
                                    el.style.padding = '0px 2px';
                                    el.style.borderRadius = '2px';
                                    el.style.border = 'none';
                                    el.style.color = '#00a896';
                                }}
                            }});
                            
                            marker.addTo(map);
                        }}

                        // 내부 원 (반경 표시용, 선택사항)
                        var innerCircle = L.circle([wp.lat, wp.lon], {{
                            radius: compassRadius / 2,
                            color: '#00d1b2',
                            weight: 1,
                            opacity: 0.3,
                            fill: false,
                            dashArray: '3, 3'
                        }});
                        innerCircle.addTo(map);

                        compassCircle.addTo(map);
                        compassMarkers[wp.wp_id] = compassCircle;
                    }});
                }}

                // 나침반 제거 함수
                function removeCompass() {{
                    for (var wpId in compassMarkers) {{
                        if (compassMarkers[wpId]) {{
                            map.removeLayer(compassMarkers[wpId]);
                        }}
                    }}
                    compassMarkers = {{}};

                    // 모든 나침반 라벨 제거 (방향 라벨 + 각도 라벨 + 내부 원)
                    map.eachLayer(function(layer) {{
                        if (layer instanceof L.Marker && layer.getIcon() && 
                            (layer.getIcon().options.className === 'compass-direction-label' || 
                             layer.getIcon().options.className === 'compass-degree-label')) {{
                            map.removeLayer(layer);
                        }}
                        if (layer instanceof L.Circle && layer.options.dashArray === '3, 3') {{
                            // 내부 원 제거
                            map.removeLayer(layer);
                        }}
                    }});
                }}

                function addWaypoints() {{
                    // 기존 마커 제거
                    Object.keys(markers).forEach(id => map.removeLayer(markers[id]));
                    markers = {{}};

                    waypoints.forEach(function(wp) {{
                        var iconUrl = symbols[wp.wp_id] || '';
                        var icon = L.icon({{
                            iconUrl: iconUrl,
                            iconSize: [35, 35],
                            iconAnchor: [17, 17],
                            popupAnchor: [0, -17]
                        }});

                        var marker = L.marker([wp.lat, wp.lon], {{
                            icon: icon,
                            draggable: true
                        }}).addTo(map);

                        // 마커 우클릭 이벤트 (편집/삭제)
                        marker.on('contextmenu', function(e) {{
                            L.DomEvent.preventDefault(e);    // 브라우저 기본 메뉴 방지
                            L.DomEvent.stopPropagation(e);   // 지도 클릭 이벤트로 전파 방지
                            if (backend) {{
                                backend.on_waypoint_right_click(wp.wp_id);
                            }}
                        }});

                        // 마커 드래그 이벤트 (위치 이동)
                        marker.on('dragend', function(e) {{
                            var newPos = e.target.getLatLng();
                            if (backend) {{
                                backend.on_waypoint_moved(wp.wp_id, newPos.lat, newPos.lng);
                            }}
                        }});

                        // 웨이포인트 간단 라벨 표시 (거리 포함)
                        var distanceText = wp.distance > 0 ? " | " + wp.distance + "km" : "";
                        var wpName = wp.name ? wp.name : "WP-" + (waypoints.indexOf(wp) + 1);
                        var labelText = wpName + " | " + wp.task_code + " | " + wp.alt + "m | " + wp.speed + "km/h" + distanceText;
                        marker.bindTooltip(labelText, {{
                            permanent: true,
                            direction: 'right',
                            offset: [20, 0],
                            className: 'waypoint-label',
                            sticky: false
                        }});

                        markers[wp.wp_id] = marker;
                    }});

                    drawRoute();
                }}

                function drawRoute() {{
                    if (polyline) map.removeLayer(polyline);
                    var coords = waypoints.map(wp => [wp.lat, wp.lon]);
                    if (coords.length > 0) {{
                        polyline = L.polyline(coords, {{
                            color: '#00d1b2',
                            weight: 3,
                            opacity: 0.8,
                            dashArray: '5, 10'
                        }}).addTo(map);
                    }}
                }}

                // 외부(Python)에서 호출하는 지도 갱신 함수
                window.refreshMap = function(newWaypoints, newSymbols, fitBounds) {{
                    waypoints = newWaypoints;
                    if (newSymbols) {{
                        symbols = newSymbols;
                    }}
                    addWaypoints();

                    // 나침반이 켜져있으면 다시 그리기
                    if (compassVisible) {{
                        drawCompass();
                    }}

                    if (fitBounds && waypoints.length > 0) {{
                        var group = new L.featureGroup(Object.values(markers));
                        map.fitBounds(group.getBounds(), {{ padding: [50, 50] }});
                    }}
                }};
                
                // 미션 정보 업데이트 함수
                window.updateMissionInfo = function(missionData) {{
                    var missionInfo = document.getElementById('mission-info');
                    if (!missionInfo) return;
                    
                    document.getElementById('mission-name').textContent = missionData.mission_name || '--';
                    document.getElementById('mission-wp').textContent = 'WP: ' + (missionData.waypoint_count || '0');
                    document.getElementById('mission-dist').textContent = 'DIST: ' + (missionData.total_distance || 0).toFixed(1) + 'km';
                    document.getElementById('mission-spd').textContent = 'SPD: ' + (missionData.avg_speed || 0).toFixed(1) + 'km/h';
                    
                    var hours = missionData.flight_hours || 0;
                    var minutes = missionData.flight_minutes || 0;
                    document.getElementById('mission-eta').textContent = 'ETA: ' + hours + 'h ' + minutes + 'm';
                    
                    // 미션 정보가 있으면 표시
                    if (missionData.waypoint_count > 0) {{
                        missionInfo.classList.add('visible');
                    }} else {{
                        missionInfo.classList.remove('visible');
                    }}
                }};
                
                // 미션 정보 숨김 함수
                window.hideMissionInfo = function() {{
                    var missionInfo = document.getElementById('mission-info');
                    if (missionInfo) {{
                        missionInfo.classList.remove('visible');
                    }}
                }};

                // MGRS 그리드 토글 함수
                window.toggleMGRSGrid = function() {{
                    if (mgrsGridVisible) {{
                        removeMGRSGrid();
                        mgrsGridVisible = false;
                    }} else {{
                        drawMGRSGrid();
                        mgrsGridVisible = true;
                        // 맵 이동/줌 시 그리드 자동 업데이트
                        map.on('zoomend moveend', updateMGRSGridIfVisible);
                    }}
                }};

                function drawMGRSGrid() {{
                    if (mgrsGridLayer) {{
                        map.removeLayer(mgrsGridLayer);
                    }}
                    // 기존 라벨 제거
                    mgrsLabels.forEach(label => map.removeLayer(label));
                    mgrsLabels = [];

                    var bounds = map.getBounds();
                    var lines = [];

                    // 줌 레벨에 따라 그리드 간격 결정
                    var zoomLevel = map.getZoom();
                    var gridSpacing = 1; // 기본값: 1도
                    if (zoomLevel < 6) gridSpacing = 5;
                    else if (zoomLevel < 8) gridSpacing = 2;
                    else if (zoomLevel > 12) gridSpacing = 0.5;

                    // 위도 그리드: gridSpacing마다 선 그리기
                    var lat = Math.ceil(bounds.getSouth() / gridSpacing) * gridSpacing;
                    var latLines = [];
                    while (lat <= bounds.getNorth()) {{
                        latLines.push(lat);
                        lat += gridSpacing;
                    }}

                    // 경도 그리드: gridSpacing마다 선 그리기
                    var lon = Math.ceil(bounds.getWest() / gridSpacing) * gridSpacing;
                    var lonLines = [];
                    while (lon <= bounds.getEast()) {{
                        lonLines.push(lon);
                        lon += gridSpacing;
                    }}

                    // 격자선 그리기 (위도)
                    latLines.forEach(function(lat) {{
                        var latLngs = [];
                        for (var lon = bounds.getWest(); lon <= bounds.getEast(); lon += 0.1) {{
                            latLngs.push([lat, lon]);
                        }}
                        var line = L.polyline(latLngs, {{
                            color: '#00ff00',
                            weight: 1.5,
                            opacity: 0.6,
                            dashArray: '5, 5'
                        }});
                        lines.push(line);
                    }});

                    // 격자선 그리기 (경도)
                    lonLines.forEach(function(lon) {{
                        var latLngs = [];
                        for (var lat = bounds.getSouth(); lat <= bounds.getNorth(); lat += 0.1) {{
                            latLngs.push([lat, lon]);
                        }}
                        var line = L.polyline(latLngs, {{
                            color: '#00ff00',
                            weight: 1.5,
                            opacity: 0.6,
                            dashArray: '5, 5'
                        }});
                        lines.push(line);
                    }});

                    // Python으로 MGRS 변환 요청 (grid cell 중심 좌표들)
                    var mgrsRequests = [];
                    var gridCenters = [];
                    for (var i = 0; i < latLines.length - 1; i++) {{
                        for (var j = 0; j < lonLines.length - 1; j++) {{
                            var centerLat = (latLines[i] + latLines[i + 1]) / 2;
                            var centerLon = (lonLines[j] + lonLines[j + 1]) / 2;
                            mgrsRequests.push({{lat: centerLat, lon: centerLon}});
                            gridCenters.push({{lat: centerLat, lon: centerLon}});
                        }}
                    }}

                    // Python 백엔드에 MGRS 변환 요청
                    if (backend && mgrsRequests.length > 0) {{
                        window.pendingGridCenters = gridCenters; // 나중에 사용할 좌표 저장
                        backend.compute_mgrs_grid(JSON.stringify(mgrsRequests));

                        // MGRS 데이터가 준비될 때까지 대기
                        setTimeout(function() {{
                            addMGRSLabels(gridCenters);
                        }}, 100);
                    }}

                    // FeatureGroup으로 그룹화
                    mgrsGridLayer = L.featureGroup(lines);
                    mgrsGridLayer.addTo(map);

                    // 맵 이동/줌 시 그리드 자동 업데이트
                    if (mgrsGridVisible) {{
                        map.off('zoomend moveend', updateMGRSGridIfVisible);
                        map.on('zoomend moveend', updateMGRSGridIfVisible);
                    }}
                }}

                function addMGRSLabels(gridCenters) {{
                    gridCenters.forEach(function(center) {{
                        var key = center.lat.toFixed(3) + '_' + center.lon.toFixed(3);
                        var mgrsCoord = '';

                        if (window.mgrsGridData && window.mgrsGridData[key]) {{
                            mgrsCoord = window.mgrsGridData[key];
                        }} else {{
                            // 폴백: 위경도 표시
                            
                            Coord = Math.round(center.lat * 100) / 100 + '° / ' + Math.round(center.lon * 100) / 100 + '°';
                        }}

                        var marker = L.marker([center.lat, center.lon], {{
                            icon: L.divIcon({{
                                className: 'mgrs-grid-label',
                                html: mgrsCoord,
                                iconSize: null
                            }})
                        }}).addTo(map);
                        mgrsLabels.push(marker);
                    }});
                }};

                window.addMGRSLabelsToGrid = addMGRSLabels;

                function updateMGRSGridIfVisible() {{
                    if (mgrsGridVisible) {{
                        drawMGRSGrid();
                    }}
                }}

                function removeMGRSGrid() {{
                    if (mgrsGridLayer) {{
                        map.removeLayer(mgrsGridLayer);
                        mgrsGridLayer = null;
                    }}
                    // 모든 라벨 제거
                    mgrsLabels.forEach(label => map.removeLayer(label));
                    mgrsLabels = [];
                    map.off('zoomend moveend', updateMGRSGridIfVisible);
                }}
            </script>
        </body>
        </html>
        """
        return html

    def refresh_map(self, mission: Mission, fit_bounds=False):
        """맵 새로고침 (웨이포인트 리스트 업데이트)"""
        if not self.is_map_ready:
            return

        waypoints_json = json.dumps([wp.to_dict() for wp in mission.waypoints])

        # 군사 기호 SVG 갱신
        symbols = {}
        for wp in mission.waypoints:
            svg = MilitarySymbolGenerator.create_svg(wp.task_code)
            svg_b64 = base64.b64encode(svg.encode()).decode()
            symbols[wp.wp_id] = f"data:image/svg+xml;base64,{svg_b64}"

        symbols_json = json.dumps(symbols)

        # MGRS 정보 생성
        mgrs_data = {}
        for wp in mission.waypoints:
            mgrs_coord = MGRSConverter.lat_lon_to_mgrs(wp.lat, wp.lon)
            mgrs_data[wp.wp_id] = mgrs_coord

        mgrs_data_json = json.dumps(mgrs_data)

        fit_bounds_js = "true" if fit_bounds else "false"
        js_code = f"refreshMap({waypoints_json}, {symbols_json}, {fit_bounds_js}); window.mgrsData = {mgrs_data_json};"
        self.page().runJavaScript(js_code)
        
        # 미션 정보 업데이트
        self.update_mission_info_on_map(mission)

    @pyqtSlot()
    def on_map_ready(self):
        """JS에서 맵 초기화 완료 시 호출"""
        self.is_map_ready = True
        # GeoJSON 레이어 로드
        self.load_geojson_layers()
        # GeoJSON 레이어 로드 완료 시그널 발생
        self.geojson_layers_loaded.emit()
        if self.current_mission:
            self.refresh_map(self.current_mission, fit_bounds=True)

    @pyqtSlot(float, float)  # JS에서 위도, 경도를 인자로 보냄
    def on_map_click(self, lat, lon):
        """지도 빈 곳 우클릭 시 호출"""
        self.waypoint_added.emit(float(lat), float(lon))

    @pyqtSlot(str)  # JS에서 wp_id를 문자열로 보냄
    def on_waypoint_right_click(self, wp_id):
        """마커 우클릭 시 호출"""
        if not self.current_mission:
            return

        # wp_id로 웨이포인트 찾기
        wp = None
        for w in self.current_mission.waypoints:
            if w.wp_id == wp_id:
                wp = w
                break

        if not wp:
            return

        dialog = WaypointEditDialog(wp, self.parentWidget(), self.loc)
        if dialog.exec_() == QDialog.Accepted:
            if dialog.result == 'delete':
                self.waypoint_deleted.emit(wp_id)
            elif dialog.result == 'save':
                self.waypoint_updated.emit(wp_id, wp.alt, wp.task_code, wp.speed)

    @pyqtSlot(str, float, float)
    def on_waypoint_moved(self, wp_id, lat, lon):
        """마커 드래그 종료 시 호출"""
        self.waypoint_moved.emit(wp_id, float(lat), float(lon))

    def toggle_mgrs_grid(self):
        """MGRS 그리드 표시/숨김 토글"""
        if self.is_map_ready:
            self.mgrs_grid_visible = not self.mgrs_grid_visible
            self.page().runJavaScript("toggleMGRSGrid();")
            return self.mgrs_grid_visible
        return False

    def toggle_coords_display(self):
        """좌표 표시 토글"""
        if self.is_map_ready:
            self.coords_display_visible = not self.coords_display_visible
            self.page().runJavaScript("toggleCoordsDisplay();")
            return self.coords_display_visible
        return False

    def toggle_geojson_layer(self, layer_key):
        """GeoJSON 레이어 토글"""
        if self.is_map_ready:
            self.page().runJavaScript(f"toggleGeoJsonLayer('{layer_key}');")
            return True
        return False
        
    def toggle_control_zone(self):
        """관제권 표시 토글"""
        if self.is_map_ready:
            self.control_zone_visible = not self.control_zone_visible
            self.page().runJavaScript("toggleControlZone();")
            return self.control_zone_visible
        return False

    def toggle_compass(self):
        """나침반 도구 표시/숨김 토글"""
        if self.is_map_ready:
            self.compass_visible = not self.compass_visible
            self.page().runJavaScript("toggleCompass();")
            return self.compass_visible
        return False

    @pyqtSlot(str)
    def compute_mgrs_grid(self, grid_points_json):
        """JavaScript에서 MGRS 변환 요청을 받아 처리"""
        try:
            grid_points = json.loads(grid_points_json)
            mgrs_grid_data = {}

            for point in grid_points:
                lat = point['lat']
                lon = point['lon']
                mgrs_coord = MGRSConverter.lat_lon_to_mgrs(lat, lon)
                key = f"{lat:.3f}_{lon:.3f}"
                mgrs_grid_data[key] = mgrs_coord

            # 결과를 JavaScript로 전달
            mgrs_grid_json = json.dumps(mgrs_grid_data)
            self.page().runJavaScript(f"window.mgrsGridData = {mgrs_grid_json};")
        except Exception as e:
            print(f"MGRS 그리드 변환 오류: {str(e)}")

    @pyqtSlot(float, float, str)
    def convert_single_mgrs(self, lat, lon, cache_key):
        """단일 좌표의 MGRS 변환 (마우스 추적용)"""
        try:
            mgrs_coord = MGRSConverter.lat_lon_to_mgrs(lat, lon)

            # JavaScript 캐시 업데이트
            cache_obj = {cache_key: mgrs_coord}
            cache_json = json.dumps(cache_obj)
            self.page().runJavaScript(f"""
                if (!window.cachedMgrsCoords) {{
                    window.cachedMgrsCoords = {{}};
                }}
                Object.assign(window.cachedMgrsCoords, {cache_json});
                // 현재 마우스 위치와 일치하면 업데이트
                if (coordsDisplay) {{
                    var currentText = coordsDisplay.textContent;
                    if (currentText.includes('계산 중...')) {{
                        var latStr = parseFloat('{lat}').toFixed(5);
                        var lonStr = parseFloat('{lon}').toFixed(5);
                        coordsDisplay.textContent = `LAT: ${{latStr}} LON: ${{lonStr}} MGRS: {mgrs_coord}`;
                    }}
                }}
            """)
        except Exception as e:
            print(f"MGRS 변환 오류: {str(e)}")

    def load_geojson_layers(self):
        """openAIP_data 디렉터리에서 GeoJSON 파일들을 로드하여 지도에 추가 (접두사 무관 오버레이)"""
        if not self.is_map_ready:
            return
        
        # 현재 파일의 디렉터리를 기준으로 openAIP_data 경로 설정
        current_dir = Path(__file__).parent
        geojson_dir = current_dir / "openAIP_data"
        
        # 지원하는 레이어 타입
        supported_layers = ['apt', 'nav', 'obs', 'raa', 'rca']
        
        # 디렉터리에서 GeoJSON 파일 검색 및 레이어별로 그룹화
        layer_files = {layer: [] for layer in supported_layers}
        
        if geojson_dir.exists():
            # 각 레이어 타입에 대해 모든 파일 찾기
            for layer_type in supported_layers:
                # 디렉터리에서 패턴에 맞는 모든 파일 검색
                for file_path in geojson_dir.glob(f'*_{layer_type}.geojson'):
                    layer_files[layer_type].append(file_path)
        
        # 사용 가능한 레이어 목록 저장
        self.available_layers = set()
        
        # 전체 파일 수 계산
        total_files = sum(len(files) for files in layer_files.values())
        loaded_count = 0
        
        for layer_key, file_paths in layer_files.items():
            if not file_paths:
                continue
            
            # 현재 레이어의 모든 파일을 병합
            merged_geojson = {
                'type': 'FeatureCollection',
                'features': []
            }
            
            for file_path in file_paths:
                loaded_count += 1
                
                # 스플래시 화면이 있으면 진행률 업데이트
                try:
                    if hasattr(self, 'splash') and self.splash:
                        self.splash.update_geojson_progress(loaded_count, total_files, file_path.name)
                except:
                    pass
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        geojson_data = json.load(f)
                    
                    # features 배열이 있으면 모두 병합
                    if 'features' in geojson_data:
                        merged_geojson['features'].extend(geojson_data['features'])
                    
                    print(f"GeoJSON 데이터 로드: {file_path.name}")
                except Exception as e:
                    print(f"GeoJSON 로드 오류 ({file_path.name}): {str(e)}")
            
            # 병합된 데이터가 있으면 지도에 추가
            if merged_geojson['features']:
                try:
                    geojson_json = json.dumps(merged_geojson)
                    self.page().runJavaScript(f"addGeoJsonLayer('{layer_key}', {geojson_json});")
                    self.available_layers.add(layer_key)
                    print(f"GeoJSON 레이어 로드 완료: {layer_key} ({len(merged_geojson['features'])}개 feature)")
                except Exception as e:
                    print(f"GeoJSON 레이어 추가 오류 ({layer_key}): {str(e)}")
        
        # 로드되지 않은 레이어 확인
        unloaded_layers = set(supported_layers) - self.available_layers
        if unloaded_layers:
            print(f"다음 레이어는 로드되지 않음: {', '.join(unloaded_layers)}")
    
    def update_mission_info_on_map(self, mission: Mission):
        """지도 위에 미션 정보 업데이트"""
        if not self.is_map_ready:
            return
        
        # 웨이포인트 간 거리 계산
        total_distance = sum(wp.distance for wp in mission.waypoints)
        
        # 평균 속도 계산
        avg_speed = 0
        if len(mission.waypoints) > 0:
            avg_speed = sum(wp.speed for wp in mission.waypoints) / len(mission.waypoints)
        
        # 비행시간 계산
        flight_hours = 0
        flight_minutes = 0
        if avg_speed > 0 and total_distance > 0:
            flight_hours_total = total_distance / avg_speed
            flight_hours = int(flight_hours_total)
            flight_minutes = int((flight_hours_total - flight_hours) * 60)
        
        # JavaScript로 미션 정보 업데이트
        mission_data = {
            'mission_name': mission.mission_name,
            'waypoint_count': len(mission.waypoints),
            'total_distance': total_distance,
            'avg_speed': avg_speed,
            'flight_hours': flight_hours,
            'flight_minutes': flight_minutes
        }
        
        mission_data_json = json.dumps(mission_data)
        self.page().runJavaScript(f"updateMissionInfo({mission_data_json});")


# ============================================================================
# 웨이포인트 편집 다이얼로그
# ============================================================================

class WaypointEditDialog(QDialog):
    def __init__(self, waypoint: Waypoint, parent=None, localization_manager=None):
        super().__init__(parent)
        self.waypoint = waypoint
        self.result = None
        self.loc = localization_manager
        self.init_ui()

    def init_ui(self):
        window_title = self.loc.get_text("main.window.waypoint_editor.title") if self.loc else "WAYPOINT EDITOR"
        self.setWindowTitle(window_title)
        self.setFixedWidth(450)
        # 로컬 스타일 최소화 (글로벌 스타일 활용)
        self.setStyleSheet("""
            QDialog { background-color: #1a1a1a; }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        form = QFormLayout()
        form.setVerticalSpacing(15)

        # 웨이포인트 이름
        self.name_input = QLineEdit(self.waypoint.name or "")
        placeholder = self.loc.get_text("main.placeholder.waypoint_name") if self.loc else "예: Alpha, Waypoint-1"
        self.name_input.setPlaceholderText(placeholder)
        label = self.loc.get_text("main.label.waypoint_name") if self.loc else "WAYPOINT NAME"
        form.addRow(label, self.name_input)

        # NATO 포네틱 버튼
        phonetic_layout = QHBoxLayout()
        self.phonetic_input = QLineEdit()
        self.phonetic_input.setReadOnly(True)
        phonetic_layout.addWidget(self.phonetic_input)

        btn_text = self.loc.get_text("main.button.convert") if self.loc else "변환"
        phonetic_btn = QPushButton(btn_text)
        phonetic_btn.setMaximumWidth(60)
        phonetic_btn.setStyleSheet("background-color: #00d1b2; color: #121212; border: none;")
        phonetic_btn.clicked.connect(self.convert_to_phonetic)
        phonetic_layout.addWidget(phonetic_btn)
        label = self.loc.get_text("main.label.nato_phonetic") if self.loc else "NATO PHONETIC"
        form.addRow(label, phonetic_layout)

        # 위경도 (읽기 전용)
        self.lat_input = QLineEdit(f"{self.waypoint.lat:.6f}")
        self.lat_input.setReadOnly(True)
        label = self.loc.get_text("main.label.latitude") if self.loc else "LATITUDE"
        form.addRow(label, self.lat_input)

        self.lon_input = QLineEdit(f"{self.waypoint.lon:.6f}")
        self.lon_input.setReadOnly(True)
        label = self.loc.get_text("main.label.longitude") if self.loc else "LONGITUDE"
        form.addRow(label, self.lon_input)

        # MGRS 좌표 (읽기 전용)
        mgrs_coord = MGRSConverter.lat_lon_to_mgrs(self.waypoint.lat, self.waypoint.lon)
        self.mgrs_input = QLineEdit(mgrs_coord)
        self.mgrs_input.setReadOnly(True)
        label = self.loc.get_text("main.label.mgrs") if self.loc else "MGRS"
        form.addRow(label, self.mgrs_input)

        # Alt
        self.alt_input = QSpinBox()
        self.alt_input.setRange(0, 5000)
        self.alt_input.setSuffix(" m")
        self.alt_input.setValue(int(self.waypoint.alt))
        label = self.loc.get_text("main.label.altitude") if self.loc else "ALTITUDE"
        form.addRow(label, self.alt_input)

        # Task Code
        self.task_input = QComboBox()
        self.task_input.addItems(
            ['TAKE_OFF', 'CRUISE', 'LANDING', 'RECON', 'STRIKE', 'RALLY', 'INFANTRY', 'ARMOR', 'ARTILLERY', 'AIR',
             'MEDEVAC'])
        self.task_input.setCurrentText(self.waypoint.task_code)
        label = self.loc.get_text("main.label.task") if self.loc else "TASK"
        form.addRow(label, self.task_input)

        # Speed
        self.speed_input = QSpinBox()
        self.speed_input.setRange(1, 500)  # Speed range in km/h
        self.speed_input.setSuffix(" km/h")
        self.speed_input.setValue(int(self.waypoint.speed))
        label = self.loc.get_text("main.label.speed") if self.loc else "SPEED"
        form.addRow(label, self.speed_input)

        # Target ETA (editable)
        self.eta_input = QLineEdit(self.waypoint.eta or "")
        placeholder = self.loc.get_text("main.placeholder.eta") if self.loc else "HH:MM (예: 14:30)"
        self.eta_input.setPlaceholderText(placeholder)
        label = self.loc.get_text("main.label.target_eta") if self.loc else "TARGET ETA"
        form.addRow(label, self.eta_input)

        layout.addLayout(form)

        # 버튼
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        btn_text = self.loc.get_text("main.button.delete") if self.loc else "DELETE"
        delete_btn = QPushButton(btn_text)
        delete_btn.setStyleSheet("background-color: #3d1a1a; color: #ff3860; border: 1px solid #ff3860;")
        delete_btn.clicked.connect(self.delete_waypoint)
        button_layout.addWidget(delete_btn)

        button_layout.addStretch()

        btn_text = self.loc.get_text("main.button.cancel") if self.loc else "CANCEL"
        cancel_btn = QPushButton(btn_text)
        cancel_btn.setStyleSheet("background-color: #2c2c2c; color: #e0e0e0; border: 1px solid #3d3d3d;")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        btn_text = self.loc.get_text("main.button.save") if self.loc else "SAVE"
        save_btn = QPushButton(btn_text)
        save_btn.setStyleSheet("background-color: #00d1b2; color: #121212; border: none;")
        save_btn.clicked.connect(self.save_waypoint)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def delete_waypoint(self):
        dialog_title = self.loc.get_text("main.dialog.confirm") if self.loc else "확인"
        msg_text = self.loc.get_text("main.dialog.delete_confirm") if self.loc else "정말 삭제하시겠습니까?"
        reply = QMessageBox.question(self, dialog_title, msg_text)
        if reply == QMessageBox.Yes:
            self.result = 'delete'
            self.accept()

    def save_waypoint(self):
        self.waypoint.name = self.name_input.text().strip() or ""
        self.waypoint.alt = float(self.alt_input.value())
        self.waypoint.task_code = self.task_input.currentText()
        self.waypoint.speed = float(self.speed_input.value())
        self.waypoint.eta = self.eta_input.text().strip() or None
        self.result = 'save'
        self.accept()

    def convert_to_phonetic(self):
        """Convert waypoint name to NATO phonetic alphabet."""
        name = self.name_input.text().strip()
        if not name:
            return
        phonetic = NATOPhoneticConverter.to_phonetic(name)
        self.phonetic_input.setText(phonetic)
        # Optionally set as name
        self.name_input.setText(phonetic)


# ============================================================================
# 웨이포인트 리스트 위젯
# ============================================================================

class WaypointListWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.list_widget = QListWidget(self)
        self.layout.addWidget(self.list_widget)

    def update_waypoints(self, waypoints: List[Waypoint]):
        """Update the list widget with waypoint details."""
        self.list_widget.clear()
        for i, wp in enumerate(waypoints):
            wp_name = wp.name if wp.name else f"Waypoint {i + 1}"
            distance_text = f" | {wp.distance}km" if wp.distance > 0 else ""
            wp_text = f"[{i + 1:02d}] {wp_name} | 속도 {wp.speed}km/h | ETA {wp.eta}{distance_text}"
            item = QListWidgetItem(wp_text)
            self.list_widget.addItem(item)


# ============================================================================
# 메인 윈도우
# ============================================================================

class DARTMainWindow(QMainWindow):
    def __init__(self, splash=None, localization_manager=None):
        super().__init__()
        self.splash = splash
        self.loc = localization_manager
        
        # 스플레시에서 app_info 가져오기
        self.app_info = splash.app_info if splash else {}
        
        if self.splash:
            msg = self.loc.get_text("main.status.initializing_main_window") if self.loc else "메인 창 초기화..."
            self.splash.set_progress(0.1, msg)
        
        window_title = self.loc.get_text("main.window.title") if self.loc else "DART - Drone Analytics & Routing Tool"
        self.setWindowTitle(window_title)
        self.setGeometry(0, 0, 1920, 1080)

        if self.splash:
            msg = self.loc.get_text("main.status.connecting_database") if self.loc else "데이터베이스 연결..."
            self.splash.set_progress(0.2, msg)
        
        self.db = MissionDatabase()
        self.missions = []
        self.current_mission_index = -1

        if self.splash:
            msg = self.loc.get_text("main.status.creating_ui") if self.loc else "UI 컴포넌트 생성..."
            self.splash.set_progress(0.4, msg)
        
        self.init_ui()
        
        if self.splash:
            msg = self.loc.get_text("main.status.loading_missions") if self.loc else "미션 데이터 로딩..."
            self.splash.set_progress(0.7, msg)
        
        self.load_missions()

        if self.splash:
            self.splash.set_progress(0.85, "스타일 적용...")
        
        self.apply_modern_style()

        if self.splash:
            self.splash.set_progress(0.95, "GeoJSON 데이터 준비...")
        
        # Connect database signal to UI update
        if hasattr(self.db, 'mission_updated'):
            self.db.mission_updated.connect(self.on_mission_updated)
        
        # GeoJSON 로딩은 지도가 준비된 후에
        QTimer.singleShot(100, self.delayed_geojson_loading)
    
    def delayed_geojson_loading(self):
        """지도가 준비된 후 GeoJSON 데이터를 로딩"""
        if hasattr(self, 'map_view') and hasattr(self.map_view, 'load_geojson_layers'):
            self.map_view.load_geojson_layers()

    def apply_modern_style(self):
        self.setStyleSheet("""
            /* Base Colors */
            QMainWindow, QDialog, QMessageBox, QMenu {
                background-color: #1a1a1a;
                color: #e0e0e0;
            }
            QWidget {
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
            }

            /* Labels */
            QLabel {
                color: #e0e0e0;
                background: transparent;
            }

            /* Button Base */
            QPushButton {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 8px 16px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #444444;
                border-color: #00d1b2;
            }
            QPushButton:pressed {
                background-color: #222222;
            }

            /* Special Buttons */
            QPushButton#primaryButton {
                background-color: #00d1b2;
                color: #ffffff;
                border: none;
                font-weight: bold;
            }
            QPushButton#primaryButton:hover {
                background-color: #00b89c;
            }

            QPushButton#secondaryButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
            }
            QPushButton#secondaryButton:hover {
                background-color: #444444;
                border-color: #00d1b2;
            }

            /* Inputs */
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #2a2a2a;
                color: #ffffff !important; /* 강제로 하얀색 적용 */
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px;
                selection-background-color: #00d1b2;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #00d1b2;
            }

            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #00d1b2;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                color: #e0e0e0;
                selection-background-color: #00d1b2;
                selection-color: #121212;
                border: 1px solid #444444;
                outline: none;
            }

            /* Tabs */
            QTabWidget::pane {
                border: 1px solid #333333;
                background-color: #1a1a1a;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #2a2a2a;
                color: #b0b0b0;
                padding: 10px 20px;
                border: 1px solid #333333;
                border-bottom: none;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1a1a1a;
                color: #00d1b2;
                border-bottom: 2px solid #00d1b2;
            }

            /* List / Table */
            QListWidget {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                color: #e0e0e0;
                outline: none;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #262626;
            }
            QListWidget::item:selected {
                background-color: #2a2a2a;
                color: #00d1b2;
            }

            /* ScrollBar */
            QScrollBar:vertical {
                border: none;
                background: #1a1a1a;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #444444;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #555555;
            }

            /* Dialog specific */
            QDialog QLabel {
                color: #e0e0e0;
            }
            QMessageBox QLabel {
                color: #ffffff;
            }

            /* ButtonBox */
            QDialogButtonBox QPushButton {
                background-color: #333333;
                color: #ffffff;
                min-width: 80px;
            }
        """)

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # HUD
        hud = self.create_hud()
        main_layout.addWidget(hud, stretch=0)

        # 중간 (지도 + 패널)
        middle_layout = QHBoxLayout()

        # 좌측 패널
        self.mission_panel = self.create_mission_panel()
        middle_layout.addWidget(self.mission_panel, stretch=1)

        # 지도
        self.map_view = TacticalMapView(self, self.splash, self.loc)
        self.map_view.waypoint_added.connect(self.add_waypoint)
        self.map_view.waypoint_deleted.connect(self.delete_waypoint)
        self.map_view.waypoint_updated.connect(self.update_waypoint)
        self.map_view.waypoint_moved.connect(self.moved_waypoint)
        self.map_view.geojson_layers_loaded.connect(self.update_geojson_combo)
        middle_layout.addWidget(self.map_view, stretch=4)

        main_layout.addLayout(middle_layout, stretch=4)

        # 웨이포인트 리스트 위젯 토글 섹션
        waypoint_control_layout = QHBoxLayout()
        btn_text = self.loc.get_text("main.label.waypoint_list") if self.loc else "▼ 웨이포인트 목록"
        toggle_list_btn = QPushButton("▼ " + btn_text)
        toggle_list_btn.setObjectName("secondaryButton")
        toggle_list_btn.setMaximumWidth(200)
        toggle_list_btn.clicked.connect(self.toggle_waypoint_list)
        self.toggle_list_btn = toggle_list_btn  # 나중에 텍스트 변경용
        waypoint_control_layout.addWidget(toggle_list_btn)
        waypoint_control_layout.addStretch()
        main_layout.addLayout(waypoint_control_layout, stretch=0)

        # 웨이포인트 리스트 위젯 추가
        self.waypoint_list_widget = WaypointListWidget()
        main_layout.addWidget(self.waypoint_list_widget, stretch=1)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def toggle_waypoint_list(self):
        """웨이포인트 리스트 위젯 표시/숨김 토글"""
        is_visible = self.waypoint_list_widget.isVisible()
        self.waypoint_list_widget.setVisible(not is_visible)

        # 버튼 텍스트 업데이트
        label_text = self.loc.get_text("main.label.waypoint_list") if self.loc else "웨이포인트 목록"
        if self.waypoint_list_widget.isVisible():
            self.toggle_list_btn.setText("▼ " + label_text)
        else:
            self.toggle_list_btn.setText("▶ " + label_text)

    def toggle_mgrs_grid(self):
        """MGRS 그리드 표시/숨김 토글"""
        is_visible = self.map_view.toggle_mgrs_grid()
        if is_visible:
            self.mgrs_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #00d1b2;
                    color: #121212;
                    border: 1px solid #00d1b2;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #00b89c;
                }
            """)
        else:
            self.mgrs_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #333333;
                    color: #e0e0e0;
                    border: 1px solid #444444;
                    border-radius: 4px;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    background-color: #444444;
                    border-color: #00d1b2;
                }
                QPushButton:pressed {
                    background-color: #00d1b2;
                    color: #121212;
                }
            """)

    def toggle_coords_display(self):
        """좌표 표시 토글"""
        is_visible = self.map_view.toggle_coords_display()
        if is_visible:
            self.coords_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #00d1b2;
                    color: #121212;
                    border: 1px solid #00d1b2;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #00b89c;
                }
            """)
        else:
            self.coords_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #333333;
                    color: #e0e0e0;
                    border: 1px solid #444444;
                    border-radius: 4px;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    background-color: #444444;
                    border-color: #00d1b2;
                }
                QPushButton:pressed {
                    background-color: #00d1b2;
                    color: #121212;
                }
            """)

    def toggle_control_zones(self):
        """관제권 표시 토글"""
        is_visible = self.map_view.toggle_control_zone()
        if is_visible:
            self.control_zone_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ff0000;
                    color: #ffffff;
                    border: 1px solid #ff0000;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #cc0000;
                }
            """)
        else:
            self.control_zone_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #333333;
                    color: #e0e0e0;
                    border: 1px solid #444444;
                    border-radius: 4px;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    background-color: #444444;
                    border-color: #ff0000;
                }
                QPushButton:pressed {
                    background-color: #ff0000;
                    color: #ffffff;
                }
            """)

    def toggle_compass(self):
        """나침반 도구 토글"""
        is_visible = self.map_view.toggle_compass()
        if is_visible:
            self.compass_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #00d1b2;
                    color: #121212;
                    border: 1px solid #00d1b2;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #00c9a8;
                }
            """)
        else:
            self.compass_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #333333;
                    color: #e0e0e0;
                    border: 1px solid #444444;
                    border-radius: 4px;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    background-color: #444444;
                    border-color: #00d1b2;
                }
                QPushButton:pressed {
                    background-color: #00d1b2;
                    color: #121212;
                }
            """)

    def toggle_geojson_layer(self, layer_key):
        """GeoJSON 레이어 토글"""
        # 레이어 파일이 존재하는지 확인
        if hasattr(self.map_view, 'available_layers') and layer_key not in self.map_view.available_layers:
            QMessageBox.warning(self, "레이어 사용 불가", 
                              f"'{layer_key}' 레이어 파일이 openAIP_data 디렉터리에 존재하지 않습니다.")
            return
        
        is_visible = self.map_view.toggle_geojson_layer(layer_key)
        # 토글 상태에 따라 버튼 스타일 업데이트 (선택사항)

    def update_geojson_combo(self):
        """사용 가능한 GeoJSON 레이어만 드롭다운에 표시"""
        if not hasattr(self.map_view, 'available_layers'):
            return
        
        # 기존 항목 제거 (첫 번째 "GeoJSON 선택" 항목 제외)
        while self.geojson_layer_combo.count() > 1:
            self.geojson_layer_combo.removeItem(1)
        
        # 사용 가능한 레이어만 추가
        for display_name, layer_key, color in self.all_geojson_layers:
            if layer_key in self.map_view.available_layers:
                self.geojson_layer_combo.addItem(f"{display_name} ✓", layer_key)
            else:
                self.geojson_layer_combo.addItem(f"{display_name} (사용불가능)", layer_key)
                # 비활성 항목은 선택할 수 없도록 처리
                item_index = self.geojson_layer_combo.count() - 1
                item = self.geojson_layer_combo.model().item(item_index)
                if item:
                    item.setEnabled(False)
    
    def on_geojson_layer_selected(self, index):
        """드롭다운에서 GeoJSON 레이어 선택"""
        if index <= 0:  # "GeoJSON 선택" 기본값 또는 인덱스 0
            return
        
        layer_key = self.geojson_layer_combo.currentData()
        if layer_key and hasattr(self.map_view, 'available_layers') and layer_key in self.map_view.available_layers:
            self.toggle_geojson_layer(layer_key)
        # 선택 후 드롭다운을 기본값으로 리셋
        self.geojson_layer_combo.setCurrentIndex(0)

    def create_hud(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(30)

        # 로고
        logo_label = QLabel("DART")
        logo_label.setStyleSheet("color: #00d1b2; font-size: 20px; font-weight: bold; letter-spacing: 2px;")
        layout.addWidget(logo_label)

        layout.addSpacing(20)

        # 미션명
        self.hud_mission_label = QLabel("MISSION: [준비 중]")
        self.hud_mission_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.hud_mission_label.setStyleSheet("color: #e0e0e0;")
        layout.addWidget(self.hud_mission_label)

        layout.addSpacing(20)

        # 웨이포인트 카운트
        self.hud_waypoint_label = QLabel("WP: 0")
        self.hud_waypoint_label.setFont(QFont("Segoe UI", 10))
        self.hud_waypoint_label.setStyleSheet("color: #b0b0b0;")
        layout.addWidget(self.hud_waypoint_label)

        # 총 거리
        self.hud_distance_label = QLabel("DIST: 0 km")
        self.hud_distance_label.setFont(QFont("Segoe UI", 10))
        self.hud_distance_label.setStyleSheet("color: #b0b0b0;")
        layout.addWidget(self.hud_distance_label)

        # 평균 속도
        self.hud_avg_speed_label = QLabel("AVG SPD: 0 km/h")
        self.hud_avg_speed_label.setFont(QFont("Segoe UI", 10))
        self.hud_avg_speed_label.setStyleSheet("color: #b0b0b0;")
        layout.addWidget(self.hud_avg_speed_label)

        # 예상 비행시간
        self.hud_flight_time_label = QLabel("ETA: 0 h")
        self.hud_flight_time_label.setFont(QFont("Segoe UI", 10))
        self.hud_flight_time_label.setStyleSheet("color: #b0b0b0;")
        layout.addWidget(self.hud_flight_time_label)

        # 마지막 저장
        self.hud_last_save_label = QLabel("SAVED: -")
        self.hud_last_save_label.setFont(QFont("Segoe UI", 9))
        self.hud_last_save_label.setStyleSheet("color: #808080;")
        layout.addWidget(self.hud_last_save_label)

        layout.addStretch()

        # MGRS 그리드 토글 버튼
        btn_text = self.loc.get_text("main.button.mgrs_grid") if self.loc else "MGRS GRID"
        self.mgrs_toggle_btn = QPushButton(btn_text)
        self.mgrs_toggle_btn.setMaximumWidth(80)
        self.mgrs_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #444444;
                border-color: #00d1b2;
            }
            QPushButton:pressed {
                background-color: #00d1b2;
                color: #121212;
            }
        """)
        self.mgrs_toggle_btn.setFont(QFont("Segoe UI", 9))
        self.mgrs_toggle_btn.clicked.connect(self.toggle_mgrs_grid)
        layout.addWidget(self.mgrs_toggle_btn)

        # 좌표 표시 토글 버튼
        btn_text = self.loc.get_text("main.button.coords") if self.loc else "COORDS"
        self.coords_toggle_btn = QPushButton(btn_text)
        self.coords_toggle_btn.setMaximumWidth(100)
        self.coords_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #444444;
                border-color: #00d1b2;
            }
            QPushButton:pressed {
                background-color: #00d1b2;
                color: #121212;
            }
        """)
        self.coords_toggle_btn.setFont(QFont("Segoe UI", 9))
        self.coords_toggle_btn.clicked.connect(self.toggle_coords_display)
        layout.addWidget(self.coords_toggle_btn)

        # 관제권 표시 토글 버튼
        btn_text = self.loc.get_text("main.button.control_zone") if self.loc else "관제권"
        self.control_zone_toggle_btn = QPushButton(btn_text)
        self.control_zone_toggle_btn.setMaximumWidth(100)
        self.control_zone_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #444444;
                border-color: #ff0000;
            }
            QPushButton:pressed {
                background-color: #ff0000;
                color: #ffffff;
            }
        """)
        self.control_zone_toggle_btn.setFont(QFont("Segoe UI", 9))
        self.control_zone_toggle_btn.clicked.connect(self.toggle_control_zones)
        layout.addWidget(self.control_zone_toggle_btn)

        # 나침반 도구 토글 버튼
        btn_text = self.loc.get_text("main.button.compass") if self.loc else "Compass"
        self.compass_toggle_btn = QPushButton(btn_text)
        self.compass_toggle_btn.setMaximumWidth(100)
        self.compass_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #444444;
                border-color: #00d1b2;
            }
            QPushButton:pressed {
                background-color: #00d1b2;
                color: #121212;
            }
        """)
        self.compass_toggle_btn.setFont(QFont("Segoe UI", 9))
        self.compass_toggle_btn.clicked.connect(self.toggle_compass)
        layout.addWidget(self.compass_toggle_btn)

        # GeoJSON 레이어 선택 드롭다운
        self.all_geojson_layers = [
            ("APT - 공항", "apt", "#ff6b6b"),
            ("NAV - 네비게이션", "nav", "#4ecdc4"),
            ("OBS - 장애물", "obs", "#ffe66d"),
            ("RAA - 제한구역", "raa", "#a8e6cf"),
            ("RCA - R-Class", "rca", "#ffd3b6")
        ]
        
        self.geojson_layer_combo = QComboBox()
        self.geojson_layer_combo.setMaximumWidth(150)
        self.geojson_layer_combo.addItem("GeoJSON 선택", None)
        
        # 일단 모든 레이어를 추가 (나중에 update_geojson_combo에서 업데이트됨)
        for display_name, layer_key, color in self.all_geojson_layers:
            self.geojson_layer_combo.addItem(display_name, layer_key)
        
        self.geojson_layer_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9px;
            }
            QComboBox:hover {
                border-color: #00d1b2;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #00d1b2;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                color: #e0e0e0;
                selection-background-color: #00d1b2;
                selection-color: #121212;
                border: 1px solid #444444;
                outline: none;
                padding: 4px;
            }
        """)
        self.geojson_layer_combo.setFont(QFont("Segoe UI", 9))
        self.geojson_layer_combo.currentIndexChanged.connect(self.on_geojson_layer_selected)
        layout.addWidget(self.geojson_layer_combo)

        # 버전
        version_text = f"v{self.app_info.get('version', '?')}"
        if self.app_info.get('version_detail'):
            version_text += f" ({self.app_info.get('version_detail')})"
        version_label = QLabel(version_text)
        version_label.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(version_label)

        widget.setLayout(layout)
        widget.setFixedHeight(60)
        widget.setStyleSheet("background-color: #1a1a1a; border-bottom: 2px solid #00d1b2;")
        return widget

    def create_mission_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.mission_tabs = QTabWidget()
        self.mission_tabs.setTabsClosable(True)
        self.mission_tabs.tabCloseRequested.connect(self.close_mission_tab)
        self.mission_tabs.currentChanged.connect(self.on_mission_tab_changed)
        layout.addWidget(self.mission_tabs, stretch=3)

        new_mission_btn = QPushButton(self.loc.get_text("main.button.new_mission") if self.loc else "➕ 새 미션 추가")
        new_mission_btn.setObjectName("primaryButton")
        new_mission_btn.clicked.connect(self.create_new_mission)
        layout.addWidget(new_mission_btn)

        insert_wp_btn = QPushButton(self.loc.get_text("main.button.insert_waypoint") if self.loc else "웨이포인트 삽입")
        insert_wp_btn.setObjectName("secondaryButton")
        insert_wp_btn.clicked.connect(self.prompt_insert_waypoint)
        layout.addWidget(insert_wp_btn)

        save_btn = QPushButton(self.loc.get_text("main.button.local_save") if self.loc else "로컬 저장")
        save_btn.setObjectName("secondaryButton")
        save_btn.clicked.connect(self.save_all_missions)
        layout.addWidget(save_btn)

        export_layout = QHBoxLayout()
        export_json_btn = QPushButton(self.loc.get_text("main.button.export_json") if self.loc else "JSON")
        export_json_btn.setObjectName("secondaryButton")
        export_json_btn.clicked.connect(self.export_json)
        export_layout.addWidget(export_json_btn)

        export_csv_btn = QPushButton(self.loc.get_text("main.button.export_csv") if self.loc else "CSV")
        export_csv_btn.setObjectName("secondaryButton")
        export_csv_btn.clicked.connect(self.export_csv)
        export_layout.addWidget(export_csv_btn)

        layout.addLayout(export_layout)

        widget.setLayout(layout)
        widget.setStyleSheet("background-color: #121212;")
        return widget


    def create_mission_tab_content(self, mission: Mission) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        info_card = QWidget()
        info_card.setStyleSheet("background-color: #1e1e1e; border-radius: 8px; padding: 5px;")
        info_layout = QFormLayout(info_card)
        info_layout.setLabelAlignment(Qt.AlignRight)

        def create_info_label(text, bold=False):
            lbl = QLabel(text)
            if bold:
                lbl.setStyleSheet("font-weight: bold; color: #00d1b2;")
            else:
                lbl.setStyleSheet("color: #b0b0b0;")
            return lbl

        info_layout.addRow(create_info_label("ID:"), create_info_label(mission.mission_id))
        info_layout.addRow(create_info_label("NAME:"), create_info_label(mission.mission_name, True))
        info_layout.addRow(create_info_label("CREATED:"), create_info_label(mission.created_at[:10]))

        layout.addWidget(info_card)

        # 웨이포인트 타이틀
        wp_header = QHBoxLayout()
        wp_title = QLabel("WAYPOINTS")
        wp_title.setStyleSheet("font-weight: bold; color: #00d1b2; font-size: 14px;")
        wp_header.addWidget(wp_title)
        wp_header.addStretch()
        layout.addLayout(wp_header)

        waypoint_list = QListWidget()
        waypoint_list.setAlternatingRowColors(False)

        for idx, wp in enumerate(mission.waypoints):
            color = MilitarySymbolGenerator.get_color(wp.task_code)
            eta_display = wp.eta if wp.eta else "미설정"
            wp_name = wp.name if wp.name else f"WP-{idx + 1:02d}"
            item_text = f"{idx + 1:02d} | {wp_name:<12} | {wp.task_code:<8} | Alt: {int(wp.alt)}m | Speed: {wp.speed} km/h | ETA: {eta_display}"
            item = QListWidgetItem(item_text)
            item.setToolTip(f"Lat: {wp.lat:.5f}, Lon: {wp.lon:.5f}, Distance: {wp.distance:.2f}km")
            waypoint_list.addItem(item)

        layout.addWidget(waypoint_list)
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def load_missions(self):
        self.missions = self.db.load_missions()
        for mission in self.missions:
            tab = self.create_mission_tab_content(mission)
            self.mission_tabs.addTab(tab, mission.mission_name)

        if self.missions:
            self.mission_tabs.setCurrentIndex(0)
            self.on_mission_tab_changed(0)

    def on_mission_tab_changed(self, index):
        if 0 <= index < len(self.missions):
            self.current_mission_index = index
            mission = self.missions[index]
            self.map_view.load_mission(mission)
            self.waypoint_list_widget.update_waypoints(mission.waypoints)  # 웨이포인트 리스트 업데이트
            self.update_hud()
            
            # 지도 위에 미션 정보 업데이트
            if hasattr(self.map_view, 'update_mission_info_on_map'):
                self.map_view.update_mission_info_on_map(mission)

    def create_new_mission(self):
        dialog = QDialog(self)
        dialog_title = self.loc.get_text("main.dialog.create_new_mission") if self.loc else "CREATE NEW MISSION"
        dialog.setWindowTitle(dialog_title)
        dialog.setFixedWidth(400)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title_text = self.loc.get_text("main.label.mission_details") if self.loc else "MISSION DETAILS"
        title = QLabel(title_text)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00d1b2; margin-bottom: 10px;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setVerticalSpacing(15)

        name_input = QLineEdit()
        name_input.setText(f"Mission_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        name_input.setMinimumHeight(35)
        label = self.loc.get_text("main.label.mission_name") if self.loc else "MISSION NAME"
        form.addRow(label, name_input)
        layout.addLayout(form)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        btn_text = self.loc.get_text("main.button.cancel") if self.loc else "CANCEL"
        cancel_btn = QPushButton(btn_text)
        cancel_btn.setMinimumHeight(35)
        cancel_btn.clicked.connect(dialog.reject)

        btn_text = self.loc.get_text("main.button.create_mission") if self.loc else "CREATE MISSION"
        create_btn = QPushButton(btn_text)
        create_btn.setObjectName("primaryButton")
        create_btn.setMinimumHeight(35)
        create_btn.clicked.connect(dialog.accept)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(create_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            mission_name = name_input.text()
            mission_id = f"M_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            mission = Mission(mission_id, mission_name, [])

            self.missions.append(mission)
            tab = self.create_mission_tab_content(mission)
            self.mission_tabs.addTab(tab, mission_name)
            self.mission_tabs.setCurrentIndex(len(self.missions) - 1)

    def close_mission_tab(self, index):
        if 0 <= index < len(self.missions):
            del self.missions[index]
            self.mission_tabs.removeTab(index)

    def get_current_mission(self) -> Optional[Mission]:
        if 0 <= self.current_mission_index < len(self.missions):
            return self.missions[self.current_mission_index]
        return None

    def insert_waypoint(self, wp1_id, wp2_id):
        """웨이포인트 1과 웨이포인트 2 사이에 새 웨이포인트 삽입"""
        mission = self.get_current_mission()
        if not mission:
            warn_title = self.loc.get_text("main.dialog.warning") if self.loc else "경고"
            warn_msg = self.loc.get_text("main.message.mission_not_selected") if self.loc else "먼저 미션을 선택하세요"
            QMessageBox.warning(self, warn_title, warn_msg)
            return

        # 웨이포인트 1과 2를 찾기
        wp1 = next((wp for wp in mission.waypoints if wp.wp_id == wp1_id), None)
        wp2 = next((wp for wp in mission.waypoints if wp.wp_id == wp2_id), None)

        if not wp1 or not wp2:
            warn_title = self.loc.get_text("main.dialog.warning") if self.loc else "경고"
            warn_msg = self.loc.get_text("main.message.waypoint_not_found") if self.loc else "웨이포인트를 찾을 수 없습니다"
            QMessageBox.warning(self, warn_title, warn_msg)
            return

        # 중간 지점 계산
        mid_lat = (wp1.lat + wp2.lat) / 2
        mid_lon = (wp1.lon + wp2.lon) / 2
        mid_alt = (wp1.alt + wp2.alt) / 2
        mid_speed = (wp1.speed + wp2.speed) / 2

        # wp2의 인덱스 찾기
        wp_index = mission.waypoints.index(wp2)

        # NATO Phonetic 이름 생성
        nato_name = NATOPhoneticConverter.get_phonetic_for_index(wp_index)

        # 새 웨이포인트 생성
        new_wp = Waypoint(
            lat=mid_lat,
            lon=mid_lon,
            alt=mid_alt,
            speed=mid_speed,
            task_code="CRUISE",
            name=nato_name
        )

        # 리스트에 삽입
        mission.waypoints.insert(wp_index, new_wp)

        # UI 업데이트
        self.refresh_display()
        QMessageBox.information(self, "성공", f"웨이포인트가 {wp1.name}과 {wp2.name} 사이에 삽입되었습니다")

    def prompt_insert_waypoint(self):
        """웨이포인트 삽입을 위한 다이얼로그 표시"""
        mission = self.get_current_mission()
        if not mission or len(mission.waypoints) < 2:
            QMessageBox.warning(self, "경고", "웨이포인트가 2개 이상 필요합니다")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("웨이포인트 삽입")
        dialog.setFixedWidth(400)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel("삽입할 웨이포인트 선택")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00d1b2; margin-bottom: 10px;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setVerticalSpacing(15)

        # 웨이포인트 1 선택
        wp1_combo = QComboBox()
        wp1_combo.addItems([f"{wp.name} (ALT: {wp.alt}m)" for wp in mission.waypoints])
        form.addRow("시작 웨이포인트", wp1_combo)

        # 웨이포인트 2 선택
        wp2_combo = QComboBox()
        wp2_combo.addItems([f"{wp.name} (ALT: {wp.alt}m)" for wp in mission.waypoints])
        wp2_combo.setCurrentIndex(1)  # 기본값: 두 번째 웨이포인트
        form.addRow("종료 웨이포인트", wp2_combo)

        layout.addLayout(form)

        # 설명
        desc_label = QLabel("선택한 두 웨이포인트 사이에 새로운 웨이포인트가 생성됩니다")
        desc_label.setStyleSheet("color: #b0b0b0; font-size: 11px;")
        layout.addWidget(desc_label)

        # 버튼
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        cancel_btn = QPushButton("취소")
        cancel_btn.setStyleSheet("background-color: #2c2c2c; color: #e0e0e0; border: 1px solid #3d3d3d;")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        insert_btn = QPushButton("삽입")
        insert_btn.setObjectName("primaryButton")
        insert_btn.clicked.connect(lambda: dialog.accept())
        button_layout.addWidget(insert_btn)

        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            wp1_index = wp1_combo.currentIndex()
            wp2_index = wp2_combo.currentIndex()

            if wp1_index >= 0 and wp2_index >= 0 and wp1_index != wp2_index:
                wp1_id = mission.waypoints[wp1_index].wp_id
                wp2_id = mission.waypoints[wp2_index].wp_id
                self.insert_waypoint(wp1_id, wp2_id)
            else:
                QMessageBox.warning(self, "경고", "유효한 웨이포인트를 선택하세요")

    def add_waypoint(self, lat, lon):
        mission = self.get_current_mission()
        if not mission:
            QMessageBox.warning(self, "경고", "먼저 미션을 선택하세요")
            return

        # NATO Phonetic 이름 자동 생성
        wp_index = len(mission.waypoints)
        nato_name = NATOPhoneticConverter.get_phonetic_for_index(wp_index)

        wp = Waypoint(lat=lat, lon=lon, alt=100, task_code="RECON", name=nato_name)
        mission.waypoints.append(wp)
        self.refresh_display()

    def delete_waypoint(self, wp_id):
        mission = self.get_current_mission()
        if mission:
            mission.waypoints = [wp for wp in mission.waypoints if wp.wp_id != wp_id]
            self.refresh_display()

    def update_waypoint(self, wp_id, alt, task_code, speed):
        mission = self.get_current_mission()
        if mission:
            for wp in mission.waypoints:
                if wp.wp_id == wp_id:
                    wp.alt = alt
                    wp.task_code = task_code
                    wp.speed = speed
                    break
            self.refresh_display()

    def moved_waypoint(self, wp_id, lat, lon):
        mission = self.get_current_mission()
        if mission:
            for wp in mission.waypoints:
                if wp.wp_id == wp_id:
                    wp.lat = lat
                    wp.lon = lon
                    break
            self.refresh_display()

    def refresh_display(self):
        mission = self.get_current_mission()
        if mission:
            # 웨이포인트 간의 거리 계산
            self.calculate_waypoint_distances(mission)

            self.map_view.refresh_map(mission)
            self.update_mission_tab(mission)
            self.update_hud()
            self.waypoint_list_widget.update_waypoints(mission.waypoints)  # 웨이포인트 리스트 위젯 업데이트
            
            # 지도 위에 미션 정보 업데이트
            if hasattr(self.map_view, 'update_mission_info_on_map'):
                self.map_view.update_mission_info_on_map(mission)

    def calculate_waypoint_distances(self, mission: Mission):
        """각 웨이포인트 간의 거리를 계산하고 저장"""
        for i, wp in enumerate(mission.waypoints):
            if i == 0:
                wp.distance = 0.0  # 첫 번째 웨이포인트는 거리가 0
            else:
                prev_wp = mission.waypoints[i - 1]
                # geopy를 사용한 거리 계산 (km)
                dist = distance((prev_wp.lat, prev_wp.lon), (wp.lat, wp.lon)).km
                wp.distance = round(dist, 2)

    def update_mission_tab(self, mission: Mission):
        current_index = self.mission_tabs.currentIndex()
        if current_index >= 0:
            tab = self.create_mission_tab_content(mission)
            self.mission_tabs.blockSignals(True)
            self.mission_tabs.removeTab(current_index)
            self.mission_tabs.insertTab(current_index, tab, mission.mission_name)
            self.mission_tabs.setCurrentIndex(current_index)
            self.mission_tabs.blockSignals(False)

    def update_hud(self):
        mission = self.get_current_mission()
        if mission:
            # 미션명
            self.hud_mission_label.setText(f"MISSION: {mission.mission_name}")

            # 웨이포인트 카운트
            wp_count = len(mission.waypoints)
            self.hud_waypoint_label.setText(f"WP: {wp_count}")

            # 총 거리 계산
            total_distance = sum(wp.distance for wp in mission.waypoints)
            self.hud_distance_label.setText(f"DIST: {total_distance:.1f} km")

            # 평균 속도 계산
            if wp_count > 0:
                avg_speed = sum(wp.speed for wp in mission.waypoints) / wp_count
                self.hud_avg_speed_label.setText(f"AVG SPD: {avg_speed:.1f} km/h")

                # 예상 비행시간 계산 (총거리 / 평균속도)
                if avg_speed > 0:
                    flight_hours = total_distance / avg_speed
                    hours = int(flight_hours)
                    minutes = int((flight_hours - hours) * 60)
                    self.hud_flight_time_label.setText(f"ETA: {hours}h {minutes}m")
                else:
                    self.hud_flight_time_label.setText("ETA: - ")
            else:
                self.hud_avg_speed_label.setText("AVG SPD: 0 km/h")
                self.hud_flight_time_label.setText("ETA: 0 h")

            # 마지막 저장 시간
            if mission.last_saved_at:
                last_save_dt = datetime.fromisoformat(mission.last_saved_at)
                now_dt = datetime.now()
                diff = now_dt - last_save_dt

                if diff.total_seconds() < 60:
                    save_text = "SAVED: 방금"
                elif diff.total_seconds() < 3600:
                    minutes = int(diff.total_seconds() / 60)
                    save_text = f"SAVED: {minutes}분 전"
                elif diff.total_seconds() < 86400:
                    hours = int(diff.total_seconds() / 3600)
                    save_text = f"SAVED: {hours}시간 전"
                else:
                    days = int(diff.total_seconds() / 86400)
                    save_text = f"SAVED: {days}일 전"
                self.hud_last_save_label.setText(save_text)
            else:
                self.hud_last_save_label.setText("SAVED: -")
        else:
            self.hud_mission_label.setText("MISSION: [없음]")
            self.hud_waypoint_label.setText("WP: 0")
            self.hud_distance_label.setText("DIST: 0 km")
            self.hud_avg_speed_label.setText("AVG SPD: 0 km/h")
            self.hud_flight_time_label.setText("ETA: 0 h")
            self.hud_last_save_label.setText("SAVED: -")

    def save_all_missions(self):
        for mission in self.missions:
            self.db.save_mission(mission)
        QMessageBox.information(self, "완료", "모든 미션이 저장되었습니다")

    def export_json(self):
        mission = self.get_current_mission()
        if not mission:
            QMessageBox.warning(self, "경고", "미션을 선택하세요")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "JSON 내보내기", f"./exports/{mission.mission_id}.json", "JSON Files (*.json)"
        )

        if file_path:
            data = {
                'mission_id': mission.mission_id,
                'mission_name': mission.mission_name,
                'created_at': mission.created_at,
                'waypoints': [wp.to_dict() for wp in mission.waypoints]
            }

            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "완료", f"저장됨: {file_path}")

    def export_csv(self):
        mission = self.get_current_mission()
        if not mission:
            QMessageBox.warning(self, "경고", "미션을 선택하세요")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "CSV 내보내기", f"./exports/{mission.mission_id}.csv", "CSV Files (*.csv)"
        )

        if file_path:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8-sig') as f:
                f.write("순서,웨이포인트명,위도,경도,고도(m),작업코드,속도(km/h),목표ETA,거리(km)\n")
                for idx, wp in enumerate(mission.waypoints, 1):
                    wp_name = wp.name if wp.name else f"WP-{idx:02d}"
                    eta_value = wp.eta if wp.eta else ""
                    f.write(
                        f"{idx},{wp_name},{wp.lat},{wp.lon},{wp.alt},{wp.task_code},{wp.speed},{eta_value},{wp.distance}\n")

            QMessageBox.information(self, "완료", f"저장됨: {file_path}")

    def on_mission_updated(self, mission: Mission):
        """Handle mission updates and refresh the UI."""
        self.load_mission(mission)


# ============================================================================
# 메인 실행
# ============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Pre-main stage 플러그인 실행
    plugin_loader.run_plugins("pre-main", context=plugin_context)
    
    # 스플레시 화면 표시 (수동 모드 - 실제 로딩과 동기화)
    splash = show_splash_screen()
    
    # 애플리케이션 정보 설정
    app_info = {
        'version': '1.3',
        'version_detail': 'BETA',
        'build_number': '001',
        'build_date': '2026-01-18',
        'developer': 'STUDIO CSGNS',
        'license': 'GPLv3 License',
        'copyright': '© 2026 STUDIO CSGNS'
    }
    splash.set_app_info(app_info)
    
    splash.set_progress(0.05, "애플리케이션 시작...")
    
    # Splash stage 플러그인 실행
    plugin_loader.run_plugins("splash", context=plugin_context)
    
    # 실제 로딩 과정을 단계별로 진행
    try:
        import time
        
        # 모듈 로딩
        splash.set_progress(0.15, "시스템 모듈 로딩...")
        time.sleep(0.2)
        
        # 데이터베이스 초기화
        splash.set_progress(0.30, "데이터베이스 초기화...")
        time.sleep(0.2)
        
        # UI 컴포넌트 구성
        splash.set_progress(0.50, "UI 컴포넌트 구성...")
        time.sleep(0.2)
        
        # 메인 창 생성
        splash.set_progress(0.70, "메인 윈도우 초기화...")
        window = DARTMainWindow(splash, localization_manager)
        
        # GeoJSON 데이터 로드는 백그라운드에서 진행
        splash.set_progress(0.85, "지도 데이터 로드 중...")
        app.processEvents()
        
        # 최종 완료
        splash.finish_loading()
        
    except Exception as e:
        splash.set_progress(1.0, f"오류 발생: {str(e)}")
        time.sleep(1.0)
        print(f"로딩 중 오류: {e}")
        import traceback
        traceback.print_exc()
    
    # 스플레시 화면 종료 및 메인 창 표시
    splash.finish(window)
    window.show()
    
    # Post-main stage 플러그인 실행
    plugin_loader.run_plugins("post-main", context=plugin_context)
    
    sys.exit(app.exec_())
