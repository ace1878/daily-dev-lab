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
python folder_report.py . --json-output report.json
python folder_report.py . --markdown-output report.md
python folder_report.py . --csv report.csv
python folder_report.py . --min-size 1MiB
python folder_report.py . --max-size 2GiB
python folder_report.py . --sort-by size
python folder_report.py . --include-hidden
python folder_report.py . --exclude "*.log" --exclude "node_modules"
python folder_report.py . --extension txt --extension .csv
python folder_report.py . --max-depth 1
python folder_report.py . --show-skipped
```

분석 중 접근 오류가 발생한 경로는 기본적으로 개수만 표시합니다.
`--show-skipped`를 사용하면 건너뛴 경로도 이름 오름차순으로 확인할 수 있습니다.
건너뛴 경로가 없으면 해당 구역은 출력하지 않습니다. JSON의 `skipped` 필드와
CSV 출력 방식은 기존과 동일합니다.

```powershell
# 접근 오류로 건너뛴 경로의 개수와 목록 표시
python folder_report.py . --show-skipped

# 깊이·확장자 필터와 함께 사용
python folder_report.py . --max-depth 2 --extension py --show-skipped
```

`--max-depth DEPTH`를 사용하면 기준 폴더에서 지정한 깊이까지만 탐색합니다.
`0`은 기준 폴더의 파일만, `1`은 바로 아래 하위 폴더의 파일까지 포함합니다.
옵션을 생략하면 기존처럼 모든 하위 폴더를 탐색합니다.

```powershell
# 현재 폴더의 파일만 분석
python folder_report.py . --max-depth 0

# 바로 아래 하위 폴더까지 분석
python folder_report.py . --max-depth 1

# 깊이 제한과 기존 필터를 함께 사용
python folder_report.py . --max-depth 2 --extension py --exclude "__pycache__" --json
```

`--extension EXT`를 사용하면 지정한 확장자의 파일만 분석합니다. 옵션을 여러 번
사용하면 지정한 확장자 중 하나와 일치하는 파일을 모두 포함합니다. 확장자 앞의
점은 생략할 수 있고 대소문자를 구분하지 않습니다.

```powershell
# TXT 파일만 분석(.txt와 동일)
python folder_report.py . --extension txt

# TXT 또는 CSV 파일만 분석
python folder_report.py . --extension .txt --extension CSV

# 확장자·크기·제외·정렬 필터를 함께 사용하고 JSON으로 출력
python folder_report.py . --extension txt --min-size 1024 --max-size 1048576 --exclude "*.log" --sort-by size --json
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

`--min-size SIZE`를 사용하면 지정한 크기 이상의 파일만 통계에 포함합니다.
경계값과 같은 크기의 파일도 포함되며, 파일 수·전체 용량·확장자 통계·큰 파일
목록에 같은 기준이 적용됩니다. 단위 없는 정수는 기존처럼 바이트로 처리하며,
`KiB`, `MiB`, `GiB` 단위를 대소문자 구분 없이 사용할 수 있습니다.
각 단위는 1024배 기준이며 크기 숫자는 0 이상의 정수만 허용합니다. 음수, 소수,
`KB`나 `MB`처럼 지원하지 않는 단위는 오류로 처리됩니다.

```powershell
# 1 MiB(1,048,576바이트) 이상의 파일만 분석
python folder_report.py . --min-size 1048576

# 1 MiB 이상의 파일만 분석
python folder_report.py . --min-size 1MiB

# 로그 파일을 제외하면서 1 MiB 이상의 결과를 CSV로 저장
python folder_report.py . --min-size 1048576 --exclude "*.log" --csv report.csv
```

`--max-size SIZE`를 사용하면 지정한 크기 이하의 파일만 통계에 포함합니다.
`--min-size`와 함께 지정하면 두 경계값을 포함하는 크기 범위만 분석합니다.

```powershell
# 1 MiB 이하의 파일만 분석
python folder_report.py . --max-size 1048576

# 1 KiB 이상, 1 MiB 이하의 파일만 분석(단위 대소문자 무관)
python folder_report.py . --min-size 1KiB --max-size 1mIb

# 범위 필터와 제외·정렬·CSV 옵션 함께 사용
python folder_report.py . --min-size 1024 --max-size 1048576 --exclude "*.log" --sort-by size --csv report.csv
```

`--json-output OUTPUT.json`을 사용하면 `--json`으로 화면에 표시하는 것과 같은
전체 분석 결과를 UTF-8 JSON 파일로 저장합니다. 출력 파일이 분석 폴더 안에
있어도 해당 파일 자체는 통계에서 제외합니다.

```powershell
# 전체 분석 결과를 report.json으로 저장
python folder_report.py . --json-output report.json

# 기존 필터와 함께 JSON 파일로 저장
python folder_report.py . --extension py --max-depth 2 --json-output report.json
```

`--csv OUTPUT.csv`를 사용하면 확장자별 통계를 CSV 파일로 저장합니다. CSV 열은
`extension`, `files`, `size_bytes` 순서입니다. `--json`, `--json-output`, `--csv`,
`--markdown-output`은
서로 동시에 사용할 수 없습니다.

```powershell
# 확장자별 파일 수와 바이트 용량을 report.csv로 저장
python folder_report.py . --csv report.csv
```

`--markdown-output OUTPUT.md`를 사용하면 제목, 기준 폴더, 파일 수, 전체 용량,
건너뛴 경로 수와 함께 확장자별 통계 및 큰 파일 목록을 Markdown 표로 저장합니다.
용량 표의 단위는 바이트이며 기존 정렬 기준과 `--top` 설정을 따릅니다.
빈 결과는 `(no files)`로 표시합니다. 파일은 UTF-8로 저장하며, 출력 파일 자체는
분석 대상에서 제외합니다. 기존 파일을 덮어쓰려면 `--force`를 지정해야 합니다.
경로의 Markdown 특수문자는 문자 참조로 저장하여 표나 링크 문법으로 해석되지
않게 하며, Markdown 미리보기에서는 원래 문자로 표시됩니다.

```powershell
python folder_report.py . --markdown-output report.md
python folder_report.py . --extension py --max-depth 2 --sort-by size --markdown-output report.md
```

CSV, JSON, Markdown 보고서는 기본적으로 새 파일로만 저장합니다. 출력 파일이
이미 존재하면 오류를 표시하고 기존 내용을 보존합니다. 의도적으로 덮어쓸 때는
`--force`를 사용합니다. 새 파일은 배타적 생성 모드로 열어, 저장 직전에 다른
프로세스가 같은 이름의 파일을 생성하더라도 덮어쓰지 않습니다.

```powershell
# 새 보고서 생성(이미 존재하면 오류)
python folder_report.py . --csv report.csv

# 기존 보고서를 덮어쓰기
python folder_report.py . --csv report.csv --force
python folder_report.py . --json-output report.json --force
python folder_report.py . --markdown-output report.md --force
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

