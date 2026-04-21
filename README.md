# AI싱크 재테크클럽 자동 브리핑 파이프라인

이 저장소는 매 영업일 오전 08:00 KST에 한국어 시장 브리핑 HTML을 생성하고 아카이브를 갱신하도록 설계되어 있습니다.

## 한 번만 설정

1. GitHub 저장소 `aisyncclub/moneyclub`의 `Settings > Secrets and variables > Actions`로 이동합니다.
2. `GEMINI_API_KEY` 시크릿을 추가합니다.
3. 필요하면 `Variables`에 `GEMINI_MODEL`을 추가합니다.
   기본값은 `gemini-2.0-flash`이며, 유료 모델을 쓰려면 `gemini-3.0-pro` 등으로 바꾸면 됩니다.

## 로컬 테스트

```bash
cd /Users/firstandre/dev_test_file/stock_study/_deploy_moneyclub
python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt
export GEMINI_API_KEY=your_key_here
export GEMINI_MODEL=gemini-2.0-flash
python scripts/collect_data.py
python scripts/generate_briefing.py
python scripts/deploy.py --date "$(python - <<'PY'\nimport json\nfrom pathlib import Path\nprint(json.loads(Path('data/latest.json').read_text())['date'])\nPY\n)" --no-push
```

## GitHub에서 수동 실행

`Actions > Daily Market Briefing > Run workflow`에서 수동 실행할 수 있습니다.

## 알려진 한계

- 스케줄은 주말을 건너뜁니다. `0 23 * * 0-4` 기준으로 월~금 KST 오전에만 실행됩니다.
- 무료 Gemini 모델은 응답 포맷 안정성과 호출 한도에서 변동이 있을 수 있습니다.
- 미국 장 마감 데이터 기준이라 한국 오전 시점의 선물/프리마켓 흐름과 완전히 같지 않을 수 있습니다.
- RSS 피드는 간헐적으로 지연되거나 차단될 수 있어, 일부 소스가 비면 다른 소스 중심으로 서술될 수 있습니다.
