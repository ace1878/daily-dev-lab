# JSON Inspector v1.0.0 릴리스 노트 초안

JSON Inspector의 첫 정식 릴리스 초안입니다.

## 주요 기능

- 단일 UTF-8 JSON 파일의 문법 검사와 구문 오류 위치 표시
- 루트 자료형, 키 또는 항목 수, 최대 깊이 요약
- 점과 배열 인덱스로 지정한 경로의 JSON 값 조회
- 문서 전체의 JSON 자료형별 값 개수 집계
- 기본 검사, 요약, 통계 결과의 기계 판독용 JSON 출력
- 비표준 숫자 상수 `NaN`, `Infinity`, `-Infinity` 거부 및 같은 철자의 문자열 허용
- folder-report와 별도로 설치되는 wheel 및 `json-inspector` 명령

## 설치 및 사용

Python 3.12 이상이 필요하며 런타임 외부 의존성은 없습니다. 저장소 최상위
폴더에서 설치합니다.

```powershell
python -m pip install ./json-inspector
json-inspector --version
json-inspector sample.json --summary --json
json-inspector sample.json --path "user.name"
```

소스 직접 실행은 `python json-inspector/json_inspector.py sample.json`을 사용합니다.
입력 예시와 전체 옵션은 [사용 안내](README.md)에 있습니다.

## 테스트 및 제한 사항

- Ubuntu와 Windows의 Python 3.12 CI에서 프로젝트 테스트를 실행하고, 이 릴리스
  변경에 wheel 빌드·설치 및 설치된 CLI의 `--help`, `--version` 검증을 포함합니다.
- 문서 전체를 메모리에 읽습니다. 경로 조회는 키와 0 이상의 인덱스를 지원합니다.
- `1e400`처럼 Python `float` 범위를 넘는 값을 조회하면 JSON 직렬화가 실패할 수 있습니다.
