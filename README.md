# 영수증 지출장부

영수증 사진을 Claude로 읽어 한 장에 한 줄씩 장부로 정리합니다.
날짜 · 가게 · 품목 · 합계 · 결제수단 · 분류(식비/교통/사무용품/배송/생활용품)

- 품목 금액의 합이 합계와 다르거나, 글자가 안 읽히는 영수증은 따로 알려 줍니다.
- 사진에 없는 내용은 비워 둡니다(지어내지 않음).

## 웹사이트
https://jaebong-choi.github.io/receipt-ledger/
Claude API 키를 넣고 사진을 끌어 놓으면 됩니다. 키와 사진은 브라우저에서 Anthropic으로만 바로 전송됩니다.

## PC에서 (파이썬)
```
pip install anthropic
set ANTHROPIC_API_KEY=sk-ant-...
python 장부만들기.py
```
`영수증` 폴더의 사진을 읽어 `지출장부.csv`를 만들고, 확인이 필요한 영수증과 분류별 합계를 출력합니다.
