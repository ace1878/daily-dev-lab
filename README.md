# daily-dev-lab

짧은 시간 안에 만들고 직접 검수할 수 있는 실용적인 Python 도구를 쌓는 저장소입니다.

## Day 1: Folder Report

폴더를 재귀적으로 살펴보고 다음 정보를 보여 주는 명령줄 도구입니다.

- 전체 파일 수와 용량
- 확장자별 파일 수와 용량
- 용량이 큰 파일 목록

파일을 읽거나 변경하지 않고 이름과 크기만 확인합니다. 심볼릭 링크는 따라가지 않습니다.

### 설치

Python 3.10 이상이 필요합니다. 저장소 폴더에서 가상환경을 만들고 editable 모드로
설치하면 `folder-report` 명령을 사용할 수 있습니다. editable 설치에서는 소스 수정이
바로 반영됩니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\folder-report.exe --help
.\.venv\Scripts\folder-report.exe .
```

가상환경을 활성화하면 짧은 명령으로 실행할 수 있습니다.

```powershell
.\.venv\Scripts\Activate.ps1
folder-report .
folder-report . --extension py --max-depth 2 --json
folder-report . --markdown-output report.md
```

기존 `python folder_report.py ...` 실행 방식과 모든 옵션도 그대로 사용할 수 있습니다.
설치는 `pyproject.toml`의 setuptools 설정을 사용하며 `build/`, `dist/`, `*.egg-info/`는
Git 추적에서 제외합니다.

`--version`은 폴더를 분석하지 않고 패키지 버전을 출력한 뒤 종료 코드 `0`으로 끝납니다.

```powershell
folder-report --version
python folder_report.py --version
# 출력 예: folder-report 0.1.0
```

설치된 도구는 `pyproject.toml`에서 생성된 패키지 메타데이터를 사용합니다.
설치 없이 Python 파일을 직접 실행할 때는 같은 폴더의 `pyproject.toml`에서 버전을
읽으므로 코드에 버전 문자열을 중복해서 관리하지 않습니다.

### wheel 빌드 및 독립 설치 검증

저장소 폴더에서 배포용 wheel을 만들고 임시 가상환경에서 검증할 수 있습니다.
개발용 editable 설치와 별개로 동작합니다.

```powershell
python -m pip wheel . --no-deps --wheel-dir dist
python scripts/verify_wheel.py
```

검증 스크립트는 `dist/daily_dev_lab-*.whl` 파일이 하나일 때 자동으로 선택합니다.
여러 버전이 있으면 `python scripts/verify_wheel.py dist/파일명.whl`처럼 지정합니다.
저장소 밖 임시 가상환경에 해당 wheel만 설치하고, 설치된 모듈의 실제 위치,
`folder-report --help`, 임시 폴더 분석 결과(파일 2개, 8바이트)를 검사합니다.
Windows의 `Scripts/*.exe`와 Ubuntu의 `bin/*` 경로 차이를 자동 처리합니다.
검증 후 임시 환경은 삭제되며 빌드한 wheel은 `dist/`에 남습니다.
검증 스크립트는 표준 라이브러리만 사용하며, wheel 설치 시 외부 인덱스나 의존성을
다운로드하지 않습니다. 빌드 단계에는 기존 setuptools 빌드 환경이 사용됩니다.

### 사용법

`--summary-only`는 전체 파일 수·용량·확장자별 통계를 출력하고 큰 파일 목록 구역을
생략합니다. 텍스트와 Markdown은 해당 구역 전체를 생략하고 JSON은 기존 필드를
유지하면서 `largest_files`를 빈 배열로 저장합니다. CSV는 기존 확장자별 통계를
그대로 저장합니다. 빈 폴더에서도 통계와 `(no files)` 표시를 확인할 수 있습니다.

```powershell
folder-report . --summary-only
python folder_report.py . --summary-only --show-time
python folder_report.py . --summary-only --json
python folder_report.py . --summary-only --markdown-output summary.md
python folder_report.py . --summary-only --quiet --json-output summary.json
```

`--quiet`과 함께 사용하면 일반 터미널 출력을 생략하고 지정한 보고서 파일을
저장합니다. `--show-time`은 기존처럼 stderr에 표시되며 `--quiet`이면 생략합니다.
`--show-skipped`로 요청한 접근 오류 경로 목록과 기존 종료 코드 규칙도 적용됩니다.

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
python folder_report.py . --strict
```

`--quiet`은 실제 분석을 수행하면서 터미널의 일반 출력만 생략합니다. 텍스트·JSON
화면 보고서, 파일 저장 완료 안내, `--show-time` 시간 메시지를 표시하지 않습니다.
명시적으로 지정한 CSV·JSON·Markdown 파일은 같은 형식과 내용으로 생성합니다.
오류 메시지는 stderr에 표시하며, 정상 `0`, 입력·저장 오류 `2`, strict 접근 오류 `3`,
용량 제한 초과 `4`의 종료 코드는 유지합니다. `--quiet`을 생략하면 기존 동작을 유지합니다.

```powershell
# 화면 보고서 없이 분석
folder-report . --quiet

# 필터 적용 후 합계가 10MiB를 초과하면 오류 메시지와 종료 코드 4
python folder_report.py . --quiet --extension py --fail-over-size 10MiB
$LASTEXITCODE

# 안내·시간 메시지 없이 JSON 파일 생성
python folder_report.py . --quiet --show-time --json-output report.json
```

`--quiet --json`은 JSON 화면 출력도 생략합니다. 파일이 필요하면 `--json-output PATH`를
사용하세요. 용량 제한을 초과해도 지정한 보고서 파일은 저장되지만, `--strict` 접근 오류가
있으면 기존처럼 파일을 저장하지 않고 종료 코드 `3`을 반환합니다. `--help`와 `--version`의
명시적인 정보 요청은 `--quiet`으로 숨기지 않습니다.

`--show-time`을 사용하면 보고서 출력·저장 후 분석 소요 시간을 초 단위(소수점 셋째
자리)로 표시합니다. `time.perf_counter()`로 폴더 분석 구간만 측정하며, 출력·저장에
걸린 시간은 포함하지 않습니다. 시간 메시지는 stderr로 출력하므로 JSON 화면 출력과
CSV·JSON·Markdown 파일 내용에 섞이지 않습니다. 옵션 생략 시 기존 출력이 유지됩니다.

```powershell
folder-report . --show-time
python folder_report.py . --max-depth 1 --show-time
python folder_report.py . --json --show-time
python folder_report.py . --json-output report.json --show-time
```

시간 메시지 예시: `Analysis time: 0.012 seconds`

분석 실패, `--strict` 접근 오류 또는 보고서 저장 실패 시에는 시간 메시지를 출력하지
않습니다. `--fail-over-size`로 용량을 초과한 경우는 보고서와 시간을 출력하고 기존처럼
종료 코드 `4`를 반환합니다.

기본 터미널 출력은 크기를 B·KiB·MiB·GiB·TiB로 자동 표시하며, 내용 길이에 맞춰
열을 정렬합니다. 큰 파일은 크기 내림차순이며 같은 크기는 경로 오름차순입니다.

```text
Folder: sample
Files: 3
Total size: 1.5 MiB

By extension:
  Extension  Files     Size
  ---------  -----  -------
  .bin           1  1.5 MiB
  .txt           2    515 B

Largest files:
     Size  Path
  -------  -----------
  1.5 MiB  archive.bin
    512 B  notes.txt
      3 B  tiny.txt
```

빈 폴더는 기존처럼 `(no files)`로 표시합니다. 이 표 정렬은 터미널 텍스트 출력에만
적용되며 JSON·CSV·Markdown 형식과 크기 필터 옵션은 기존과 동일합니다.

`--strict`를 사용하면 분석 중 접근 오류로 건너뛴 경로가 하나라도 있을 때
오류 메시지를 stderr에 출력하고 종료 코드 `3`을 반환합니다. 이 경우 화면 보고서와
CSV·JSON·Markdown 파일을 출력하지 않으며, `--force`를 함께 지정해도 기존 출력
파일 내용을 보존합니다. 접근 오류가 없으면 평소처럼 보고서를 출력하고 종료 코드
`0`을 반환합니다. 옵션을 생략하면 접근 가능한 파일의 분석 결과를 기존처럼 출력합니다.
필터로 제외되거나 깊이 제한 밖에 있는 경로는 접근 오류로 취급하지 않습니다.

```powershell
# 접근 오류가 있으면 실패 처리
python folder_report.py . --strict
$LASTEXITCODE

# 분석에 접근 오류가 없을 때만 JSON 저장
python folder_report.py . --strict --json-output report.json
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

`--file-sort name|size`로 큰 파일 목록의 표시 순서를 선택할 수 있습니다.
`--top N`으로 크기가 큰 파일 N개를 먼저 선정하고 해당 파일들을 정렬합니다.
`name`은 파일 이름(디렉터리 부분 제외)의 오름차순이며, 같은 이름은 상대 경로
오름차순으로 정렬합니다. 이름 비교는 대소문자를 구분합니다.
기본값 `size`는 크기 내림차순이며 같은 크기는 상대 경로 오름차순입니다.
텍스트·JSON·Markdown의 큰 파일 목록에 적용되며 CSV는 확장자별 통계를 저장합니다.

```powershell
folder-report . --top 10 --file-sort name
python folder_report.py . --file-sort size --min-size 1KiB --json
python folder_report.py . --file-sort name --exclude "*.log" --exclude-file excluded-dirs.txt
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

`--min-list-size SIZE`는 기준값 이상인 파일만 큰 파일 목록에 표시합니다.
전체 파일 수, 전체 용량, 확장자별 통계와 `--fail-over-size` 판정에는 영향을 주지
않습니다. `--exclude`와 `--exclude-file`을 함께 사용할 수 있습니다.
정수 바이트 또는 `B`, `KB`, `MB`, `GB`, `KiB`, `MiB`, `GiB`를 지정할 수
있습니다. `1KB`는 1,000바이트, `1KiB`는 1,024바이트이며 대소문자를 구분하지
않습니다. 목록 필터는 텍스트·JSON·Markdown의 큰 파일 목록에 적용됩니다.
CSV에는 확장자별 통계만 있으므로 결과가 달라지지 않습니다.

```powershell
folder-report . --min-list-size 1MB
python folder_report.py . --min-list-size 1KiB --exclude "*.log" --json
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

`--exclude-dir NAME`은 **디렉터리만** 이름의 정확한 일치로 제외합니다. 대소문자를
구분하며 여러 번 지정할 수 있습니다. 모든 깊이에서 같은 이름의 디렉터리 내부를
탐색하지 않고, 그 안의 파일은 모든 통계에서 제외합니다. 같은 이름의 파일은 유지합니다.
경로나 와일드카드 패턴은 해석하지 않으며, 일치하는 이름이 없으면 결과가 바뀌지 않습니다.
기존 `--exclude`와 `--exclude-from`의 패턴 규칙은 그대로 유지되며 함께 사용할 수 있습니다.

```powershell
folder-report . --exclude-dir node_modules
folder-report . --exclude-dir node_modules --exclude-dir vendor
python folder_report.py . --exclude-dir cache --exclude "*.log" --json

# 숨김 폴더는 기본 제외되므로 포함 모드에서 디렉터리 제외 규칙 검수
folder-report . --include-hidden --exclude-dir .git --exclude-dir .venv
```

옵션을 생략하면 기존 탐색 결과가 유지됩니다. 분석 대상으로 직접 지정한 기준 폴더
자체는 제외하지 않고, 그 아래에서 탐색하는 디렉터리에 규칙을 적용합니다.

`--exclude-file PATH`는 UTF-8 파일에서 **디렉터리 이름**을 한 줄씩 읽습니다.
빈 줄과 앞뒤 공백, `#`으로 시작하는 주석 줄은 무시하며 UTF-8 BOM도 지원합니다.
중복 이름은 하나로 처리하고, `--exclude-dir`과 같은 대소문자 구분·정확한 이름 일치
규칙으로 모든 깊이의 디렉터리를 제외합니다. 같은 이름의 파일은 제외하지 않으며,
와일드카드와 경로 패턴은 해석하지 않습니다. 줄 중간의 `#`은 이름의 일부입니다.

예를 들어 `excluded-dirs.txt`를 다음과 같이 작성합니다.

```text
# 디렉터리 이름 목록
node_modules
cache
cache
```

```powershell
folder-report . --exclude-file excluded-dirs.txt
folder-report . --exclude-file excluded-dirs.txt --exclude "*.log" --exclude-dir vendor
python folder_report.py . --exclude-file excluded-dirs.txt --json
```

설정 파일 경로는 실행 중인 폴더를 기준으로 합니다. 목록이 비어 있으면 기존 결과를
유지하며 설정 파일 자체는 자동 제외하지 않습니다. 파일이 없거나 읽을 수 없거나
UTF-8이 아니면 stderr에 경로와 오류 원인을 출력하고 종료 코드 `2`를 반환합니다.
이 경우 분석·보고서 저장을 시작하지 않으며 기존 보고서 파일도 보존합니다.

`--exclude-from PATH`로 UTF-8 텍스트 파일의 제외 패턴을 읽을 수 있습니다.
한 줄에 패턴 하나를 작성하며 앞뒤 공백, 빈 줄, `#`으로 시작하는 주석은 무시합니다.
UTF-8 BOM이 있는 파일도 지원합니다. 줄 중간의 `#`은 패턴의 일부로 취급합니다.
옵션을 여러 번 지정하거나 `--exclude`와 함께 사용하면 모든 패턴을 합쳐 적용합니다.
패턴 매칭 규칙은 `--exclude`와 동일합니다. 상대 설정 파일 경로는 실행 중인
현재 폴더를 기준으로 하며, 설정 파일 자체가 자동으로 분석에서 제외되지는 않습니다.
파일이 없거나 읽을 수 없거나 UTF-8이 아니면 stderr에 오류를 출력하고 종료 코드 `2`를 반환합니다.

예를 들어 `exclude-patterns.txt`를 다음과 같이 작성합니다.

```text
# 로그 및 의존성 폴더 제외
*.log
node_modules

*.tmp
```

```powershell
folder-report . --exclude-from exclude-patterns.txt
folder-report . --exclude-from exclude-patterns.txt --exclude-from local-patterns.txt --exclude "*.bak"
python folder_report.py . --exclude-from exclude-patterns.txt --json
```

`--fail-over-size SIZE`를 사용하면 필터 적용 후 전체 분석 용량이 제한값을 초과할 때
종료 코드 `4`를 반환합니다. 제한값과 정확히 같으면 정상 처리합니다. 정수 바이트와
`KiB`, `MiB`, `GiB`를 대소문자 구분 없이 사용할 수 있습니다.
초과하더라도 보고서는 정상적으로 출력하거나 저장하며, 실제 용량과 제한 용량을
바이트 단위로 stderr에 알립니다. JSON 화면 출력에는 오류 메시지가 섞이지 않습니다.
`--strict` 접근 오류가 있으면 보고서를 만들지 않고 종료 코드 `3`을 우선 반환합니다.
파일 저장 실패 등 기존 오류는 종료 코드 `2`를 유지합니다.

```powershell
folder-report . --fail-over-size 10MiB
$LASTEXITCODE

# 필터 적용 후 합계 검사 및 JSON 출력
folder-report . --extension py --exclude "*.log" --fail-over-size 1MiB --json

# 용량을 초과해도 보고서 파일은 저장됨(기존 파일은 --force 필요)
folder-report . --fail-over-size 1MiB --markdown-output report.md
```

종료 코드:

- `0`: 정상 처리(용량 제한 미지정 또는 제한값 이하)
- `2`: 잘못된 입력, 설정 파일 읽기 실패, 보고서 저장 실패 등
- `3`: `--strict` 사용 중 접근 오류 발생(보고서 생성 안 함)
- `4`: 보고서 출력·저장 후 용량 제한 초과 확인

### 테스트

```powershell
python -m unittest discover -s tests -v
```

### CI

GitHub Actions가 다음 상황에서 Python 3.12를 사용해 Ubuntu와 Windows 환경에서
각각 전체 테스트를 자동 실행합니다.

- `main` 브랜치에 push할 때
- pull request를 만들거나 새로운 변경을 올릴 때

실행 결과는 GitHub 저장소의 **Actions** 탭에서 `Tests` 워크플로를 선택해 확인할
수 있습니다. OS 매트릭스의 `test (ubuntu-latest)`와 `test (windows-latest)` 작업이
각각 다음 검증을 수행합니다.

1. `python -m pip install -e .`로 editable 설치
2. `folder-report --help`로 설치된 CLI 진입점 확인
3. `python -m unittest discover -s tests -v`로 전체 테스트 실행
4. `python -m pip wheel . --no-deps --wheel-dir dist`로 wheel 빌드
5. `python scripts/verify_wheel.py`로 저장소 밖 임시 가상환경 설치·실행 검증

각 작업의 단계별 로그에서 성공·실패 원인을 확인할 수 있습니다. 설치, CLI 실행,
테스트 중 어느 단계라도 실패하면 해당 작업과 워크플로가 실패합니다. 한 OS가
실패하더라도 다른 OS 작업은 취소하지 않아 두 환경의 결과를 확인할 수 있습니다.

