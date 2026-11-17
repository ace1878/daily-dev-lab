# folder-report v1.0.0

## 주요 기능

- 폴더 전체 파일 수·용량 및 확장자별 통계
- 상위 N개 큰 파일 선정, 이름·크기순 표시 및 목록 전용 크기 필터
- 크기·확장자·탐색 깊이 필터와 파일·디렉터리 제외
- 제외 패턴 파일 및 정확한 디렉터리 이름 목록 파일
- 터미널 텍스트, JSON, CSV, Markdown 보고서
- 요약 출력, quiet 모드, 분석 시간 및 건너뛴 경로 표시
- strict 접근 오류 처리와 전체 용량 제한 검사
- 기존 보고서 덮어쓰기 보호 및 명시적인 `--force` 지원

## 출시 전 검수에서 수정한 문제

- `[ ]`가 포함된 출력 파일명을 리터럴 경로로 비교하여, 유사한 다른 파일의 잘못된
  제외와 보고서 자체의 재집계를 방지했습니다.
- 디렉터리 사전 확인 중 발생한 접근 오류를 건너뛴 경로에 기록합니다.
- 제외 목록 파일의 권한 오류 테스트가 패키지 설치 여부에 의존하던 문제를 수정했습니다.

## 설치 및 사용

Python 3.10 이상이 필요하며 런타임 외부 의존성은 없습니다.

```powershell
python -m pip install ./daily_dev_lab-1.0.0-py3-none-any.whl
folder-report --help
folder-report --version
folder-report . --summary-only
```

`--version` 출력은 `folder-report 1.0.0`입니다. 개발용 editable 설치와
`python folder_report.py` 직접 실행도 지원합니다.

## 입력 단위 및 종료 코드

- `--min-size`, `--max-size`, `--fail-over-size`는 정수 바이트와 KiB·MiB·GiB를 지원합니다.
- `--min-list-size`는 위 단위에 더해 B·KB·MB·GB를 지원합니다.
- 종료 코드는 정상 `0`, 입력·저장 오류 `2`, strict 접근 오류 `3`, 용량 제한 초과 `4`입니다.
- `--strict` 접근 오류가 발생하면 보고서를 저장하지 않습니다.
- `--fail-over-size` 용량 초과 시에는 보고서를 생성한 뒤 종료 코드 `4`를 반환합니다.

## 검증 정보

Windows·Python 3.14.7에서 미설치 소스, editable 설치, 격리 wheel 설치 환경의
전체 테스트 151개가 각각 통과했습니다.

출시 커밋의 Ubuntu·Windows CI 결과와 배포 산출물 정보는 GitHub Release 본문에서
확인할 수 있습니다. 첨부 wheel의 SHA-256 체크섬은 `SHA256SUMS`에 제공합니다.
