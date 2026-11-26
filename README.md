# daily-dev-lab

짧은 개발 작업으로 실용적인 도구를 만들고, 직접 검수와 자동화 테스트를 거쳐
취업 포트폴리오로 발전시켜 나가는 저장소입니다.

## 프로젝트 목록

| 프로젝트 | 상태 | 내용 |
| --- | --- | --- |
| Project 01 · folder-report | Released · v1.0.0 | 폴더의 파일 수·용량·확장자별 통계를 분석하는 Python CLI |
| Project 02 · JSON Inspector | v1.0.0 출시 준비 중 | JSON 유효성 검사·구조 요약·경로 조회·자료형 통계 Python CLI |

## Project 01 · folder-report v1.0.0

폴더를 재귀적으로 분석해 전체 파일 수와 용량, 확장자별 통계, 큰 파일 목록을
보여 줍니다. 크기·확장자·깊이 필터와 제외 규칙을 적용할 수 있으며
텍스트·JSON·CSV·Markdown 보고서를 지원합니다.

[정식 GitHub Release와 wheel 다운로드](https://github.com/ace1878/daily-dev-lab/releases/tag/v1.0.0) ·
[상세 사용 설명](https://github.com/ace1878/daily-dev-lab/blob/main/docs/folder-report.md)

### 설치와 빠른 시작

Python 요구 버전은 3.10 이상입니다. 아래 PowerShell 명령은 저장소 최상위 폴더에서
실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\folder-report.exe --version
.\.venv\Scripts\folder-report.exe --help
.\.venv\Scripts\folder-report.exe . --summary-only
.\.venv\Scripts\folder-report.exe . --extension py --max-depth 1 --json
```

`--version` 출력은 `folder-report 1.0.0`입니다. 가상환경을 활성화한 뒤에는
`folder-report` 명령을 바로 사용할 수 있습니다. Python 파일 직접 실행도 지원합니다.

```powershell
python folder_report.py . --summary-only
```

전체 CLI 옵션, 필터 규칙, 출력 파일 저장, 오류·종료 코드와 wheel 검증 절차는
[folder-report 상세 문서](https://github.com/ace1878/daily-dev-lab/blob/main/docs/folder-report.md)에서 확인할 수 있습니다.

### 테스트와 CI

저장소 최상위 폴더에서 전체 테스트를 실행합니다.

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions는 `main` push와 pull request에서 Ubuntu·Windows, Python 3.12로
테스트·설치·wheel 검증을 실행합니다.
[실행 결과](https://github.com/ace1878/daily-dev-lab/actions)와
[상세 CI 설명](https://github.com/ace1878/daily-dev-lab/blob/main/docs/folder-report.md#ci)을 확인할 수 있습니다.

## Project 02 · JSON Inspector

UTF-8 JSON 파일 하나를 검사하고 구조 요약, 경로별 값 조회, 자료형별 통계를
제공합니다. 기계 판독용 JSON 출력도 지원합니다.

```powershell
python -m pip install ./json-inspector
json-inspector --help
```

[설치·사용·테스트 안내](https://github.com/ace1878/daily-dev-lab/blob/main/json-inspector/README.md)
