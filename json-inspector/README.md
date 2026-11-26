# JSON Inspector

UTF-8 JSON 파일 하나를 검사하는 Python CLI입니다. 설정 파일이나 API 응답을
확인할 때 JSON 문법을 검사하고, 구조·자료형 통계를 살펴보거나 필요한 값만
조회할 수 있습니다. 결과를 다른 도구에 전달할 수 있도록 JSON 출력도 제공합니다.

## 설치와 시작

패키지가 요구하는 Python 버전은 3.12 이상이며 런타임 외부 의존성은 없습니다.
저장소 최상위 폴더에서 가상환경을 활성화한 뒤 설치합니다.

```powershell
python -m pip install ./json-inspector
json-inspector --help
json-inspector --version
```

CLI와 패키지 메타데이터 버전은 `1.0.0`입니다. `--version`은 파일 인수 없이
`json-inspector 1.0.0`을 출력합니다. 설치하지 않고 소스를 직접 실행할 수도 있습니다.

```powershell
python json-inspector/json_inspector.py --version
python json-inspector/json_inspector.py sample.json
```

## CLI 옵션

| 옵션 | 설명 |
| --- | --- |
| 옵션 없음 | JSON 유효성 검사 |
| `--summary` | 루트 자료형, 키 또는 항목 수, 컨테이너 최대 깊이 |
| `--stats` | 문서 전체의 JSON 자료형별 값 개수 |
| `--path PATH` | 지정된 경로의 값을 JSON으로 출력 |
| `--json` | 기본 검사·요약·통계 결과를 기계 판독용 JSON으로 출력 |
| `--help` | 사용법 출력 |
| `--version` | 버전 출력 |

`--summary`, `--stats`, `--path` 중 하나를 선택할 수 있습니다. `--json`은 각
모드와 함께 쓸 수 있으며 `--path`의 출력 형식은 그대로입니다. 통계는 루트와
중첩된 값을 세고 객체의 키 이름은 제외합니다. 객체·배열의 최상위 깊이는 1이고
최상위 값이 문자열·수·불리언·null이면 깊이는 0입니다.

## 사용 예시

다음 내용을 UTF-8 `sample.json`으로 저장합니다.

```json
{"user":{"name":"Alice"},"age":21,"skills":["Python","SQL"],"active":true}
```

```powershell
json-inspector sample.json
json-inspector sample.json --summary
json-inspector sample.json --stats
json-inspector sample.json --path "user.name"
json-inspector sample.json --summary --json
```

기본 검사는 `Valid JSON: sample.json`, 경로 조회는 `"Alice"`를 출력합니다.
통계의 전체 값 개수는 `8`입니다. `--summary --json`의 출력은 다음과 같습니다.

```json
{
  "valid": true,
  "root_type": "object",
  "root_keys": 4,
  "max_depth": 2
}
```

## 경로 문법

점으로 객체 키를 연결하고 대괄호에는 0부터 시작하는 배열 인덱스를 넣습니다.
루트가 배열이면 인덱스로 시작할 수 있습니다.

```text
user.name
skills[0]
users[0].name
[0].name
matrix[0][1]
```

## 종료 코드

| 코드 | 의미 |
| --- | --- |
| `0` | 정상 처리 |
| `1` | 유효하지 않은 JSON 입력 |
| `2` | 파일·인코딩·CLI·경로 조회 등 처리 오류 |

오류는 stderr에 출력합니다. JSON 구문 오류에는 파서가 제공하는 줄과 열을 표시합니다.

## 알려진 제한 사항

- 한 번에 UTF-8 JSON 파일 하나를 처리하며 문서 전체를 메모리에 읽습니다. 원본은 그대로 보존합니다.
- 경로 문법은 키와 인덱스만 지원합니다. 완전한 JSONPath, 와일드카드, 필터,
  슬라이스, 음수 인덱스, 특수 키를 위한 이스케이프는 지원하지 않습니다.
- 숫자 상수 `NaN`, `Infinity`, `-Infinity`는 코드 `1`로 거부합니다.
  같은 철자의 문자열은 유효합니다.
- `1e400`처럼 문법상 유효하나 Python `float` 범위를 넘는 값은 검증을 통과할 수
  있습니다. 조회 결과에 해당 값이 포함되면 JSON 직렬화 오류로 코드 `2`를 반환합니다.

## 테스트

저장소 최상위 폴더에서 실행합니다.

```powershell
python -m unittest discover -s json-inspector/tests -v
```

[저장소의 GitHub Actions](https://github.com/ace1878/daily-dev-lab/actions)는 Ubuntu와
Windows의 Python 3.12에서 테스트를 실행합니다.

## 라이선스

현재 저장소에는 별도로 명시된 라이선스가 없습니다.
