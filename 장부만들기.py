"""영수증 폴더의 사진을 Claude로 읽어 지출장부.csv를 만든다.

사용법:  python 장부만들기.py            (같은 폴더의 '영수증' 폴더를 읽음)
         python 장부만들기.py 다른폴더
         python 장부만들기.py --test     (합계 검증 로직 자체 점검)
필요:    pip install anthropic   /   환경변수 ANTHROPIC_API_KEY
"""
import base64, csv, json, sys
from collections import defaultdict
from pathlib import Path

CATS = ["식비", "교통", "사무용품", "배송", "생활용품"]
TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
MAX_BYTES = 5 * 1024 * 1024  # API 이미지 한도

PROMPT = """영수증 사진 한 장을 JSON으로 옮겨라.
사진에 실제로 보이는 내용만 옮긴다. 안 보이거나 확실하지 않은 칸은 null로 둔다. 추측해서 채우지 않는다.
- date: YYYY-MM-DD
- store: 가게 이름
- items: 품목마다 이름과 그 줄의 최종 금액(원, 정수). 할인은 음수 줄로 넣는다. 금액이 안 보이면 amount는 null.
- total: 영수증에 적힌 최종 결제 합계(원, 정수)
- payment: 영수증에 적힌 결제수단 그대로(예: 신용카드 국민, 현금, 계좌이체)
- category: 품목을 보고 식비/교통/사무용품/배송/생활용품 중 하나. 영수증이 아니면 null.
- readable: 영수증이 아니거나 글자를 거의 못 읽으면 false"""

NS = {"type": ["string", "null"]}
NI = {"type": ["integer", "null"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "readable": {"type": "boolean"},
        "date": NS, "store": NS, "total": NI, "payment": NS,
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "amount": NI},
            "required": ["name", "amount"], "additionalProperties": False}},
        "category": {"anyOf": [{"type": "string", "enum": CATS}, {"type": "null"}]},
    },
    "required": ["readable", "date", "store", "items", "total", "payment", "category"],
    "additionalProperties": False,
}


def check(r):
    """문제 목록을 돌려준다. 빈 목록이면 통과."""
    if not r.get("readable"):
        return ["안 읽힘"]
    probs = [f"{name} 없음" for k, name in [("date", "날짜"), ("store", "가게"), ("payment", "결제수단"), ("category", "분류")] if not r.get(k)]
    amounts = [i["amount"] for i in r.get("items") or []]
    if not amounts:
        probs.append("품목 없음")
    elif None in amounts:
        probs.append("금액 안 읽힌 품목 있음")
    elif r.get("total") is None:
        probs.append("합계 없음")
    elif sum(amounts) != r["total"]:
        probs.append(f"합계 불일치: 품목 합 {sum(amounts):,} ≠ 합계 {r['total']:,}")
    return probs


def read_receipt(client, path):
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError(f"사진이 5MB를 넘음({len(data) // 1024 // 1024}MB) - 줄여서 다시 넣어 주세요")
    msg = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": TYPES[path.suffix.lower()],
                                         "data": base64.standard_b64encode(data).decode()}},
            {"type": "text", "text": PROMPT},
        ]}],
    )
    if msg.stop_reason != "end_turn":
        raise ValueError(f"응답이 중간에 멈춤({msg.stop_reason})")
    return json.loads(next(b.text for b in msg.content if b.type == "text"))


def main(folder):
    import anthropic
    client = anthropic.Anthropic()
    files = sorted(p for p in folder.iterdir() if p.is_file())
    photos = [p for p in files if p.suffix.lower() in TYPES]
    skipped = [p for p in files if p not in photos]
    if not photos:
        sys.exit(f"{folder} 에 사진(jpg/png/webp/gif)이 없습니다.")

    rows, problems, by_cat = [], [], defaultdict(int)
    for n, p in enumerate(photos, 1):
        print(f"[{n}/{len(photos)}] {p.name}", flush=True)
        try:
            r = read_receipt(client, p)
        except (anthropic.APIError, ValueError) as e:
            r, err = {"readable": False}, f"안 읽힘: {e}"
        else:
            err = None
        probs = [err] if err else check(r)
        if probs:
            problems.append((p.name, probs))
        if r.get("readable"):
            items = "; ".join(f"{i['name']} {i['amount']:,}" if i["amount"] is not None else f"{i['name']} ?" for i in r["items"])
            rows.append([p.name, r["date"] or "", r["store"] or "", items, r["total"] if r["total"] is not None else "",
                         r["payment"] or "", r["category"] or "", " / ".join(probs) or "OK"])
            if r["category"] and r["total"] is not None:
                by_cat[r["category"]] += r["total"]

    out = folder.parent / "지출장부.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: 엑셀에서 한글 안 깨짐
        w = csv.writer(f)
        w.writerow(["파일", "날짜", "가게", "품목", "합계", "결제수단", "분류", "검증"])
        w.writerows(rows)
    print(f"\n저장: {out}  ({len(rows)}줄)")

    print("\n[확인 필요]" if problems or skipped else "\n[확인 필요] 없음")
    for name, probs in problems:
        print(f"  {name}: {' / '.join(probs)}")
    for p in skipped:
        print(f"  {p.name}: 사진 형식 아님(HEIC 등은 JPG로 바꿔 주세요)")

    print("\n[분류별 합계]")
    for c in CATS:
        print(f"  {c:<6}{by_cat[c]:>12,}원")
    print(f"  {'총합':<6}{sum(by_cat.values()):>12,}원")


def _test():
    ok = {"readable": True, "date": "2026-11-01", "store": "가게", "payment": "현금", "category": "식비",
          "items": [{"name": "a", "amount": 3000}, {"name": "할인", "amount": -500}], "total": 2500}
    assert check(ok) == []
    assert check({**ok, "total": 3000}) == ["합계 불일치: 품목 합 2,500 ≠ 합계 3,000"]
    assert check({**ok, "items": [{"name": "a", "amount": None}]}) == ["금액 안 읽힌 품목 있음"]
    assert check({**ok, "store": None, "total": None}) == ["가게 없음", "합계 없음"]
    assert check({"readable": False}) == ["안 읽힘"]
    print("검증 로직 OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        _test()
    else:
        main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "영수증")
