# daily-dev-lab

짧은 시간 안에 만들고 직접 검수할 수 있는 실용적인 Python 도구를 쌓는 저장소입니다.

## Day 1: Folder Report

폴더를 재귀적으로 살펴보고 다음 정보를 보여 주는 명령줄 도구입니다.

- 전체 파일 수와 용량
- 확장자별 파일 수와 용량
- 용량이 큰 파일 목록

파일을 읽거나 변경하지 않고 이름과 크기만 확인합니다. 심볼릭 링크는 따라가지 않습니다.

### 사용법

```powershell
python folder_report.py C:\path\to\folder
python folder_report.py . --top 10
python folder_report.py . --json
python folder_report.py . --include-hidden
```

기본값에서는 숨김 파일·폴더와 `__pycache__`를 제외합니다.

### 테스트

```powershell
python -m unittest discover -s tests -v
```

