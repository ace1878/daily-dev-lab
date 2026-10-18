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
python folder_report.py . --csv report.csv
python folder_report.py . --min-size 1048576
python folder_report.py . --max-size 1048576
python folder_report.py . --sort-by size
python folder_report.py . --include-hidden
python folder_report.py . --exclude "*.log" --exclude "node_modules"
```

`--sort-by`로 확장자별 통계의 정렬 기준을 선택할 수 있습니다.

- `extension`: 확장자 이름 오름차순(기본값)
- `size`: 확장자별 총용량 내림차순
- `count`: 확장자별 파일 개수 내림차순

용량이나 파일 개수가 같으면 확장자 이름 오름차순으로 정렬합니다. 선택한 순서는
텍스트, JSON, CSV 출력에 똑같이 적용됩니다.

```powershell
python folder_report.py . --sort-by size
python folder_report.py . --sort-by count
python folder_report.py . --min-size 1048576 --exclude "*.log" --sort-by size
```

`--min-size BYTES`를 사용하면 지정한 바이트 이상의 파일만 통계에 포함합니다.
경계값과 같은 크기의 파일도 포함되며, 파일 수·전체 용량·확장자 통계·큰 파일
목록에 같은 기준이 적용됩니다.

```powershell
# 1 MiB(1,048,576바이트) 이상의 파일만 분석
python folder_report.py . --min-size 1048576

# 로그 파일을 제외하면서 1 MiB 이상의 결과를 CSV로 저장
python folder_report.py . --min-size 1048576 --exclude "*.log" --csv report.csv
```

`--max-size BYTES`를 사용하면 지정한 바이트 이하의 파일만 통계에 포함합니다.
`--min-size`와 함께 지정하면 두 경계값을 포함하는 크기 범위만 분석합니다.

```powershell
# 1 MiB 이하의 파일만 분석
python folder_report.py . --max-size 1048576

# 1 KiB 이상, 1 MiB 이하의 파일만 분석
python folder_report.py . --min-size 1024 --max-size 1048576

# 범위 필터와 제외·정렬·CSV 옵션 함께 사용
python folder_report.py . --min-size 1024 --max-size 1048576 --exclude "*.log" --sort-by size --csv report.csv
```

`--csv OUTPUT.csv`를 사용하면 확장자별 통계를 CSV 파일로 저장합니다. CSV 열은
`extension`, `files`, `size_bytes` 순서입니다. `--json`과 `--csv`는 동시에 사용할
수 없습니다.

```powershell
# 확장자별 파일 수와 바이트 용량을 report.csv로 저장
python folder_report.py . --csv report.csv
```

기본값에서는 숨김 파일·폴더와 `__pycache__`를 제외합니다.

`--exclude`는 여러 번 지정할 수 있습니다. 파일은 `*.log` 같은 패턴으로,
디렉터리는 `node_modules` 같은 이름으로 제외합니다. 제외된 항목은 파일 수,
전체 용량, 확장자별 통계, 큰 파일 목록에 포함되지 않습니다.

```powershell
# 로그 파일과 모든 node_modules 디렉터리를 빼고 현재 폴더 분석
python folder_report.py . --exclude "*.log" --exclude "node_modules"
```

### 테스트

```powershell
python -m unittest discover -s tests -v
```

### CI

GitHub Actions가 다음 상황에서 Python 3.12와 Ubuntu 환경으로 전체 테스트를
자동 실행합니다.

- `main` 브랜치에 push할 때
- pull request를 만들거나 새로운 변경을 올릴 때

실행 결과는 GitHub 저장소의 **Actions** 탭에서 `Tests` 워크플로를 선택해 확인할
수 있습니다. 각 실행의 `test` 작업에서 테스트 로그와 성공·실패 원인을 볼 수
있습니다. 테스트 명령이 실패하면 워크플로도 실패합니다.

