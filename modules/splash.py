"""
스플레시 화면 모듈 - 심플하고 현대적인 디자인
"""

from PyQt5.QtWidgets import QSplashScreen, QApplication
from PyQt5.QtGui import QPixmap, QColor, QFont, QPainter, QLinearGradient, QPen
from PyQt5.QtCore import Qt, QTimer, QRect, pyqtSignal
import math


class ModernSplashScreen(QSplashScreen):
    """현대적이고 심플한 스플레시 화면"""
    
    # main.py와 동일한 테마 색상
    BACKGROUND_COLOR = QColor(26, 26, 26)   # #1a1a1a
    PRIMARY_COLOR = QColor(0, 209, 178)     # #00d1b2  
    SECONDARY_COLOR = QColor(18, 18, 18)    # #121212
    TEXT_COLOR = QColor(224, 224, 224)      # #e0e0e0
    ACCENT_COLOR = QColor(51, 51, 51)       # #333333
    
    # 로딩 상태 신호
    loading_finished = pyqtSignal()
    
    def __init__(self, width=800, height=500):
        """
        스플레시 화면 초기화
        
        Args:
            width: 너비 (기본값: 800)
            height: 높이 (기본값: 500)
        """
        # 픽셀맵 생성
        pixmap = QPixmap(width, height)
        pixmap.fill(self.BACKGROUND_COLOR)
        
        # QSplashScreen 초기화
        super().__init__(pixmap)
        
        self.width = width
        self.height = height
        self.pixmap = pixmap
        self.progress = 0.0  # 로딩 진행률 (0.0 ~ 1.0)
        self.loading_text = "초기화 중..."
        
        # 로딩 애니메이션 타이머 (화면 업데이트용)
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_loading)
        self.animation_timer.start(50)  # 50ms마다 업데이트
        
        # 애플리케이션 정보
        self.app_info = {
            'version': 'Unknown',
            'version_detail': 'Unknown',
            'build_number': 'Unknown',
            'build_date': 'Unknown',
            'developer': 'STUDIO CSGNS',
            'license': 'GPLv3 License',
            'copyright': '© 2026 STUDIO CSGNS'
        }
        
        # 로고 그리기
        self._draw_splash()
        
        # 창 설정
        self.setWindowFlags(
            Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        
    def set_progress(self, progress, message):
        """외부에서 로딩 진행률과 메시지를 설정"""
        self.progress = max(0.0, min(1.0, progress))
        self.loading_text = message
        self._draw_splash()
        QApplication.processEvents()
    
    def set_app_info(self, app_info: dict):
        """애플리케이션 정보 설정"""
        self.app_info.update(app_info)
        self._draw_splash()
    
    def update_geojson_progress(self, current, total, filename=""):
        """GeoJSON 로딩 진행률 업데이트 (current/total)"""
        progress = 0.95 + (0.05 * current / total) if total > 0 else 0.95
        message = f"GeoJSON 로딩 중... ({current}/{total})"
        if filename:
            message += f"\n{filename}"
        self.set_progress(progress, message)
    
    def finish_loading(self):
        """로딩 완료 처리"""
        self.set_progress(1.0, "로딩 완료!")
        # 완료 후 신호 발송
        QTimer.singleShot(300, self.loading_finished.emit)
    
    def _advance_loading(self):
        """로딩 진행률을 단계별로 증가 (더 이상 사용되지 않음 - 외부에서 set_progress 사용)"""
        pass
    
    def _update_loading(self):
        """로딩바 애니메이션 업데이트"""
        self._draw_splash()
        
    def _draw_splash(self):
        """스플레시 화면 그리기"""
        # 새 픽셀맵 생성
        self.pixmap = QPixmap(self.width, self.height)
        
        painter = QPainter(self.pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        
        # 배경 미묘한 그라디언트
        gradient = QLinearGradient(0, 0, 0, self.height)
        gradient.setColorAt(0, self.BACKGROUND_COLOR)
        gradient.setColorAt(1, self.SECONDARY_COLOR)
        painter.fillRect(0, 0, self.width, self.height, gradient)
        
        center_x = self.width / 2
        center_y = self.height / 2
        
        # 메인 타이틀
        painter.setPen(self.PRIMARY_COLOR)
        main_font = QFont("Segoe UI", 54, QFont.Light)
        painter.setFont(main_font)
        
        title_rect = QRect(0, int(center_y - 50), self.width, 80)
        painter.drawText(title_rect, Qt.AlignCenter, "DART")
        
        # 서브타이틀
        painter.setPen(self.TEXT_COLOR)
        subtitle_font = QFont("Segoe UI", 14, QFont.Normal)
        painter.setFont(subtitle_font)
        
        subtitle_rect = QRect(0, int(center_y + 20), self.width, 40)
        painter.drawText(subtitle_rect, Qt.AlignCenter, "Drone Analytics & Routing Tool")
        
        # 로딩 텍스트 (부제와 로딩바 사이)
        painter.setPen(self.TEXT_COLOR)
        loading_font = QFont("Segoe UI", 11, QFont.Normal)
        painter.setFont(loading_font)
        
        text_lines = self.loading_text.split('\n')
        line_height = 20
        total_lines_height = len(text_lines) * line_height
        # 부제 아래에서 충분한 여유 후 시작
        loading_text_start_y = int(center_y + 70)
        
        for i, line in enumerate(text_lines):
            line_y = loading_text_start_y + i * line_height
            loading_rect = QRect(0, line_y, self.width, 20)
            painter.drawText(loading_rect, Qt.AlignCenter, line)
        
        # 애니메이션 로딩 바
        bar_y = self.height - 140
        bar_width = self.width // 2
        bar_x = center_x - bar_width // 2
        bar_height = 6
        
        # 배경 바
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.ACCENT_COLOR)
        painter.drawRoundedRect(int(bar_x), int(bar_y), bar_width, bar_height, 3, 3)
        
        # 진행 바 (애니메이션)
        active_width = int(bar_width * self.progress)
        if active_width > 0:
            progress_gradient = QLinearGradient(bar_x, bar_y, bar_x + active_width, bar_y)
            progress_gradient.setColorAt(0, self.PRIMARY_COLOR)
            progress_gradient.setColorAt(1, QColor(0, 255, 200))
            
            painter.setBrush(progress_gradient)
            painter.drawRoundedRect(int(bar_x), int(bar_y), active_width, bar_height, 3, 3)
        
        # 진행률 퍼센트
        painter.setPen(QColor(128, 128, 128))
        percent_font = QFont("Segoe UI", 10, QFont.Normal)
        painter.setFont(percent_font)
        
        percent_text = f"{int(self.progress * 100)}%"
        percent_rect = QRect(0, int(bar_y + 15), self.width, 20)
        painter.drawText(percent_rect, Qt.AlignCenter, percent_text)
        
        # 애플리케이션 정보 표시 (하단)
        info_y = self.height - 90
        info_font = QFont("Segoe UI", 8, QFont.Normal)
        painter.setFont(info_font)
        painter.setPen(QColor(102, 102, 102))  # #666666
        
        # 버전 정보 줄
        version_text = f"v{self.app_info['version']}"
        if self.app_info['version_detail']:
            version_text += f" ({self.app_info['version_detail']})"
        version_text += f" | Build {self.app_info['build_number']} | {self.app_info['build_date']}"
        
        version_rect = QRect(20, int(info_y), self.width - 40, 14)
        painter.drawText(version_rect, Qt.AlignLeft, version_text)
        
        # 개발자 정보 줄
        dev_text = self.app_info['developer']
        dev_rect = QRect(20, int(info_y + 15), self.width - 40, 14)
        painter.drawText(dev_rect, Qt.AlignLeft, dev_text)
        
        # 라이선스 및 저작권 줄
        license_text = f"{self.app_info['license']} | {self.app_info['copyright']}"
        license_rect = QRect(20, int(info_y + 30), self.width - 40, 14)
        painter.drawText(license_rect, Qt.AlignLeft, license_text)
        
        painter.end()
        self.setPixmap(self.pixmap)
    
    def closeEvent(self, event):
        """스플레시 화면 종료 시 타이머 정리"""
        if hasattr(self, 'animation_timer'):
            self.animation_timer.stop()
        if hasattr(self, 'loading_timer'):
            self.loading_timer.stop()
        super().closeEvent(event)


def show_splash_screen():
    """
    스플레시 화면 표시
    
    Returns:
        ModernSplashScreen: 스플레시 화면 객체
    """
    splash = ModernSplashScreen(800, 500)
    splash.show()
    QApplication.processEvents()
    return splash
