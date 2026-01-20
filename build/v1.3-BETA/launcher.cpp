#include <windows.h>
#include <shellapi.h>
#include <wincrypt.h>
#include <string>
#include <vector>

// 링커 설정 강제 지정 (진입점 오류 방지)
#pragma comment(lib, "crypt32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(linker, "/subsystem:windows")

namespace Expected {
    // 해시 비교를 위해 대문자로 작성됨
    const char* MAIN_EXE_HASH = "30E49E43E09602CA9823A09CF6DA04C90334EDD4864A463C69D19C0A72409613";
    const char* QtWebEngineProcess_EXE_HASH = "43535990DA17776D53A0958B813B16604FD94B5FC7AA34CF2C0630F2624A976C";
}

// SHA256 해시 계산 함수
std::string CalculateSHA256(const std::wstring& filePath) {
    HANDLE hFile = CreateFileW(filePath.c_str(), GENERIC_READ,
        FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (hFile == INVALID_HANDLE_VALUE) return "";

    HCRYPTPROV hProv = 0;
    HCRYPTHASH hHash = 0;
    std::string result = "";

    if (CryptAcquireContextW(&hProv, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT)) {
        if (CryptCreateHash(hProv, CALG_SHA_256, 0, 0, &hHash)) {
            BYTE buffer[8192];
            DWORD bytesRead = 0;
            while (ReadFile(hFile, buffer, 8192, &bytesRead, NULL) && bytesRead > 0) {
                CryptHashData(hHash, buffer, bytesRead, 0);
            }

            BYTE hash[32];
            DWORD hashLen = 32;
            if (CryptGetHashParam(hHash, HP_HASHVAL, hash, &hashLen, 0)) {
                // Expected 해시와 비교하기 위해 대문자 "ABCDEF" 사용
                char hexDigits[] = "0123456789ABCDEF";
                for (DWORD i = 0; i < hashLen; i++) {
                    result += hexDigits[hash[i] >> 4];
                    result += hexDigits[hash[i] & 0xf];
                }
            }
            CryptDestroyHash(hHash);
        }
        CryptReleaseContext(hProv, 0);
    }
    CloseHandle(hFile);
    return result;
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {
    // 1. 중복 실행 방지 (Mutex)
    HANDLE hMutex = CreateMutex(NULL, TRUE, L"DARTLauncherMutex");
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        MessageBox(NULL, L"이미 프로그램이 실행 중입니다.", L"DART 런처", MB_ICONWARNING);
        return 1;
    }

    // 2. 경로 설정
    wchar_t exePath[MAX_PATH];
    GetModuleFileName(NULL, exePath, MAX_PATH);
    std::wstring dirPath = exePath;
    dirPath = dirPath.substr(0, dirPath.find_last_of(L"\\/") + 1);

    std::wstring mainExe = dirPath + L"main.exe";
    std::wstring qtWebEngineProcessExe = dirPath + L"QtWebEngineProcess.exe";

    // 3. main.exe 무결성 검증
    std::string actualHash = CalculateSHA256(mainExe);
    if (actualHash.empty()) {
        MessageBox(NULL, L"main.exe를 찾을 수 없습니다.", L"DART 런처", MB_ICONERROR);
        CloseHandle(hMutex);
        return 2;
    }
    if (actualHash != Expected::MAIN_EXE_HASH) {
        MessageBox(NULL, L"main.exe의 무결성 검증에 실패했습니다.\n설치가 잘못되거나 변조되었을 가능성이 있습니다.", L"보안 경고", MB_ICONERROR);
        CloseHandle(hMutex);
        return 3;
    }

    // 4. QtWebEngineProcess.exe 무결성 검증
    std::string qtActualHash = CalculateSHA256(qtWebEngineProcessExe);
    if (qtActualHash.empty()) {
        MessageBox(NULL, L"QtWebEngineProcess.exe를 찾을 수 없습니다.", L"DART 런처", MB_ICONERROR);
        CloseHandle(hMutex);
        return 5;
    }
    if (qtActualHash != Expected::QtWebEngineProcess_EXE_HASH) {
        MessageBox(NULL, L"QtWebEngineProcess.exe의 무결성 검증에 실패했습니다.", L"보안 경고", MB_ICONERROR);
        CloseHandle(hMutex);
        return 6;
    }

    // 5. 인자값 파싱 및 전달
    int argc;
    LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    std::wstring args = L"";
    for (int i = 1; i < argc; ++i) {
        args += L" \"";
        args += argv[i];
        args += L"\"";
    }
    if (argv) LocalFree(argv);

    // 6. 프로그램 실행
    SHELLEXECUTEINFOW sei = { sizeof(sei) };
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;
    sei.lpFile = mainExe.c_str();
    sei.lpParameters = args.size() > 0 ? args.c_str() : NULL;
    sei.nShow = SW_SHOWNORMAL;

    if (!ShellExecuteExW(&sei)) {
        MessageBox(NULL, L"main.exe 실행에 실패했습니다.", L"에러", MB_ICONERROR);
    }
    else {
        // 성공적으로 실행되었다면 핸들을 닫아줍니다.
        if (sei.hProcess) CloseHandle(sei.hProcess);
    }

    CloseHandle(hMutex);
    return 0;
}
