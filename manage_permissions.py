#!/usr/bin/env python
"""권한 저장소 관리 유틸리티
사용자가 저장된 권한을 조회, 수정, 초기화할 수 있습니다.
"""

import json
import sys
from pathlib import Path


def get_permission_file():
    """권한 저장소 파일 경로 반환"""
    return Path.home() / ".tdcs" / "permissions.json"


def show_saved_permissions():
    """저장된 권한 표시"""
    perm_file = get_permission_file()
    
    if not perm_file.exists():
        print("저장된 권한이 없습니다.")
        return
    
    with open(perm_file, 'r', encoding='utf-8') as f:
        permissions = json.load(f)
    
    print("\n" + "=" * 70)
    print("저장된 권한 현황")
    print("=" * 70)
    
    for plugin_name, perms in permissions.items():
        print(f"\n[{plugin_name}]")
        for perm_name, granted in perms.items():
            status = "✓ 승인" if granted else "✗ 거부"
            print(f"  - {perm_name}: {status}")
    
    print(f"\n파일 위치: {perm_file}")
    print("=" * 70)


def reset_permissions():
    """저장된 모든 권한 초기화"""
    perm_file = get_permission_file()
    
    if not perm_file.exists():
        print("초기화할 권한이 없습니다.")
        return
    
    # 확인
    while True:
        choice = input("\n저장된 모든 권한을 삭제하시겠습니까? (y/n): ").lower().strip()
        if choice == 'y':
            perm_file.unlink()
            print("✓ 모든 권한이 초기화되었습니다.")
            print("  다음 실행 시 권한을 다시 묻게 됩니다.")
            break
        elif choice == 'n':
            print("초기화가 취소되었습니다.")
            break
        else:
            print("y 또는 n을 입력하세요.")


def reset_plugin_permission(plugin_name, permission_name=None):
    """특정 플러그인의 권한 초기화"""
    perm_file = get_permission_file()
    
    if not perm_file.exists():
        print("저장된 권한이 없습니다.")
        return
    
    with open(perm_file, 'r', encoding='utf-8') as f:
        permissions = json.load(f)
    
    if plugin_name not in permissions:
        print(f"'{plugin_name}' 플러그인의 권한이 없습니다.")
        return
    
    if permission_name is None:
        # 플러그인의 모든 권한 초기화
        del permissions[plugin_name]
        print(f"✓ '{plugin_name}' 플러그인의 모든 권한이 초기화되었습니다.")
    else:
        # 특정 권한만 초기화
        if permission_name in permissions[plugin_name]:
            del permissions[plugin_name][permission_name]
            if not permissions[plugin_name]:  # 빈 딕셔너리면 제거
                del permissions[plugin_name]
            print(f"✓ '{plugin_name}' 플러그인의 '{permission_name}' 권한이 초기화되었습니다.")
        else:
            print(f"'{plugin_name}' 플러그인에 '{permission_name}' 권한이 없습니다.")
            return
    
    # 파일에 저장
    with open(perm_file, 'w', encoding='utf-8') as f:
        json.dump(permissions, f, indent=2, ensure_ascii=False)


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="TDCS 권한 저장소 관리 유틸리티",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  # 저장된 모든 권한 표시
  python manage_permissions.py show
  
  # 모든 권한 초기화
  python manage_permissions.py reset
  
  # 특정 플러그인의 모든 권한 초기화
  python manage_permissions.py reset-plugin sample_permission_request
  
  # 특정 플러그인의 특정 권한만 초기화
  python manage_permissions.py reset-permission sample_permission_request read_main_locales
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='명령어')
    
    # show 명령어
    subparsers.add_parser('show', help='저장된 권한 표시')
    
    # reset 명령어
    subparsers.add_parser('reset', help='모든 권한 초기화')
    
    # reset-plugin 명령어
    reset_plugin_parser = subparsers.add_parser('reset-plugin', help='플러그인 권한 초기화')
    reset_plugin_parser.add_argument('plugin', help='플러그인 이름')
    
    # reset-permission 명령어
    reset_perm_parser = subparsers.add_parser('reset-permission', help='특정 권한 초기화')
    reset_perm_parser.add_argument('plugin', help='플러그인 이름')
    reset_perm_parser.add_argument('permission', help='권한 이름')
    
    args = parser.parse_args()
    
    if args.command == 'show':
        show_saved_permissions()
    elif args.command == 'reset':
        reset_permissions()
    elif args.command == 'reset-plugin':
        reset_plugin_permission(args.plugin)
    elif args.command == 'reset-permission':
        reset_plugin_permission(args.plugin, args.permission)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
